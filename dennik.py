# -*- coding: utf-8 -*-
"""
dennik.py – osobný denník zverenca (blueprint 'dennik').

- Tréningy:    /trainings     zápis tréningu (typ, vzdialenosť, čas, úseky, poznámka) a kalendár
- Regenerácia: /log           HRV, regenerácia a pokojový tep; import z CSV súborov WHOOP
- Pripravenosť: /api/readiness skóre 0–100 z dnešného HRV voči 30-dňovému priemeru a regenerácie

HRV, regenerácia a pokojový tep sú údaje o zdraví (čl. 9 GDPR) – ukladajú sa len s výslovným
súhlasom, ktorý používateľ dáva pri každom zápise aj importe (políčko health_consent).
"""
import csv
import io
import json
import math
import re
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from auth import login_required
from models import db, BiometricLog, TrainingLog

bp = Blueprint('dennik', __name__)

HEALTH_CONSENT_MSG = ('Bez súhlasu so spracovaním údajov o zdraví sa meranie neuloží. '
                      'Zaškrtni políčko so súhlasom a skús to znova.')

# Fyziologicky zmysluplné rozsahy – mimo nich ide o preklep alebo chybný import
HRV_RANGE = (0, 500)          # ms, otvorený interval
RECOVERY_RANGE = (0, 100)     # %
RHR_RANGE = (20, 250)         # údery za minútu


def _health_consent_given():
    return request.form.get('health_consent') == '1'


def _in_range(value, bounds, open_interval=False):
    lo, hi = bounds
    if value is None or not math.isfinite(value):
        return False
    return lo < value < hi if open_interval else lo <= value <= hi


# ---------------------------------------------------------------------------
# Tréningový denník
# ---------------------------------------------------------------------------
@bp.route('/trainings', methods=['GET', 'POST'])
@login_required
def trainings():
    if request.method == 'POST':
        t_type = (request.form.get('training_type') or '').strip()
        if not t_type:
            flash('Vyber alebo napíš typ tréningu.', 'danger')
            return redirect(url_for('dennik.trainings'))
        dur_sec = request.form.get('dur_sec', type=int)
        dur_hun = request.form.get('dur_hun', type=int)
        intervals = [i.strip() for i in request.form.getlist('interval_times[]') if i.strip()]
        db.session.add(TrainingLog(
            user_id=g.user.id,
            training_type=t_type[:100],
            distance_km=request.form.get('distance_km', type=float),
            duration_min=request.form.get('dur_min', type=int),
            duration_sec=(float((dur_sec or 0) + (dur_hun or 0) / 100.0)
                          if dur_sec is not None or dur_hun is not None else None),
            intervals_data=','.join(intervals) or None,
            notes=request.form.get('notes'),
        ))
        db.session.commit()
        flash('Tréning uložený.', 'success')
        return redirect(url_for('dennik.trainings'))

    all_trainings = TrainingLog.query.filter_by(user_id=g.user.id) \
        .order_by(TrainingLog.date.desc()).all()
    grouped, by_date = {}, {}
    for t in all_trainings:
        grouped.setdefault(t.training_type, []).append(t)
        by_date.setdefault(t.date.strftime('%Y-%m-%d'), []).append(t.training_type)
    return render_template('trainings.html', grouped_trainings=grouped,
                           train_dates_json=json.dumps(by_date))


# ---------------------------------------------------------------------------
# Regenerácia a HRV
# ---------------------------------------------------------------------------
@bp.route('/log', methods=['GET', 'POST'])
@login_required
def log_data():
    if request.method == 'POST':
        if not _health_consent_given():
            flash(HEALTH_CONSENT_MSG, 'danger')
            return redirect(url_for('dennik.log_data'))
        hrv = request.form.get('hrv', type=float)
        recovery = request.form.get('recovery', type=int)
        rhr = request.form.get('rhr', type=int)
        if not _in_range(hrv, HRV_RANGE, open_interval=True):
            flash('Zadaj HRV ako číslo v milisekundách (0–500).', 'danger')
        elif recovery is not None and not _in_range(recovery, RECOVERY_RANGE):
            flash('Regenerácia musí byť 0–100 %.', 'danger')
        elif rhr is not None and not _in_range(rhr, RHR_RANGE):
            flash('Pokojový tep musí byť 20–250 úderov za minútu.', 'danger')
        else:
            db.session.add(BiometricLog(user_id=g.user.id, hrv=hrv, recovery=recovery, rhr=rhr))
            db.session.commit()
            flash('Meranie uložené.', 'success')
        return redirect(url_for('dennik.log_data'))

    logs = BiometricLog.query.filter_by(user_id=g.user.id) \
        .order_by(BiometricLog.date.desc(), BiometricLog.id.desc()).limit(14).all()
    return render_template('log.html', logs=logs)


@bp.route('/log/<int:log_id>/zmazat', methods=['POST'])
@login_required
def log_delete(log_id):
    """Zmazanie jedného biometrického záznamu – smie len jeho vlastník."""
    row = db.session.get(BiometricLog, log_id)
    if row is None:
        abort(404)
    if row.user_id != g.user.id:
        abort(403)
    when = row.date.strftime('%d. %m. %Y')
    db.session.delete(row)
    db.session.commit()
    flash(f'Meranie z {when} bolo zmazané.', 'success')
    return redirect(url_for('dennik.log_data'))


# --- import WHOOP --------------------------------------------------------------
WHOOP_DATE_COLS = ('Cycle start time', 'Date', 'Day', 'cycle_start_time', 'Start Time', 'start_time',
                   'Datum', 'Dátum')
WHOOP_HRV_COLS = ('Heart rate variability (ms)', 'HRV (ms)', 'HRV', 'Heart Rate Variability',
                  'heart_rate_variability_ms', 'hrv_rmssd_ms')
WHOOP_RECOVERY_COLS = ('Recovery score %', 'Recovery (%)', 'Recovery score', 'recovery_score', 'Recovery')
WHOOP_RHR_COLS = ('Resting heart rate (bpm)', 'RHR (bpm)', 'RHR', 'resting_heart_rate', 'Resting heart rate')
DATE_FORMATS = ('%Y-%m-%d', '%d.%m.%Y', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d')


def find_column(row, names):
    """Hodnota stĺpca podľa prvého názvu z `names`, ktorý v riadku je (bez ohľadu na veľkosť písmen)."""
    by_name = {col.strip().lower(): value for col, value in row.items() if col}
    for name in names:
        value = by_name.get(name.strip().lower())
        if value is not None:
            return value.strip() or None
    return None


def to_float(value):
    """„65,2 ms“ → 65.2; prázdne alebo nečíselné → None."""
    if not value:
        return None
    cleaned = re.sub(r'[^\d.\-]', '', str(value).replace(',', '.'))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def parse_date(text):
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


def decode_csv(raw):
    """Bajty súboru → text; WHOOP exportuje UTF-8, staršie tabuľky môžu byť cp1250 / latin-1."""
    for enc in ('utf-8-sig', 'cp1250', 'latin-1'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def parse_whoop_csv(content):
    """
    Riadky CSV z WHOOP → zoznam slovníkov {date, hrv, recovery, rhr} + počet preskočených riadkov
    a názvy stĺpcov (do hlásenia, keď sa nič nenačíta). Hlavička nemusí byť na prvom riadku.
    """
    lines = content.splitlines()
    header_idx = next((i for i, line in enumerate(lines)
                       if ('date' in line.lower() or 'time' in line.lower())
                       and any(k in line.lower() for k in ('hrv', 'recovery', 'heart'))), 0)
    reader = csv.DictReader(io.StringIO('\n'.join(lines[header_idx:])))
    columns = reader.fieldnames or []
    rows, skipped = [], 0
    for row in reader:
        entry_date = parse_date(find_column(row, WHOOP_DATE_COLS))
        hrv = to_float(find_column(row, WHOOP_HRV_COLS))
        if entry_date is None or not _in_range(hrv, HRV_RANGE, open_interval=True):
            skipped += 1
            continue
        recovery = to_float(find_column(row, WHOOP_RECOVERY_COLS))
        rhr = to_float(find_column(row, WHOOP_RHR_COLS))
        # Neplatné recovery/RHR sa len vynechajú, HRV je povinné
        rows.append({
            'date': entry_date, 'hrv': hrv,
            'recovery': int(recovery) if _in_range(recovery, RECOVERY_RANGE) else None,
            'rhr': int(rhr) if _in_range(rhr, RHR_RANGE) else None,
        })
    return rows, skipped, columns


@bp.route('/import-whoop', methods=['POST'])
@login_required
def import_whoop():
    if not _health_consent_given():
        flash(HEALTH_CONSENT_MSG, 'danger')
        return redirect(url_for('dennik.log_data'))
    files = [f for f in request.files.getlist('whoop_csv') if f and f.filename.lower().endswith('.csv')]
    if not files:
        flash('Vyber platný CSV súbor z WHOOP.', 'danger')
        return redirect(url_for('dennik.log_data'))

    existing = {d for (d,) in db.session.query(BiometricLog.date).filter_by(user_id=g.user.id)}
    imported = skipped = 0
    columns = []
    for f in files:
        content = decode_csv(f.stream.read())
        if content is None:
            skipped += 1
            continue
        rows, bad, cols = parse_whoop_csv(content)
        skipped += bad
        columns = columns or cols
        for r in rows:
            if r['date'] in existing:       # duplicita sa hľadá len v záznamoch tohto používateľa
                skipped += 1
                continue
            existing.add(r['date'])
            db.session.add(BiometricLog(user_id=g.user.id, **r))
            imported += 1
    db.session.commit()

    if imported == 0:
        msg = f'Import: 0 pridaných, {skipped} preskočených.'
        if columns:
            msg += ' Stĺpce v súbore: ' + ', '.join(f'"{c}"' for c in columns[:10])
        flash(msg, 'warning')
    else:
        flash(f'Import dokončený: {imported} záznamov pridaných z {len(files)} súbor(ov), '
              f'{skipped} preskočených.', 'success')
    return redirect(url_for('dennik.log_data'))


# ---------------------------------------------------------------------------
# Pripravenosť na tréning
# ---------------------------------------------------------------------------
READINESS_LEVELS = (
    # (od %, nadpis, vysvetlenie, farba, ikona)
    (80, 'Trénuj naplno', 'Podľa HRV a regenerácie si dobre zregenerovaný. Vhodný deň na intenzívnejší tréning.',
     'green', 'rocket_launch'),
    (60, 'Stredný tréning', 'Hodnoty sú v poriadku. Vhodné tempové behy alebo stredné intervaly.',
     'yellow', 'directions_run'),
    (40, 'Ľahký tréning', 'Hodnoty naznačujú, že telo ešte regeneruje. Skôr ľahký klus alebo strečing.',
     'orange', 'self_improvement'),
    (0, 'Oddychuj', 'HRV a regenerácia sú nízke. Dnes je lepší aktívny odpočinok než tréning.',
     'red', 'bedtime'),
)


def readiness_score(hrv_today, hrv_avg, recovery=None):
    """
    Pripravenosť 0–100 %. HRV voči priemeru (pomer orezaný na 0,5–1,5) dáva 0–60 bodov,
    regenerácia 0–100 % dáva 0–40 bodov. Bez regenerácie sa HRV časť prepočíta na 0–100.
    """
    ratio = max(0.5, min(1.5, hrv_today / hrv_avg if hrv_avg else 1.0))
    hrv_points = (ratio - 0.5) * 60
    if recovery is not None:
        return round(min(100, max(0, hrv_points + recovery * 0.4)))
    return round(min(100, max(0, hrv_points / 60 * 100)))


@bp.route('/api/readiness')
@login_required
def readiness():
    today = date.today()
    mine = BiometricLog.query.filter_by(user_id=g.user.id)
    last = mine.filter_by(date=today).order_by(BiometricLog.id.desc()).first() \
        or mine.order_by(BiometricLog.date.desc()).first()
    if last is None:
        # Bez meraní to nie je chyba – stránka ukáže prázdny stav s odkazom na zápis
        return jsonify({'empty': True,
                        'message': 'Zatiaľ žiadne merania. Najprv si zapíš HRV a regeneráciu.'})

    hrv_values = [l.hrv for l in mine.filter(BiometricLog.date >= today - timedelta(days=30))
                  if l.hrv is not None]
    avg_hrv = sum(hrv_values) / len(hrv_values) if hrv_values else last.hrv
    pct = readiness_score(last.hrv, avg_hrv, last.recovery)
    _, label, sublabel, color, icon = next(level for level in READINESS_LEVELS if pct >= level[0])
    diff = round(last.hrv - avg_hrv, 1)
    return jsonify({
        'readiness': pct,
        'label': label,
        'sublabel': sublabel,
        'color': color,
        'icon': icon,
        'hrv': round(last.hrv, 1),
        'hrv_avg_30': round(avg_hrv, 1),
        'hrv_diff': f'+{diff}' if diff >= 0 else str(diff),
        'recovery': last.recovery,
        'rhr': last.rhr,
        'log_date': last.date.strftime('%d.%m.%Y'),
        'days_of_data': len(hrv_values),
    })
