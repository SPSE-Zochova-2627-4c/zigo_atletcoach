# -*- coding: utf-8 -*-
"""
Integračné testy AtletCoach cez Flask test client (pytest, bez siete a bez prehliadača).

    python -m pytest -q test_app.py

Appka beží na dočasnej databáze. Testy overujú, že sa každá stránka vykreslí pre každú rolu,
že platia pravidlá prístupu (zverenec vidí len seba, tréner len potvrdených zverencov),
validáciu vstupov a čisté funkcie (pripravenosť, import WHOOP, Strava, dátumy).
"""
import io
import os
import re
import tempfile
import time
from datetime import date, timedelta

# Prostredie sa nastaví ešte pred importom appky: dočasná DB, žiadny prehliadač, žiadny AI kľúč
_TMP = tempfile.mkdtemp(prefix='atletcoach-test-')
os.environ['ATLETCOACH_DB_URI'] = 'sqlite:///' + os.path.join(_TMP, 'test.db')
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['ATLETCOACH_NO_BROWSER'] = '1'
os.environ['GROQ_API_KEY'] = ''          # load_dotenv neprepíše existujúcu premennú → AI je vypnuté
os.environ['STRAVA_CLIENT_ID'] = ''

import pytest  # noqa: E402

from app import app  # noqa: E402
from models import (utcnow, db, User, UserProfile, RaceResult, PlannedTraining, BiometricLog,  # noqa: E402
                    VideoAnalysis, HurdleAnalysis)
import analyza  # noqa: E402
import dennik  # noqa: E402
import formaty  # noqa: E402
import strava  # noqa: E402

PASSWORD = 'heslo-na-test-123'


def _user(username, role, **kw):
    u = User(username=username, role=role, full_name=kw.pop('full_name', username.title()),
             terms_accepted_at=utcnow(), **kw)
    u.set_password(PASSWORD)
    db.session.add(u)
    db.session.flush()
    return u


@pytest.fixture(scope='module')
def people():
    """Dvaja tréneri, každý so svojím zverencom, čakajúca žiadosť a administrátor."""
    with app.app_context():
        boss = _user('riaditel', 'admin')
        coach = _user('trener1', 'trener', full_name='Peter Kováč')
        other_coach = _user('trener2', 'trener')
        athlete = _user('zverenec1', 'zverenec', full_name='Matej Novák', coach_id=coach.id, coach_confirmed=True)
        foreign = _user('cudzi', 'zverenec', coach_id=other_coach.id, coach_confirmed=True)
        pending = _user('caka', 'zverenec', coach_id=coach.id, coach_confirmed=False)
        today = date.today()
        db.session.add_all([
            RaceResult(user_id=athlete.id, discipline='400 m', result_s=48.31, date=today - timedelta(days=10),
                       competition='M-SR', source='manual'),
            RaceResult(user_id=athlete.id, discipline='400 m', result_s=48.90, date=today - timedelta(days=3),
                       competition='Mítink', source='manual'),
            RaceResult(user_id=foreign.id, discipline='100 m', result_s=11.02, date=today, source='manual'),
            PlannedTraining(athlete_id=athlete.id, coach_id=coach.id, date=today, title='Tempo 6x200 m'),
            VideoAnalysis(user_id=foreign.id, original_name='x.mp4', stored_name='a' * 32 + '.mp4',
                          result_json='{}'),
            HurdleAnalysis(user_id=athlete.id, original_name='p.mp4', stored_name='b' * 32 + '.mp4',
                           result_json='{}'),
        ])
        db.session.commit()
        ids = {u.username: u.id for u in (boss, coach, other_coach, athlete, foreign, pending)}
        ids['foreign_video'] = VideoAnalysis.query.filter_by(user_id=foreign.id).first().id
        ids['athlete_hurdles'] = HurdleAnalysis.query.filter_by(user_id=athlete.id).first().id
        return ids


def login(username):
    client = app.test_client()
    resp = client.post('/prihlasenie', data={'username': username, 'password': PASSWORD})
    assert resp.status_code == 302, f'prihlásenie {username} zlyhalo'
    return client


def assert_page(client, path, status=200):
    resp = client.get(path)
    assert resp.status_code == status, f'{path}: čakal som {status}, prišlo {resp.status_code}'
    return resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Stránky sa vykreslia pre každú rolu (zachytí aj chybné url_for v šablónach)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('path', ['/', '/stopky/', '/prihlasenie', '/registracia',
                                  '/ochrana-udajov', '/podmienky', '/cookies'])
def test_public_pages(path, people):
    html = assert_page(app.test_client(), path)
    assert 'AtletCoach' in html


def test_unknown_page_is_404(people):
    html = assert_page(app.test_client(), '/neexistuje', 404)
    assert 'Domov' in html or 'domov' in html


@pytest.mark.parametrize('path', ['/video', '/prekazky', '/plan/', '/trainings', '/log', '/ai', '/grafy/',
                                  '/trener/zverenci'])
def test_guest_is_sent_to_login(path, people):
    resp = app.test_client().get(path)
    assert resp.status_code == 302 and '/prihlasenie' in resp.headers['Location']


COACH_PAGES = ['/', '/trener/zverenci', '/plan/', '/plan/prehlad', '/plan/tyzden', '/grafy/', '/video',
               '/prekazky', '/stopky/', '/trainings', '/ai', '/profile', '/log', '/zmena-hesla']
ATHLETE_PAGES = ['/', '/plan/', '/trainings', '/zverenec/vysledky', '/grafy/', '/log', '/video', '/prekazky',
                 '/stopky/', '/ai', '/profile']
ADMIN_PAGES = ['/', '/admin/pouzivatelia', '/admin/prehlad', '/trener/zverenci', '/video']


@pytest.mark.parametrize('path', COACH_PAGES)
def test_coach_pages(path, people):
    assert_page(login('trener1'), path)


def test_coach_athlete_detail(people):
    html = assert_page(login('trener1'), f"/trener/zverenci/{people['zverenec1']}")
    assert '48.31' in html


@pytest.mark.parametrize('path', ATHLETE_PAGES)
def test_athlete_pages(path, people):
    assert_page(login('zverenec1'), path)


@pytest.mark.parametrize('path', ADMIN_PAGES)
def test_admin_pages(path, people):
    assert_page(login('riaditel'), path)


def test_coach_dashboard_marks_personal_best(people):
    html = assert_page(login('trener1'), '/')
    assert 'Matej Novák' in html
    # 48.31 je osobák (PB), 48.90 nie
    assert re.search(r'48\.31</span><span class="pb"', html)
    assert not re.search(r'48\.90</span><span class="pb"', html)
    # čakajúca žiadosť ani cudzí zverenec sa v prehľade neukážu
    assert 'Caka' not in html and 'Cudzi' not in html


# ---------------------------------------------------------------------------
# Prístup k údajom
# ---------------------------------------------------------------------------
def test_athlete_cannot_open_coach_pages(people):
    assert_page(login('zverenec1'), '/trener/zverenci', 403)
    assert_page(login('zverenec1'), '/admin/pouzivatelia', 403)


def test_coach_cannot_open_foreign_athlete(people):
    resp = login('trener1').get(f"/trener/zverenci/{people['cudzi']}")
    assert resp.status_code in (403, 404)


def test_coach_cannot_open_pending_athlete(people):
    resp = login('trener1').get(f"/trener/zverenci/{people['caka']}")
    assert resp.status_code in (403, 404)


def test_analysis_of_someone_else_is_forbidden(people):
    resp = login('trener1').get(f"/api/video/result/{people['foreign_video']}")
    assert resp.status_code == 403
    resp = login('trener2').get(f"/api/hurdles/result/{people['athlete_hurdles']}")
    assert resp.status_code == 403
    # vlastný tréner analýzu zverenca vidí
    resp = login('trener1').get(f"/api/hurdles/result/{people['athlete_hurdles']}")
    assert resp.status_code == 200 and resp.get_json()['analysis_id'] == people['athlete_hurdles']


@pytest.mark.parametrize('name', ['..%2Fapp.py', 'app.py', 'nie-je-hex.mp4', 'c' * 32 + '.mp4'])
def test_media_rejects_unknown_files(name, people):
    resp = login('riaditel').get('/media/' + name)
    assert resp.status_code == 404


def test_media_of_foreign_analysis_is_forbidden(people):
    resp = login('trener1').get('/media/' + 'a' * 32 + '.mp4')
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Regenerácia: súhlas, validácia, pripravenosť
# ---------------------------------------------------------------------------
def _biometrics(username):
    with app.app_context():
        return BiometricLog.query.filter_by(user_id=User.query.filter_by(username=username).one().id).count()


def test_log_needs_health_consent_and_valid_values(people):
    client = login('zverenec1')
    before = _biometrics('zverenec1')
    client.post('/log', data={'hrv': '70'})                                       # bez súhlasu
    client.post('/log', data={'hrv': '900', 'health_consent': '1'})               # HRV mimo rozsahu
    client.post('/log', data={'hrv': '70', 'rhr': '5', 'health_consent': '1'})    # tep mimo rozsahu
    assert _biometrics('zverenec1') == before
    client.post('/log', data={'hrv': '70', 'recovery': '80', 'rhr': '48', 'health_consent': '1'})
    assert _biometrics('zverenec1') == before + 1


def test_readiness_without_data_is_empty_state(people):
    resp = login('trener2').get('/api/readiness')
    assert resp.status_code == 200 and resp.get_json()['empty'] is True


def test_readiness_with_data(people):
    client = login('zverenec1')
    client.post('/log', data={'hrv': '72', 'recovery': '90', 'health_consent': '1'})
    data = client.get('/api/readiness').get_json()
    assert 0 <= data['readiness'] <= 100 and data['label']


def test_readiness_score():
    assert dennik.readiness_score(70, 70, 100) == 70      # HRV na priemere (30) + regenerácia 100 % (40)
    assert dennik.readiness_score(70, 70) == 50           # bez regenerácie: 30 / 60 bodov
    assert dennik.readiness_score(140, 70, 100) == 100    # pomer sa oreže na 1,5
    assert dennik.readiness_score(10, 70, 0) == 0


def test_whoop_csv():
    content = ('WHOOP export\n'
               'Cycle start time,Heart rate variability (ms),Recovery score %,Resting heart rate (bpm)\n'
               '2026-10-01 06:00:00,"65,5",82,48\n'
               '2026-10-02 06:10:00,700,90,47\n'          # HRV mimo rozsahu → preskočiť
               '02.10.2026,61,150,300\n'                  # zlé recovery a RHR sa len vynechajú
               'zly datum,60,50,50\n')
    rows, skipped, columns = dennik.parse_whoop_csv(content)
    assert [r['hrv'] for r in rows] == [65.5, 61.0]
    assert rows[0] == {'date': date(2026, 10, 1), 'hrv': 65.5, 'recovery': 82, 'rhr': 48}
    assert rows[1]['recovery'] is None and rows[1]['rhr'] is None
    assert skipped == 2 and columns[0] == 'Cycle start time'


def test_trainings_require_type(people):
    client = login('zverenec1')
    resp = client.post('/trainings', data={'training_type': ''}, follow_redirects=True)
    assert 'Vyber alebo napíš typ tréningu' in resp.get_data(as_text=True)
    resp = client.post('/trainings', data={'training_type': 'Tempo', 'distance_km': '6.2'}, follow_redirects=True)
    assert 'Tréning uložený' in resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# AI a Strava bez konfigurácie
# ---------------------------------------------------------------------------
def test_ai_chat_without_key_explains_setup(people):
    resp = login('zverenec1').post('/api/chat', json={'message': 'Ako som na tom?'})
    assert resp.status_code == 503 and 'GROQ_API_KEY' in resp.get_json()['error']
    resp = login('zverenec1').post('/api/chat', json={'message': '   '})
    assert resp.status_code == 400


def test_strava_pages_without_connection(people):
    client = login('zverenec1')
    assert client.get('/dashboard').status_code == 302
    assert client.get('/osobaky').status_code == 302
    resp = client.get('/api/heatmap-data')
    assert resp.status_code == 401 and resp.get_json()['error']
    resp = client.get('/strava/login', headers={'Referer': 'http://localhost/'})
    assert resp.status_code == 302          # bez kľúčov presmeruje späť s vysvetlením


def test_strava_helpers():
    # príklad z dokumentácie Google Encoded Polyline
    assert strava.decode_polyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@') == [[38.5, -120.2], [40.7, -120.95],
                                                                     [43.252, -126.453]]
    assert strava.pace_from_speed(4.0) == '4:10 /km'
    assert strava.seconds_to_time(3725) == '1:02:05' and strava.seconds_to_time(95) == '1:35'
    assert strava.pace_str(1200, 5) == '4:00' and strava.pace_str(0, 5) == '—'


def test_slovak_dates():
    assert formaty.den_mesiac(date(2026, 11, 4)) == '4. novembra'
    assert formaty.rozsah_dni((date(2026, 11, 2), date(2026, 11, 8))) == '2. – 8. novembra'
    assert formaty.rozsah_dni((date(2026, 10, 26), date(2026, 11, 1))) == '26. októbra – 1. novembra'
    assert formaty.tyzden(date(2026, 11, 4)) == '45. týždeň'


# ---------------------------------------------------------------------------
# Analýza videa: celý postup nahratie → úloha vo vlákne → riadok v DB, s náhradou za MediaPipe
# ---------------------------------------------------------------------------
SPRINT_SUMMARY = {'steps_detected': 9, 'contact_ms_mean': 96.4, 'contact_ms_sd': 6.1, 'flight_ms_mean': 128.2,
                  'cadence_spm': 268.0, 'duty_factor_pct': 21.4, 'asymmetry_pct': 3.2, 'speed_ms': 10.4,
                  'stride_length_m': 2.31}
HURDLE_SUMMARY = {'hurdles_detected': 10, 'interval_mean_s': 4.21, 'interval_sd_s': 0.18,
                  'steps_pattern_text': '15-15-16', 'flight_ms_mean': 410.0, 'landing_contact_ms_mean': 120.0,
                  'speed_between_ms_mean': 8.31}


class FakeEngine:
    """Náhrada modulu video_analysis: rovnaké rozhranie, žiadne OpenCV ani MediaPipe."""

    class VideoAnalysisError(Exception):
        pass

    fail = False

    @staticmethod
    def dependencies_ok():
        return True, 'OK'

    @staticmethod
    def probe_video(path):
        return {'fps': 240.0, 'frames': 960, 'width': 1280, 'height': 720}

    @classmethod
    def analyze_video(cls, path, **kw):
        kw['progress_cb'](0.5, 'Hľadám kontakty so zemou')
        if cls.fail:
            raise cls.VideoAnalysisError('Na videu sa nenašiel bežec.')
        return {'video': {'fps': 240.0, 'duration_s': 4.0}, 'summary': dict(SPRINT_SUMMARY),
                'overlay_path': None, 'keyframes': []}


def _fake_hurdles(path, opts, **files):
    files['progress_cb'](0.5, 'Hľadám prekážky')
    return {'video': {'fps': 50.0, 'duration_s': 58.0}, 'discipline': opts['discipline'],
            'summary': dict(HURDLE_SUMMARY), 'overlay_path': None, 'keyframes': []}


@pytest.fixture()
def fake_engine(monkeypatch):
    FakeEngine.fail = False
    monkeypatch.setattr(analyza, '_engine', lambda: FakeEngine)
    monkeypatch.setitem(analyza.KINDS['hurdles'], 'run', _fake_hurdles)
    return FakeEngine


def _wait_for_job(client, job_id):
    for _ in range(100):
        job = client.get(f'/api/video/job/{job_id}').get_json()
        if job.get('state') in ('done', 'error'):
            return job
        time.sleep(0.05)
    raise AssertionError('úloha analýzy neskončila')


@pytest.mark.parametrize('kind, url, model, column, value', [
    ('sprint', '/api/video/analyze', VideoAnalysis, 'contact_ms_mean', 96.4),
    ('hurdles', '/api/hurdles/analyze', HurdleAnalysis, 'steps_pattern', '15-15-16'),
])
def test_analysis_job_saves_result(kind, url, model, column, value, people, fake_engine):
    client = login('trener1')
    resp = client.post(url, content_type='multipart/form-data', data={
        'video': (io.BytesIO(b'fake video'), 'beh.mp4'), 'label': 'Test', 'height_cm': '181',
        'athlete_id': str(people['zverenec1']), 'discipline': '400mH'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    job = _wait_for_job(client, resp.get_json()['job_id'])
    assert job['state'] == 'done', job
    with app.app_context():
        row = db.session.get(model, job['analysis_id'])
        assert row.user_id == people['zverenec1'] and row.label == 'Test'
        assert getattr(row, column) == value
        assert UserProfile.for_user(people['zverenec1']).height_cm == 181   # výška sa zapamätá zverencovi
    # výsledok vidí vlastný tréner aj zverenec, cudzí tréner nie
    result_url = ('/api/video/result/' if kind == 'sprint' else '/api/hurdles/result/') + str(job['analysis_id'])
    assert login('zverenec1').get(result_url).status_code == 200
    assert login('trener2').get(result_url).status_code == 403


def test_analysis_rejects_foreign_athlete_and_bad_files(people, fake_engine):
    client = login('trener1')
    resp = client.post('/api/video/analyze', content_type='multipart/form-data', data={
        'video': (io.BytesIO(b'x'), 'beh.mp4'), 'athlete_id': str(people['cudzi'])})
    assert resp.status_code == 403
    resp = client.post('/api/video/analyze', content_type='multipart/form-data', data={
        'video': (io.BytesIO(b'x'), 'beh.exe')})
    assert resp.status_code == 400 and 'nie je podporovaný' in resp.get_json()['error']


def test_failed_analysis_reports_error_and_removes_upload(people, fake_engine):
    fake_engine.fail = True
    client = login('zverenec1')
    resp = client.post('/api/video/analyze', content_type='multipart/form-data', data={
        'video': (io.BytesIO(b'fake video'), 'beh.mp4')})
    job_id = resp.get_json()['job_id']
    job = _wait_for_job(client, job_id)
    assert job['state'] == 'error' and 'bežec' in job['message']
    with app.app_context():
        assert not os.path.exists(os.path.join(analyza.video_dir(app), job_id + '.mp4'))
