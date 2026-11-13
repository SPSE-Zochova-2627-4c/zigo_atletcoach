# -*- coding: utf-8 -*-
"""
strava.py – prepojenie so Stravou (blueprint 'strava').

OAuth 2.0 prihlásenie, prehľad posledných aktivít, osobné rekordy z best_efforts a heatmapa behov.
Kľúče STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET / STRAVA_REDIRECT_URI sú v .env; bez nich appka beží,
len „Pripojiť Stravu“ vypíše, čo chýba.

Token: access token je v session, refresh token v tabuľke strava_token (patrí prihlásenému
používateľovi appky). Vypršaný token sa obnoví cez refresh token; ak to nejde, Strava sa odpojí,
ale používateľ ostane prihlásený v appke.
"""
import json
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for
from stravalib.client import Client

from auth import login_required, roles_required
from models import db, StravaToken

bp = Blueprint('strava', __name__)

API = 'https://www.strava.com/api/v3'
RUN_TYPES = ('Run', 'VirtualRun', 'TrailRun')
PR_CACHE_DIR = Path('cache')
PR_CACHE_SECONDS = 30 * 60

MSG_NOT_CONNECTED = 'Strava nie je pripojená. Pripojíš ju v menu Strava, položka Pripojiť Stravu.'
MSG_EXPIRED = 'Platnosť prepojenia so Stravou vypršala. Pripoj Stravu znova.'


def _config():
    return {
        'client_id': os.getenv('STRAVA_CLIENT_ID'),
        'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
        'redirect_uri': (os.getenv('STRAVA_REDIRECT_URI') or os.getenv('STRAVA_CALLBACK_URL')
                         or 'http://localhost:5001/strava/callback'),
    }


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
class StravaExpired(Exception):
    """Token sa nepodarilo obnoviť – treba sa na Stravu prihlásiť znova."""


def _refresh_token(athlete_id):
    """Platný access token pre Strava atléta; ak vypršal, obnoví ho cez refresh token z DB."""
    row = StravaToken.query.filter_by(athlete_id=str(athlete_id)).first()
    if not row:
        raise StravaExpired('k atlétovi nie je uložený token')
    if row.expires_at and row.expires_at - 30 > int(time.time()):
        return row.access_token
    if not row.refresh_token:
        raise StravaExpired('chýba refresh token')

    cfg = _config()
    try:
        resp = requests.post('https://www.strava.com/oauth/token', timeout=10, data={
            'client_id': cfg['client_id'],
            'client_secret': cfg['client_secret'],
            'grant_type': 'refresh_token',
            'refresh_token': row.refresh_token,
        })
    except requests.RequestException as e:
        raise StravaExpired(f'Strava neodpovedá ({e.__class__.__name__})') from e
    if resp.status_code != 200:
        raise StravaExpired(f'obnovenie tokenu zlyhalo (HTTP {resp.status_code})')

    new = resp.json()
    row.access_token = new.get('access_token')
    row.refresh_token = new.get('refresh_token') or row.refresh_token
    row.expires_at = new.get('expires_at')
    db.session.commit()
    session['strava_access_token'] = row.access_token
    session['strava_expires_at'] = row.expires_at
    return row.access_token


def current_token():
    """
    Platný access token prihláseného používateľa, alebo None, ak Strava nie je pripojená.
    Vyhodí StravaExpired, keď token vypršal a nedá sa obnoviť.
    """
    athlete_id = session.get('strava_athlete_id')
    if athlete_id:
        return _refresh_token(athlete_id)
    return session.get('strava_access_token')


def _clear_session():
    """Odpojí Stravu, ale nechá používateľa prihláseného v appke (žiadne session.clear())."""
    for key in [k for k in list(session.keys()) if k.startswith('strava_')]:
        session.pop(key, None)
    session.modified = True


def _token_or_redirect(missing_target='index'):
    """(token, None) alebo (None, odpoveď s presmerovaním a hlásením) pre stránky Stravy."""
    try:
        token = current_token()
    except StravaExpired:
        _clear_session()
        flash(MSG_EXPIRED, 'warning')
        return None, redirect(url_for('index'))
    if not token:
        flash(MSG_NOT_CONNECTED, 'warning')
        return None, redirect(url_for(missing_target))
    return token, None


def _token_or_json_error():
    """(token, None) alebo (None, JSON chyba 401) pre API volania z JavaScriptu."""
    try:
        token = current_token()
    except StravaExpired:
        return None, (jsonify({'error': MSG_EXPIRED}), 401)
    if not token:
        return None, (jsonify({'error': MSG_NOT_CONNECTED}), 401)
    return token, None


# ---------------------------------------------------------------------------
# Formátovanie
# ---------------------------------------------------------------------------
def pace_from_speed(speed):
    """m/s → tempo „4:05 /km“."""
    if not speed:
        return '-'
    pace_sec = 1000 / float(speed)
    return f'{int(pace_sec // 60)}:{int(pace_sec % 60):02d} /km'


def speed_to_kmh(speed):
    if not speed:
        return '-'
    return f'{float(speed) * 3.6:.1f} km/h'


def swim_pace_from_speed(speed):
    if not speed:
        return '-'
    pace_sec = 100 / float(speed)
    return f'{int(pace_sec // 60)}:{int(pace_sec % 60):02d} /100m'


def seconds_to_time(seconds):
    """Sekundy → „H:MM:SS“ alebo „M:SS“."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, sec = divmod(rem, 60)
    return f'{h}:{m:02d}:{sec:02d}' if h else f'{m}:{sec:02d}'


def pace_str(seconds, km):
    """Tempo „M:SS“ na kilometer, alebo „—“ ak chýbajú údaje."""
    if not seconds or not km:
        return '—'
    m, s = divmod(int(seconds / km), 60)
    return f'{m}:{s:02d}'


def decode_polyline(encoded):
    """Dekóduje Google encoded polyline (formát trás zo Stravy) na zoznam [lat, lng]."""
    points = []
    index = lat = lng = 0
    while index < len(encoded):
        for coord_idx in range(2):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 32:
                    break
            value = ~(result >> 1) if result & 1 else result >> 1
            if coord_idx == 0:
                lat += value
            else:
                lng += value
        points.append([round(lat / 1e5, 5), round(lng / 1e5, 5)])
    return points


# ---------------------------------------------------------------------------
# Osobné rekordy (best efforts) – s 30-minútovou cache na disku
# ---------------------------------------------------------------------------
PR_KEYS = ('400m', '800m', '5k', '10k', 'half', 'marathon')
# celková vzdialenosť aktivity v km → kľúč rekordu
PR_DISTANCE_RANGES = {
    '400m': (0.35, 0.45), '800m': (0.75, 0.90),
    '5k': (4.8, 5.2), '10k': (9.7, 10.3), 'half': (20.5, 21.5), 'marathon': (41.5, 42.8),
}
# názov best_effort v API Stravy → kľúč rekordu (800 m volá Strava „1/2 mile“)
BEST_EFFORT_KEYS = {
    '400m': '400m', '1/2 mile': '800m', '5k': '5k', '10k': '10k',
    'Half-Marathon': 'half', 'Marathon': 'marathon',
}


def _pr_cache_file(token):
    return PR_CACHE_DIR / f'prs_{(token or "")[-8:]}.json'


def cached_prs(token):
    """Rekordy z cache bez volania Stravy (pre kontext AI trénera); {} ak cache nie je."""
    try:
        return json.loads(_pr_cache_file(token).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def clear_pr_cache(token):
    try:
        _pr_cache_file(token).unlink()
    except OSError:
        pass


def _pr_entry(elapsed, dist_km, date_text, url, avg_hr=None, cadence=None, elevation=None):
    return {
        'time': seconds_to_time(elapsed),
        'pace': pace_str(elapsed, dist_km),
        'date': date_text,
        'avg_hr': round(avg_hr) if avg_hr else None,
        'elevation': round(elevation or 0) or None,
        'cadence': round(cadence * 2) if cadence else None,
        'strava_url': url,
        '_elapsed': elapsed,
    }


def _offer(best, key, entry):
    if best[key] is None or entry['_elapsed'] < best[key]['_elapsed']:
        best[key] = entry


def get_strava_prs(token):
    """
    Najlepšie časy na 400 m – maratón. Prejde až 300 posledných behov (súhrn aktivít)
    a pre 90 najnovších stiahne detail s best_efforts (paralelne, 10 vlákien).
    """
    cache_file = _pr_cache_file(token)
    try:
        if time.time() - cache_file.stat().st_mtime < PR_CACHE_SECONDS:
            cached = json.loads(cache_file.read_text(encoding='utf-8'))
            return {k: cached.get(k) for k in PR_KEYS}
    except (OSError, ValueError):
        pass

    headers = {'Authorization': f'Bearer {token}'}
    best = {k: None for k in PR_KEYS}
    run_ids = []

    for page in range(1, 4):
        resp = requests.get(f'{API}/athlete/activities', headers=headers,
                            params={'per_page': 100, 'page': page}, timeout=15)
        try:
            activities = resp.json()
        except ValueError:
            break
        if not activities or not isinstance(activities, list):
            break
        for act in activities:
            if act.get('type') not in RUN_TYPES or not act.get('moving_time'):
                continue
            dist_km = (act.get('distance') or 0) / 1000
            for key, (lo, hi) in PR_DISTANCE_RANGES.items():
                if lo <= dist_km <= hi:
                    _offer(best, key, _pr_entry(
                        act['moving_time'], dist_km, (act.get('start_date_local') or '')[:10],
                        f"https://www.strava.com/activities/{act['id']}",
                        act.get('average_heartrate'), act.get('average_cadence'),
                        act.get('total_elevation_gain')))
            run_ids.append(act['id'])
        if len(activities) < 100:
            break

    def fetch_detail(activity_id):
        try:
            r = requests.get(f'{API}/activities/{activity_id}', headers=headers, timeout=10)
            return r.json() if r.status_code == 200 else None
        except (requests.RequestException, ValueError):
            return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        for future in as_completed([pool.submit(fetch_detail, aid) for aid in run_ids[:90]]):
            detail = future.result()
            if not detail:
                continue
            url = f"https://www.strava.com/activities/{detail['id']}"
            for effort in detail.get('best_efforts') or []:
                key = BEST_EFFORT_KEYS.get(effort.get('name', ''))
                elapsed = effort.get('elapsed_time') or 0
                if not key or not elapsed:
                    continue
                _offer(best, key, _pr_entry(
                    elapsed, (effort.get('distance') or 400) / 1000,
                    (detail.get('start_date_local') or '')[:10], url,
                    detail.get('average_heartrate'), detail.get('average_cadence'),
                    detail.get('total_elevation_gain')))

    for entry in best.values():
        if entry:
            entry.pop('_elapsed', None)
    try:
        PR_CACHE_DIR.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps(best), encoding='utf-8')
    except OSError:
        pass
    return best


# ---------------------------------------------------------------------------
# Routy
# ---------------------------------------------------------------------------
@bp.route('/strava/login')
@login_required
def login():
    if session.get('strava_access_token'):
        return redirect(url_for('strava.activities'))
    cfg = _config()
    if not cfg['client_id'] or not cfg['client_secret']:
        # Bez kľúčov v .env nemá Strava kam presmerovať – nie je to chyba servera, len chýbajúca konfigurácia.
        flash('Strava nie je nastavená: do súboru .env doplň STRAVA_CLIENT_ID a STRAVA_CLIENT_SECRET '
              '(pozri .env.example).', 'warning')
        return redirect(request.referrer or url_for('index'))

    # `state` sa v callbacku porovná so session – cudzí podstrčený kód sa tak neprepojí s týmto účtom
    state = secrets.token_urlsafe(16)
    session['strava_oauth_state'] = state
    params = {
        'client_id': cfg['client_id'],
        'response_type': 'code',
        'redirect_uri': cfg['redirect_uri'],
        'scope': 'read,activity:read_all',
        'approval_prompt': 'force',
        'state': state,
    }
    return redirect(f'https://www.strava.com/oauth/authorize?{urlencode(params)}')


@bp.route('/strava/callback')
@login_required
def callback():
    expected_state = session.pop('strava_oauth_state', None)
    code = request.args.get('code')
    if not code or not expected_state or request.args.get('state') != expected_state:
        flash('Prepojenie so Stravou sa nepodarilo overiť. Skús to znova cez „Pripojiť Stravu“.', 'danger')
        return redirect(url_for('index'))

    cfg = _config()
    try:
        token = Client().exchange_code_for_token(
            client_id=cfg['client_id'], client_secret=cfg['client_secret'], code=code)
    except Exception as e:  # stravalib balí chyby siete aj API do rôznych výnimiek
        current_app.logger.warning('Strava: výmena kódu za token zlyhala: %r', e)
        flash('Strava neodpovedala alebo odmietla prihlásenie. Skús to o chvíľu znova.', 'danger')
        return redirect(url_for('index'))

    athlete = token.get('athlete') or {}
    athlete_id = str(athlete['id']) if athlete.get('id') else None
    session['strava_access_token'] = token['access_token']
    session['strava_expires_at'] = token['expires_at']
    session['strava_athlete_id'] = athlete_id

    if athlete_id:
        row = StravaToken.query.filter_by(athlete_id=athlete_id).first()
        if row is None:
            row = StravaToken(athlete_id=athlete_id, access_token=token['access_token'])
            db.session.add(row)
        row.access_token = token['access_token']
        row.refresh_token = token['refresh_token']
        row.expires_at = token['expires_at']
        row.user_id = g.user.id          # token patrí prihlásenému používateľovi appky
        db.session.commit()

    flash('Strava je pripojená.', 'success')
    return redirect(url_for('strava.activities'))


@bp.route('/strava/logout')
@login_required
def logout():
    """Odpojí Stravu od účtu (odhlásenie z appky je /odhlasenie v auth.py)."""
    access_token = session.get('strava_access_token')
    athlete_id = session.get('strava_athlete_id')
    if access_token:
        # Odvolanie na strane Stravy – ďalšie pripojenie si znova vypýta súhlas
        try:
            requests.post('https://www.strava.com/oauth/deauthorize',
                          data={'access_token': access_token}, timeout=5)
        except requests.RequestException:
            pass
    if athlete_id:
        # Zmazať len vlastný token (alebo starý bez vlastníka), aby sa nedal potichu obnoviť
        StravaToken.query.filter(
            StravaToken.athlete_id == str(athlete_id),
            db.or_(StravaToken.user_id == g.user.id, StravaToken.user_id.is_(None)),
        ).delete(synchronize_session=False)
        db.session.commit()
    _clear_session()
    flash('Strava bola odpojená.', 'success')
    return redirect(url_for('index'))


@bp.route('/dashboard')
@login_required
def activities():
    """Posledných 10 aktivít zo Stravy."""
    token, response = _token_or_redirect()
    if response:
        return response

    client = Client()
    client.access_token = token
    try:
        rows = []
        for act in client.get_activities(limit=10):
            kind = str(act.type) if act.type else ''
            low = kind.lower()
            if 'ride' in low or 'cycling' in low:
                pace = speed_to_kmh(act.average_speed)
            elif 'swim' in low:
                pace = swim_pace_from_speed(act.average_speed)
            else:
                pace = pace_from_speed(act.average_speed)
            moving = int(act.moving_time)
            hr = getattr(act, 'average_heartrate', None)
            rows.append({
                'name': act.name,
                'type': kind,
                'distance': round(float(act.distance) / 1000, 2),
                'moving_time': f'{moving // 60}:{moving % 60:02d}',
                'pace': pace,
                'hr': int(hr) if hr else None,
                'date': act.start_date.strftime('%d.%m.%Y %H:%M'),
            })
    except Exception as e:  # sieť, limit API, zmenený formát odpovede
        current_app.logger.warning('Strava: načítanie aktivít zlyhalo: %r', e)
        flash('Aktivity zo Stravy sa nepodarilo načítať. Skús to o chvíľu znova.', 'danger')
        return redirect(url_for('index'))
    return render_template('dashboard.html', trainings=rows, logged_in=True)


@bp.route('/osobaky')
@login_required
def prs():
    token, response = _token_or_redirect(missing_target='strava.login')
    if response:
        return response
    if request.args.get('refresh') == '1':
        clear_pr_cache(token)
    error = None
    try:
        records = get_strava_prs(token)
    except (requests.RequestException, ValueError, KeyError) as e:
        current_app.logger.warning('Strava: rekordy zlyhali: %r', e)
        records, error = {}, 'Nepodarilo sa načítať osobné rekordy zo Stravy.'
    return render_template('osobaky.html', prs=records, error=error)


@bp.route('/heatmap')
@login_required
def heatmap():
    if not session.get('strava_access_token') and not session.get('strava_athlete_id'):
        flash(MSG_NOT_CONNECTED, 'warning')
        return redirect(url_for('strava.login'))
    return render_template('heatmap.html')


@bp.route('/api/heatmap-data')
@login_required
def heatmap_data():
    """Body všetkých behov (každý druhý bod trasy) pre heatmapu."""
    token, error = _token_or_json_error()
    if error:
        return error
    headers = {'Authorization': f'Bearer {token}'}
    points, count, page = [], 0, 1
    while True:
        try:
            resp = requests.get(f'{API}/athlete/activities', headers=headers,
                                params={'per_page': 100, 'page': page}, timeout=20)
        except requests.RequestException:
            break                       # ukáž aspoň to, čo sa stihlo načítať
        if resp.status_code != 200:
            break
        activities = resp.json()
        if not activities or not isinstance(activities, list):
            break
        for act in activities:
            polyline = (act.get('map') or {}).get('summary_polyline')
            if act.get('type') not in RUN_TYPES or not polyline:
                continue
            try:
                points.extend(decode_polyline(polyline)[::2])
                count += 1
            except IndexError:      # poškodená polyline – preskočiť len túto aktivitu
                continue
        if len(activities) < 100:
            break
        page += 1
    return jsonify({'points': points, 'activity_count': count})


@bp.route('/api/debug-prs')
@roles_required('admin')
def debug_prs():
    """Diagnostika pre admina: čo Strava vracia v best_efforts posledných 5 behov."""
    token, error = _token_or_json_error()
    if error:
        return error
    headers = {'Authorization': f'Bearer {token}'}
    resp = requests.get(f'{API}/athlete/activities', headers=headers,
                        params={'per_page': 10, 'page': 1}, timeout=15)
    results = []
    for act in (resp.json() if resp.status_code == 200 else []):
        if act.get('type') not in RUN_TYPES:
            continue
        detail = requests.get(f"{API}/activities/{act['id']}", headers=headers, timeout=10)
        if detail.status_code != 200:
            continue
        results.append({
            'activity_name': act.get('name'),
            'distance_km': round((act.get('distance') or 0) / 1000, 2),
            'moving_time': act.get('moving_time'),
            'best_efforts': [{'name': e.get('name'), 'elapsed_time': e.get('elapsed_time'),
                              'distance_m': e.get('distance')}
                             for e in detail.json().get('best_efforts') or []],
        })
        if len(results) >= 5:
            break
    return jsonify(results)
