# -*- coding: utf-8 -*-
"""
analyza.py – analýza behu z videa (blueprint 'analyza').

Dva druhy analýzy zdieľajú celý postup (nahratie → úloha vo vlákne → uloženie → výsledok):
- 'sprint'  /video     kontakt so zemou, letová fáza, frekvencia, dĺžka kroku, uhly (video_analysis.py)
- 'hurdles' /prekazky  medzičasy a kroky medzi prekážkami (hurdle_analysis.py)
Rozdiely medzi nimi sú len v slovníku KINDS (šablóna, model, funkcia analýzy, stĺpce do DB).

Videá nesmú ležať v static/ – tam ich Flask podá komukoľvek, kto pozná URL. Ležia v instance/videos
a podáva ich chránená routa /media/<súbor> (kontrola, či používateľ smie vidieť analýzu).
"""
import json
import os
import re
import shutil
import threading
import uuid
from collections import namedtuple

from flask import (Blueprint, abort, current_app, g, jsonify, render_template, request,
                   send_from_directory)

from ai_trener import AIError, groq_available, groq_complete
from auth import athlete_ids_visible_to, login_required, row_visible, scope_query, visible_athletes
from models import db, HurdleAnalysis, User, UserProfile, VideoAnalysis

bp = Blueprint('analyza', __name__)

ALLOWED_VIDEO_EXT = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm'}
HISTORY_LIMIT = 25

Upload = namedtuple('Upload', 'job_id path stored_name original_name')


def _engine():
    """
    Modul analýzy videa sa načíta až pri prvom použití: ťahá OpenCV a MediaPipe (pomalý import)
    a zvyšok appky musí fungovať aj bez nich (stránka potom vypíše, čo doinštalovať).
    """
    import video_analysis
    return video_analysis


def video_dir(app=None):
    return os.path.join((app or current_app).instance_path, 'videos')


@bp.record_once
def _prepare_storage(state):
    """Pri registrácii: priečinok na videá + presun videí zo starej verzie, ktorá ich dávala do static/."""
    target = video_dir(state.app)
    os.makedirs(target, exist_ok=True)
    legacy = os.path.join(state.app.root_path, 'static', 'uploads', 'videos')
    if os.path.isdir(legacy):
        for name in os.listdir(legacy):
            src = os.path.join(legacy, name)
            if os.path.isfile(src) and not os.path.exists(os.path.join(target, name)):
                try:
                    shutil.move(src, os.path.join(target, name))
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Prebiehajúce úlohy: job_id → stav. Žijú v pamäti procesu, po reštarte sa zabudnú (výsledky sú v DB).
# ---------------------------------------------------------------------------
_jobs = {}
_jobs_lock = threading.Lock()


def _job_set(job_id, **values):
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).update(values)
        finished = [k for k, v in _jobs.items() if v.get('state') in ('done', 'error')]
        for k in finished[:-20]:          # hotové úlohy sa nedržia donekonečna
            _jobs.pop(k, None)


def _job_get(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


# ---------------------------------------------------------------------------
# Druhy analýzy
# ---------------------------------------------------------------------------
def _run_sprint(path, opts, **files):
    return _engine().analyze_video(
        path, athlete_height_cm=opts['height_cm'], real_fps=opts['fps_override'],
        with_flow=opts['with_flow'], init_point=opts['init_point'], phase=opts['phase'], **files)


def _run_hurdles(path, opts, **files):
    import hurdle_analysis
    return hurdle_analysis.analyze_hurdle_video(
        path, discipline=opts['discipline'], athlete_height_cm=opts['height_cm'],
        real_fps=opts['fps_override'], with_flow=opts['with_flow'], init_point=opts['init_point'], **files)


def _sprint_columns(result):
    s = result['summary']
    return {key: s[key] for key in ('steps_detected', 'contact_ms_mean', 'contact_ms_sd', 'flight_ms_mean',
                                    'cadence_spm', 'duty_factor_pct', 'asymmetry_pct', 'speed_ms',
                                    'stride_length_m')}


def _hurdles_columns(result):
    s = result['summary']
    return {
        'discipline': result['discipline'],
        'hurdles_detected': s['hurdles_detected'],
        'interval_mean_s': s['interval_mean_s'],
        'interval_sd_s': s['interval_sd_s'],
        'steps_pattern': s['steps_pattern_text'],
        'flight_ms_mean': s['flight_ms_mean'],
        'landing_contact_ms_mean': s['landing_contact_ms_mean'],
        'speed_between_ms_mean': s['speed_between_ms_mean'],
    }


KINDS = {
    'sprint': {'model': VideoAnalysis, 'template': 'video.html', 'run': _run_sprint, 'columns': _sprint_columns},
    'hurdles': {'model': HurdleAnalysis, 'template': 'prekazky.html', 'run': _run_hurdles,
                'columns': _hurdles_columns},
}


# ---------------------------------------------------------------------------
# Pomocné funkcie
# ---------------------------------------------------------------------------
def _video_url(name):
    # Bez url_for – volá sa aj z vlákna analýzy, kde nie je aktívny request.
    return f'/media/{name}' if name else None


def _attach_urls(result):
    """Doplní do výsledku URL prekryvného videa a kľúčových snímok."""
    overlay = result.get('overlay_path')
    result['overlay_url'] = _video_url(os.path.basename(overlay)) if overlay else None
    for k in result.get('keyframes') or []:
        k['url'] = _video_url(k['file'])
    return result


def _form_number(name):
    raw = (request.form.get(name) or '').strip().replace(',', '.')
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _parse_upload_form():
    """Nastavenia analýzy z formulára (spoločné pre šprint aj prekážky)."""
    px, py = _form_number('click_x'), _form_number('click_y')
    return {
        'height_cm': _form_number('height_cm'),
        'fps_override': _form_number('fps_override'),
        'make_overlay': request.form.get('overlay', '1') != '0',
        'with_flow': request.form.get('flow', '1') != '0',
        'label': (request.form.get('label') or '').strip()[:120],
        # kliknutie na bežca v prvom snímku (relatívne súradnice 0–1)
        'init_point': (px, py) if px is not None and py is not None and px < 1 and py < 1 else None,
        'phase': (request.form.get('phase') or 'auto').strip(),
        'discipline': (request.form.get('discipline') or '400mH').strip(),
    }


def _save_upload():
    """Uloží nahraté video. Vráti (Upload, None) alebo (None, JSON chyba)."""
    file = request.files.get('video')
    if not file or not file.filename:
        return None, (jsonify({'error': 'Nevybral si žiadne video.'}), 400)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXT:
        return None, (jsonify({'error': f'Formát {ext or "?"} nie je podporovaný. '
                                        f'Použi {", ".join(sorted(ALLOWED_VIDEO_EXT))}.'}), 400)
    job_id = uuid.uuid4().hex
    stored_name = f'{job_id}{ext}'
    path = os.path.join(video_dir(), stored_name)
    file.save(path)
    return Upload(job_id, path, stored_name, file.filename), None


def _target_athlete_id():
    """
    Komu analýza patrí: `athlete_id` z formulára (tréner vyberá zverenca), inak prihlásený.
    Vráti (id, None) alebo (None, JSON chyba) – cudzí zverenec sa odmietne, nie potichu nahradí.
    """
    raw = (request.form.get('athlete_id') or '').strip()
    if not raw:
        return g.user.id, None
    try:
        athlete_id = int(raw)
    except ValueError:
        return None, (jsonify({'error': 'Neplatný zverenec.'}), 400)
    if athlete_id not in athlete_ids_visible_to(g.user):
        return None, (jsonify({'error': 'Na tohto zverenca nemáš oprávnenie.'}), 403)
    if db.session.get(User, athlete_id) is None:
        return None, (jsonify({'error': 'Zverenec neexistuje.'}), 404)
    return athlete_id, None


def _remember_height(height_cm, user_id):
    """Zapamätá výšku v profile atléta, ktorého video sa analyzuje (nie nutne prihláseného)."""
    if height_cm and user_id:
        UserProfile.for_user(user_id, create=True).height_cm = height_cm
        db.session.commit()


def _visible_analysis(model, analysis_id):
    """(row, None) alebo (None, JSON chyba), ak analýza neexistuje alebo ju používateľ nesmie vidieť."""
    row = db.session.get(model, analysis_id)
    if not row:
        return None, (jsonify({'error': 'Analýza neexistuje.'}), 404)
    if not row_visible(row.user_id):
        return None, (jsonify({'error': 'Na túto analýzu nemáš oprávnenie.'}), 403)
    return row, None


def _page_context():
    """Údaje pre stránky Video a Prekážky: výška z profilu, výber zverenca pre trénera."""
    profile = UserProfile.for_user(g.user.id)
    ctx = {
        'default_height': profile.height_cm if profile and profile.height_cm else '',
        'athletes': None, 'athlete_heights': {}, 'owner_names': {},
        'groq_ok': groq_available(),
    }
    if g.user.is_coach or g.user.is_admin:
        athletes = visible_athletes(g.user)
        ctx['athletes'] = athletes
        # kľúče ako text – v šablóne ich číta JS podľa hodnoty <select>
        ctx['athlete_heights'] = {
            str(p.user_id): p.height_cm
            for p in UserProfile.query.filter(UserProfile.user_id.in_([a.id for a in athletes]))
            if p.height_cm
        }
        # mená vlastníkov k položkám histórie (admin vidí aj analýzy ľudí mimo výberu)
        people = User.query.all() if g.user.is_admin else athletes
        ctx['owner_names'] = {u.id: u.username for u in people}
    return ctx


def _delete_media(row):
    names = [row.stored_name, row.overlay_name]
    try:
        names += [k.get('file') for k in json.loads(row.result_json or '{}').get('keyframes') or []]
    except ValueError:
        pass
    for name in filter(None, names):
        try:
            os.remove(os.path.join(video_dir(), name))
        except OSError:
            pass


def _cleanup_failed(folder, video_path, overlay_path):
    """Po neúspešnej analýze nenechá na disku nahraté video ani rozpracované súbory."""
    for path in (video_path, overlay_path, (overlay_path + '.tmp.mp4') if overlay_path else None):
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
    stem = os.path.splitext(os.path.basename(video_path))[0]
    try:
        for name in os.listdir(folder):
            if name.startswith(stem + '_key'):
                os.remove(os.path.join(folder, name))
    except OSError:
        pass


def _run_job(app, kind, upload, opts):
    """Beží v samostatnom vlákne – analýza môže trvať desiatky sekúnd."""
    engine = _engine()
    folder = video_dir(app)
    stem = os.path.splitext(upload.stored_name)[0]
    overlay_path = os.path.join(folder, stem + '_overlay.mp4') if opts['make_overlay'] else None

    def progress(fraction, message):
        _job_set(upload.job_id, state='running', progress=round(fraction * 100), message=message)

    try:
        result = KINDS[kind]['run'](upload.path, opts, overlay_path=overlay_path, progress_cb=progress,
                                    keyframes_dir=folder, keyframes_prefix=stem)
        with app.app_context():
            row = KINDS[kind]['model'](
                user_id=opts['athlete_id'],
                original_name=upload.original_name,
                stored_name=upload.stored_name,
                overlay_name=os.path.basename(overlay_path) if overlay_path and result.get('overlay_path') else None,
                label=opts['label'] or None,
                fps=result['video']['fps'],
                duration_s=result['video']['duration_s'],
                athlete_height_cm=opts['height_cm'],
                result_json=json.dumps(result, ensure_ascii=False),
                **KINDS[kind]['columns'](result),
            )
            db.session.add(row)
            db.session.commit()
            result['analysis_id'] = row.id
        _attach_urls(result)
        _job_set(upload.job_id, state='done', progress=100, message='Hotovo',
                 analysis_id=result['analysis_id'], result=result)
    except engine.VideoAnalysisError as e:            # zlé video, žiadny bežec v zábere…
        _job_set(upload.job_id, state='error', message=str(e))
        _cleanup_failed(folder, upload.path, overlay_path)
    except Exception as e:
        app.logger.exception('Analýza videa %s zlyhala', upload.job_id)
        _job_set(upload.job_id, state='error', message=f'Neočakávaná chyba pri analýze: {e}')
        _cleanup_failed(folder, upload.path, overlay_path)


# ---------------------------------------------------------------------------
# Stránky
# ---------------------------------------------------------------------------
def _page(kind):
    ok, deps_msg = _engine().dependencies_ok()
    model = KINDS[kind]['model']
    history = scope_query(model.query, model).order_by(model.created_at.desc()).limit(HISTORY_LIMIT).all()
    return render_template(KINDS[kind]['template'], deps_ok=ok, deps_msg=deps_msg, history=history,
                           **_page_context())


@bp.route('/video')
@login_required
def video_page():
    return _page('sprint')


@bp.route('/prekazky')
@login_required
def hurdles_page():
    return _page('hurdles')


@bp.route('/media/<path:name>')
@login_required
def media_file(name):
    """Video, prekryv aj snímky vidí len ten, kto smie vidieť samotnú analýzu."""
    safe = os.path.basename(name)
    if not safe or safe != name:
        abort(404)
    # všetky súbory jednej analýzy zdieľajú prefix job_id: <id>.mp4, <id>_overlay.mp4, <id>_kf01.jpg
    key = safe.split('_')[0].split('.')[0]
    if not re.fullmatch(r'[0-9a-f]{32}', key):
        abort(404)
    row = None
    for model in (VideoAnalysis, HurdleAnalysis):
        row = model.query.filter(model.stored_name.like(f'{key}.%')).first()
        if row is not None:
            break
    if row is None:
        abort(404)
    if not row_visible(row.user_id):
        abort(403)
    return send_from_directory(video_dir(), safe, conditional=True)


# ---------------------------------------------------------------------------
# API (volá JavaScript stránok Video a Prekážky – cesty sú pevné v šablónach)
# ---------------------------------------------------------------------------
@bp.route('/api/video/analyze', methods=['POST'], endpoint='video_analyze', defaults={'kind': 'sprint'})
@bp.route('/api/hurdles/analyze', methods=['POST'], endpoint='hurdles_analyze', defaults={'kind': 'hurdles'})
@login_required
def analyze(kind):
    engine = _engine()
    ok, deps_msg = engine.dependencies_ok()
    if not ok:
        return jsonify({'error': deps_msg}), 500
    # vlastník analýzy sa overí ešte pred uložením súboru na disk
    athlete_id, error = _target_athlete_id()
    if error:
        return error
    upload, error = _save_upload()
    if error:
        return error
    opts = _parse_upload_form()
    opts['athlete_id'] = athlete_id
    _remember_height(opts['height_cm'], athlete_id)
    try:
        info = engine.probe_video(upload.path)
    except engine.VideoAnalysisError as e:
        os.remove(upload.path)
        return jsonify({'error': str(e)}), 400

    _job_set(upload.job_id, state='queued', progress=0, message='Čakám na spracovanie',
             video_info=info, user_id=athlete_id)
    threading.Thread(target=_run_job, daemon=True,
                     args=(current_app._get_current_object(), kind, upload, opts)).start()
    return jsonify({'job_id': upload.job_id, 'video_info': info})


@bp.route('/api/video/job/<job_id>')
@login_required
def job_status(job_id):
    job = _job_get(job_id)
    if not job:
        return jsonify({'error': 'Úloha neexistuje (server bol pravdepodobne reštartovaný).'}), 404
    if not row_visible(job.get('user_id')):
        return jsonify({'error': 'Na túto úlohu nemáš oprávnenie.'}), 403
    return jsonify(job)


@bp.route('/api/video/result/<int:analysis_id>', endpoint='video_result', defaults={'kind': 'sprint'})
@bp.route('/api/hurdles/result/<int:analysis_id>', endpoint='hurdles_result', defaults={'kind': 'hurdles'})
@login_required
def result(kind, analysis_id):
    row, error = _visible_analysis(KINDS[kind]['model'], analysis_id)
    if error:
        return error
    data = _attach_urls(json.loads(row.result_json or '{}'))
    data.update(overlay_url=_video_url(row.overlay_name), analysis_id=row.id, label=row.label,
                created_at=row.created_at.strftime('%d.%m.%Y %H:%M'))
    return jsonify(data)


@bp.route('/api/video/delete/<int:analysis_id>', methods=['POST'], endpoint='video_delete',
          defaults={'kind': 'sprint'})
@bp.route('/api/hurdles/delete/<int:analysis_id>', methods=['POST'], endpoint='hurdles_delete',
          defaults={'kind': 'hurdles'})
@login_required
def delete(kind, analysis_id):
    row, error = _visible_analysis(KINDS[kind]['model'], analysis_id)
    if error:
        return error
    _delete_media(row)
    db.session.delete(row)
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# AI tréner – komentár k nameranej technike
# ---------------------------------------------------------------------------
COACH_SYSTEM_PROMPT = """Si skúsený atletický tréner šprintu a prekážkového behu. Dostaneš výsledky
automatickej analýzy techniky z videa (čísla + vyhodnotenie podľa pravidiel). Napíš atlétovi krátky,
konkrétny komentár v slovenčine (tykaj mu):

1. Dve-tri vety, čo je na technike dobré.
2. Najviac 3 najdôležitejšie veci, ktoré zlepšiť – pri každej: čo vidíš v číslach, prečo to
   spomaľuje a 1–2 konkrétne cvičenia alebo pokyny do tréningu.
3. Jedna veta, na čo sa zamerať v ďalšom videu.

Pravidlá: opieraj sa výhradne o dodané čísla, nič si nevymýšľaj. Ak je video pod 100 fps alebo sú
v upozorneniach pochybnosti o kvalite, povedz, že časové údaje sú orientačné. Uhly platia len pri
zábere presne z boku. Buď stručný (do 250 slov), bez nadpisov, môžeš použiť odrážky.
Nie si lekár: nedávaj diagnózy. Ak čísla (napr. opakovaná asymetria) naznačujú možné zranenie
alebo atlét spomína bolesť, odporuč fyzioterapeuta alebo lekára a nerob zdravotné závery."""

SPRINT_SUMMARY_FIELDS = (
    ('contact_ms_mean', 'kontakt so zemou (ms)'), ('contact_ms_sd', 'rozptyl kontaktu (ms)'),
    ('flight_ms_mean', 'letová fáza (ms)'), ('cadence_spm', 'frekvencia (krokov/min)'),
    ('step_length_m', 'dĺžka kroku (m)'), ('step_length_height_ratio', 'dĺžka kroku / výška'),
    ('speed_ms', 'rýchlosť (m/s)'), ('duty_factor_pct', 'duty factor (%)'),
    ('asymmetry_pct', 'asymetria Ľ/P (%)'), ('vertical_oscillation_cm', 'vertikálna oscilácia (cm)'),
)
HURDLE_SUMMARY_FIELDS = (
    ('interval_mean_s', 'priemerný medzičas medzi prekážkami (s)'), ('interval_sd_s', 'rozptyl medzičasov (s)'),
    ('interval_trend_pct', 'zmena medzičasu prvý→posledný (%)'), ('steps_pattern_text', 'kroky medzi prekážkami'),
    ('speed_between_ms_mean', 'rýchlosť medzi prekážkami (m/s)'),
)


def _mean_angle(steps, key, phase):
    values = [(st.get(phase) or {}).get(key) for st in steps]
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def coach_context(kind, data):
    """Textový súhrn merania pre AI trénera."""
    v = data.get('video') or {}
    s = data.get('summary') or {}
    lines = [f"Video: {v.get('fps')} fps, {v.get('duration_s')} s, kostra rozpoznaná na "
             f"{round((v.get('detected_ratio') or 0) * 100)} % snímok."]
    if kind == 'sprint':
        lines.append('Typ: šprint, fáza: ' + str((data.get('technique') or {}).get('phase_text')))
        lines += [f'- {label}: {s[key]}' for key, label in SPRINT_SUMMARY_FIELDS if s.get(key) is not None]
        steps = data.get('steps') or []
        if steps:
            td, to = 'angles_touchdown', 'angles_toeoff'
            lines.append(f"- priemerné uhly pri dopade: koleno {_mean_angle(steps, 'knee_deg', td)}°, "
                         f"trup {_mean_angle(steps, 'trunk_lean_deg', td)}°, "
                         f"holeň {_mean_angle(steps, 'shank_deg', td)}° (+ = koleno pred členkom)")
            lines.append(f"- priemerné uhly pri odraze: koleno {_mean_angle(steps, 'knee_deg', to)}°, "
                         f"stehno {_mean_angle(steps, 'thigh_deg', to)}° (- = koleno za bedrom)")
    else:
        lines.append(f"Typ: prekážky ({s.get('discipline_label')}), prekážok v zábere: {s.get('hurdles_detected')}. "
                     'Hodnotí sa len rytmus: medzičasy medzi prekážkami (dopad → dopad), počet krokov medzi '
                     'prekážkami a odrazová noha.')
        lines += [f'- {label}: {s[key]}' for key, label in HURDLE_SUMMARY_FIELDS if s.get(key) is not None]
        rel = data.get('reliability') or {}
        if rel.get('level') in ('low', 'unusable'):
            lines.append('POZOR: výsledok je ' + ('nepoužiteľný' if rel['level'] == 'unusable' else 'nespoľahlivý')
                         + ' (' + '; '.join(rel.get('reasons') or []) + '). Neúplné úseky nehodnoť.')
        for iv in data.get('intervals') or []:
            if iv.get('valid', True):
                steps = (f"{iv['steps_between']} krokov" if iv.get('steps_between') is not None
                         else 'počet krokov neistý')
                speed = f", rýchlosť {iv.get('speed_ms')} m/s" if iv.get('speed_ms') else ''
                text = f"medzičas {iv.get('interval_s')} s, {steps}{speed}"
            else:
                text = f"neúplný záznam ({iv.get('invalid_reason')})"
            lines.append(f"- úsek P{iv['from_hurdle']}→P{iv['to_hurdle']}: {text}")
        for h in data.get('hurdles') or []:
            lines.append(f"- prekážka {h['index']}: odraz z {h.get('takeoff_side_text')} nohy, "
                         f"dopad za prekážkou v čase {h.get('landing_s')} s videa")
    findings = (data.get('technique') or {}).get('findings') or []
    if findings:
        lines.append('Vyhodnotenie podľa pravidiel:')
        lines += [f"- [{f['status']}] {f['label']}: {f['value_text']} (referencia {f['reference']}) – {f['text']}"
                  for f in findings]
    if data.get('warnings'):
        lines.append('Upozornenia k meraniu: ' + ' | '.join(data['warnings']))
    return '\n'.join(lines)


@bp.route('/api/coach/<kind>/<int:analysis_id>', methods=['POST'])
@login_required
def coach_comment(kind, analysis_id):
    if kind not in KINDS:
        return jsonify({'error': 'Neznámy typ analýzy.'}), 400
    row, error = _visible_analysis(KINDS[kind]['model'], analysis_id)
    if error:
        return error
    data = json.loads(row.result_json or '{}')

    # profil patrí atlétovi z videa (tréner môže žiadať komentár k zverencovi), nie prihlásenému
    profile = UserProfile.for_user(row.user_id)
    about = profile.summary_for_ai() if profile else ''
    context = (f'Atlét: {about}\n' if about else '') + coach_context(kind, data)
    messages = [
        {'role': 'system', 'content': COACH_SYSTEM_PROMPT},
        {'role': 'user', 'content': 'Toto sú výsledky merania:\n\n' + context +
                                    '\n\nNapíš mi komentár k technike a čo mám zlepšiť.'},
    ]
    try:
        reply, model = groq_complete(messages)
    except AIError as e:
        return jsonify({'error': str(e)}), e.status

    # komentár sa uloží k výsledku, aby sa nemusel generovať znova
    data['coach_comment'] = reply
    data['coach_model'] = model
    row.result_json = json.dumps(data, ensure_ascii=False)
    db.session.commit()
    return jsonify({'reply': reply, 'model': model})
