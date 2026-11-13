"""
AtletCoach – vstupný bod aplikácie.

Tu sa vytvára Flask appka: konfigurácia, databáza (+ jednoduchá migrácia stĺpcov), prvý admin,
domovská stránka a registrácia blueprintov. Každá časť appky má vlastný modul:

    auth.py          prihlásenie, registrácia, role a viditeľnosť údajov
    trener.py        zverenci a ich výsledky          zverenec.py   výsledky a tréner zverenca
    planovanie.py    kalendár a týždenný plán         grafy.py      grafy výkonnosti
    analyza.py       analýza videa a prekážok         stopky.py     stopky s fotobunkou
    dennik.py        tréningový denník, HRV           ai_trener.py  AI chat a profil (Groq)
    strava.py        prepojenie so Stravou            world_athletics.py  import výsledkov
    admin_panel.py   správa účtov                     pravne.py     ochrana údajov, podmienky, cookies
    navigacia.py     počty do menu                    formaty.py    slovenské dátumy v šablónach

Moduly importujú len models/auth (a navzájom seba), nikdy app.py – inak by vznikol kruhový import.
"""
import mimetypes
import os
import secrets
import threading
import time
import webbrowser
from datetime import date, timedelta

from flask import Flask, render_template, session, g
from dotenv import load_dotenv

from models import (db, User, RaceResult, PlannedTraining, BiometricLog, TrainingLog, VideoAnalysis,
                    LEGACY_USER_TABLES)
from trener import personal_bests, results_for

load_dotenv()

# Manifest webovej appky musí ísť s vlastným typom, inak ho prehliadač ignoruje.
mimetypes.add_type('application/manifest+json', '.webmanifest')

app = Flask(__name__)
os.makedirs(app.instance_path, exist_ok=True)


def _secret_key():
    """
    Tajný kľúč podpisuje session cookie (prihlásenie). Pevný reťazec v kóde by znamenal,
    že si ktokoľvek s prístupom k repozitáru vie vyrobiť cookie admina – preto sa
    kľúč berie z .env, alebo sa raz vygeneruje a uloží do instance/secret_key.
    """
    key = os.getenv('SECRET_KEY')
    if key:
        return key
    path = os.path.join(app.instance_path, 'secret_key')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            key = f.read().strip()
        if key:
            return key
    except OSError:
        pass
    key = secrets.token_hex(32)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


app.config['SECRET_KEY'] = _secret_key()
# Cestu k DB možno prepísať (testy, dočasná inštancia); predvolene instance/database.db
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('ATLETCOACH_DB_URI', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Session sa vymaže keď zatvoríš prehliadač (nie permanent cookie)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = 600 * 1024 * 1024   # najväčšie nahrávané video: 600 MB

db.init_app(app)


@app.before_request
def make_session_non_permanent():
    session.permanent = False


# -----------------------------
# Init
# Modely sú v models.py (importujú ich aj blueprinty). Tu ostáva migrácia
# existujúcej databázy a prvotné vytvorenie admina.
# -----------------------------
def _ensure_columns():
    """
    Jednoduchá migrácia: db.create_all() vie vytvoriť novú tabuľku, ale
    nevie pridať stĺpec do už existujúcej.  Toto doplní chýbajúce stĺpce,
    takže existujúca database.db zostane funkčná aj po aktualizácii.

    SQLite: pridávajú sa obyčajné NULL-ové stĺpce bez FK constraintu (ALTER TABLE
    ho aj tak nevynúti, vzťah drží ORM). Každý ALTER beží zvlášť, aby jedna chyba
    nenechala chýbať ostatné stĺpce. Ak po prejdení niečo stále chýba, appka radšej
    nenaštartuje, než aby padala na každom dotaze s 'no such column'.
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    wanted = {'user_profile': [('height_cm', 'FLOAT')],
              'user': [('coach_confirmed', 'BOOLEAN NOT NULL DEFAULT 0'),
                       ('group_name', 'VARCHAR(60)'), ('nickname', 'VARCHAR(60)'),
                       ('terms_accepted_at', 'DATETIME')],
              'planned_training': [('batch_id', 'VARCHAR(36)'), ('time_text', 'VARCHAR(5)')]}
    for table in LEGACY_USER_TABLES:
        wanted.setdefault(table, []).append(('user_id', 'INTEGER'))

    tables = set(inspector.get_table_names())
    for table, cols in wanted.items():
        if table not in tables:
            continue
        existing = {c['name'] for c in inspector.get_columns(table)}
        for name, sql_type in cols:
            if name in existing:
                continue
            try:
                db.session.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {name} {sql_type}'))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f'Upozornenie: nepodarilo sa pridať stĺpec {table}.{name}: {e}')
            if name == 'user_id':
                try:
                    db.session.execute(text(
                        f'CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON "{table}" (user_id)'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

    # Kontrola: po migrácii musí každý žiadaný stĺpec existovať.
    inspector = inspect(db.engine)
    missing = []
    for table, cols in wanted.items():
        if table not in tables:
            continue
        existing = {c['name'] for c in inspector.get_columns(table)}
        missing += [f'{table}.{name}' for name, _ in cols if name not in existing]
    if missing:
        raise RuntimeError('Migrácia databázy zlyhala, chýbajú stĺpce: ' + ', '.join(missing))


def _seed_admin():
    """Prvé spustenie: bez jediného účtu by sa nedalo prihlásiť – vytvorí sa admin/admin."""
    if User.query.count() > 0:
        return
    admin = User(username='admin', role='admin', full_name='Administrátor',
                 must_change_password=True)
    admin.set_password('admin')
    db.session.add(admin)
    db.session.commit()
    print('\n' + '=' * 64)
    print('  PRVÉ SPUSTENIE: vytvorený účet administrátora')
    print('  prihlasovacie meno: admin      heslo: admin')
    print('  Po prihlásení si heslo hneď zmeň (appka to vyžiada).')
    print('=' * 64 + '\n')


with app.app_context():
    db.create_all()
    _ensure_columns()
    try:
        _seed_admin()
    except Exception as _e:
        db.session.rollback()
        print('Upozornenie: nepodarilo sa vytvoriť predvoleného admina:', _e)


# ---------------------------------------------------------------------------
# Domovská stránka: úvod pre hosťa, prehľad pre trénera, osobný prehľad pre zverenca
# ---------------------------------------------------------------------------
def _coach_dashboard():
    """Prehľad pre trénera/admina: zverenci a ich týždeň, splnenie za 28 dní, posledné výsledky s PB."""
    if g.user.is_admin:
        athletes = User.query.filter_by(role='zverenec').order_by(User.full_name, User.username).all()
    else:
        # Len potvrdení zverenci – čakajúca žiadosť nesmie prezradiť ani jeden výsledok.
        athletes = User.query.filter_by(coach_id=g.user.id, coach_confirmed=True) \
            .order_by(User.full_name, User.username).all()
    athlete_ids = [a.id for a in athletes]

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    week = {aid: {'done': 0, 'planned': 0} for aid in athlete_ids}
    completion_pct = None
    completed_count = due_count = 0
    last_results = []
    last_result_by_athlete = {}
    pb_ids = set()
    if athlete_ids:
        for plan in PlannedTraining.query.filter(
                PlannedTraining.athlete_id.in_(athlete_ids),
                PlannedTraining.date >= week_start, PlannedTraining.date <= week_end):
            week[plan.athlete_id]['planned'] += 1
            week[plan.athlete_id]['done'] += int(bool(plan.completed))
        # Splnenie sa počíta len z tréningov, ktorých termín už uplynul (posledných 28 dní).
        due = PlannedTraining.query.filter(
            PlannedTraining.athlete_id.in_(athlete_ids),
            PlannedTraining.date >= today - timedelta(days=28),
            PlannedTraining.date <= today).all()
        due_count = len(due)
        completed_count = sum(1 for p in due if p.completed)
        if due_count:
            completion_pct = round(100 * completed_count / due_count)
        results = RaceResult.query.filter(RaceResult.user_id.in_(athlete_ids)) \
            .order_by(RaceResult.date.desc(), RaceResult.id.desc()).all()
        last_results = results[:6]
        best = {}
        for r in results:
            last_result_by_athlete.setdefault(r.user_id, r)
            key = (r.user_id, r.discipline)
            if key not in best or r.result_s < best[key].result_s:
                best[key] = r
        pb_ids = {r.id for r in best.values()}

    week_planned = sum(w['planned'] for w in week.values())
    week_done = sum(w['done'] for w in week.values())
    return render_template(
        'trener/dashboard.html',
        athletes=athletes, week=week, week_planned=week_planned, week_done=week_done,
        today=today, week_start=week_start, week_end=week_end,
        completion_pct=completion_pct, completed_count=completed_count, due_count=due_count,
        last_results=last_results, last_result_by_athlete=last_result_by_athlete, pb_ids=pb_ids,
    )


@app.route('/')
def index():
    # Neprihlásený: úvodná stránka. Tréner/admin: prehľad zverencov. Zverenec: osobný dashboard.
    if g.user is None:
        return render_template('landing.html')
    if g.user.is_coach or g.user.is_admin:
        return _coach_dashboard()

    return _athlete_home()


def _athlete_home():
    """Osobný prehľad zverenca: týždeň z plánu, regenerácia, kilometre, posledné video, osobné rekordy."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    recent_logs = BiometricLog.query.filter_by(user_id=g.user.id) \
        .order_by(BiometricLog.date.desc()).limit(14).all()
    last = recent_logs[0] if recent_logs else None
    hrvs = [l.hrv for l in recent_logs[:7] if l.hrv is not None]
    trainings_week = TrainingLog.query.filter(TrainingLog.user_id == g.user.id,
                                              TrainingLog.date >= today - timedelta(days=6)).all()
    week_plans = PlannedTraining.query.filter(
        PlannedTraining.athlete_id == g.user.id,
        PlannedTraining.date >= monday, PlannedTraining.date <= monday + timedelta(days=6)) \
        .order_by(PlannedTraining.date, PlannedTraining.time_text, PlannedTraining.id).all()

    return render_template(
        'index.html',
        today=today,
        weekly_km=round(sum(t.distance_km or 0.0 for t in trainings_week), 1),
        last_hrv=last.hrv if last else None,
        avg_hrv_7=round(sum(hrvs) / len(hrvs), 1) if hrvs else None,
        last_recovery=last.recovery if last else None,
        last_rhr=last.rhr if last else None,
        recent_logs=recent_logs[:5],
        week_plans=week_plans,
        pbs=personal_bests(results_for(g.user.id)),
        last_video=VideoAnalysis.query.filter_by(user_id=g.user.id)
                                      .order_by(VideoAnalysis.created_at.desc()).first(),
        strava_logged_in=bool(session.get('strava_access_token')),
    )


# ===========================================================================
# BLUEPRINTY – registrujú sa až keď `app` existuje.
# ===========================================================================
import auth, trener, zverenec, planovanie, grafy, stopky, admin_panel, world_athletics, pravne  # noqa: E402,E401
import analyza, dennik, ai_trener, strava  # noqa: E402,E401
for _module in (auth, trener, zverenec, planovanie, grafy, stopky, admin_panel, world_athletics, pravne,
                analyza, dennik, ai_trener, strava):
    app.register_blueprint(_module.bp)

import navigacia, formaty  # noqa: E402,E401
navigacia.init_app(app)   # počty do bočného menu (zverenci, žiadosti, tréningy týždňa)
formaty.init_app(app)     # slovenské dátumy v šablónach (den_mesiac, rozsah_dni, tyzden)


if __name__ == '__main__':
    port = int(os.getenv('ATLETCOACH_PORT', '5001'))
    # Predvolene počúva len na tomto počítači; ATLETCOACH_HOST=0.0.0.0 ho otvorí pre telefón v tej istej sieti.
    host = os.getenv('ATLETCOACH_HOST', '127.0.0.1')
    # Reloader a debug sa dajú vypnúť (ATLETCOACH_RELOAD=0, FLASK_DEBUG=0) – skripty, nasadenie
    use_reloader = os.getenv('ATLETCOACH_RELOAD', '1') == '1'
    debug = os.getenv('FLASK_DEBUG', '1') == '1'
    # Otvor prehliadač iba raz (v child procese reloadera, nie v parent procese)
    if (os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not use_reloader) \
            and os.getenv('ATLETCOACH_NO_BROWSER') != '1':
        def _open_browser():
            time.sleep(1.5)
            webbrowser.open(f'http://127.0.0.1:{port}')
        threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host=host, debug=debug, port=port, use_reloader=use_reloader)
