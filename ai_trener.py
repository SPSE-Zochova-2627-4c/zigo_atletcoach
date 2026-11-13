# -*- coding: utf-8 -*-
"""
ai_trener.py – AI tréner cez Groq API (blueprint 'ai').

- /ai              stránka s pripravenosťou a chatom
- /api/chat        odpoveď AI s kontextom atléta (profil, HRV, tréningy, videá, prekážky, rekordy zo Stravy)
- /profile         profil pre AI (meno, vek, disciplína, cieľ, výška)

groq_complete() je jediné miesto, ktoré volá Groq – používa ho chat aj komentár k analýze videa
(analyza.py). Bez GROQ_API_KEY v .env appka beží, AI časti len vrátia zrozumiteľnú chybu.
"""
import json
import os
import re
from datetime import date, timedelta

import requests
from flask import (Blueprint, current_app, flash, g, jsonify, redirect, render_template, request,
                   session, url_for)

from auth import login_required
from models import (utcnow, db, BiometricLog, ChatMessage, HurdleAnalysis, TrainingLog, UserProfile,
                    VideoAnalysis)
from strava import cached_prs

bp = Blueprint('ai', __name__)

GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
# Poradie = priorita; pri výpadku alebo limite sa skúsi ďalší model
GROQ_MODELS = ('llama-3.3-70b-versatile', 'openai/gpt-oss-120b', 'deepseek-r1-distill-llama-70b')
CHAT_HISTORY_LIMIT = 20


class AIError(RuntimeError):
    """Chyba AI s textom pre používateľa a HTTP kódom pre JSON odpoveď."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _api_key():
    key = os.getenv('GROQ_API_KEY', '')
    return key if key and not key.startswith(('gsk_...', 'your_')) else None


def groq_available():
    return _api_key() is not None


def groq_complete(messages, max_tokens=900, temperature=0.3):
    """Zavolá Groq s fallbackom medzi modelmi. Vráti (text, model) alebo vyhodí AIError."""
    key = _api_key()
    if key is None:
        raise AIError('AI tréner nie je nastavený: v súbore .env chýba GROQ_API_KEY.', 503)
    last_error = None
    for model in GROQ_MODELS:
        try:
            resp = requests.post(GROQ_URL, timeout=40,
                                 headers={'Authorization': f'Bearer {key}'},
                                 json={'model': model, 'messages': messages,
                                       'max_tokens': max_tokens, 'temperature': temperature})
        except requests.RequestException as e:
            last_error = repr(e)
            continue
        if resp.status_code == 401:
            raise AIError('Groq odmietol API kľúč. Skontroluj GROQ_API_KEY v súbore .env.', 502)
        if resp.status_code == 200:
            reply = resp.json()['choices'][0]['message']['content']
            # modely s „premýšľaním“ (deepseek-r1) vracajú aj <think>…</think> – to atlét nemá vidieť
            return re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL).strip(), model
        last_error = f'{model}: HTTP {resp.status_code}'
    current_app.logger.warning('Groq neodpovedal: %s', last_error)
    raise AIError('AI tréner teraz neodpovedá. Skús to o chvíľu znova.', 502)


# ---------------------------------------------------------------------------
# Kontext atléta pre chat
# ---------------------------------------------------------------------------
CHAT_SYSTEM_PROMPT = """Si osobný tréner a výkonnostný analytik pre šprintéra/bežca. Komunikuješ VÝLUČNE po slovensky.

## TVOJA ROLA
Ťažiskom je BEŽECKÁ TECHNIKA meraná z videa — čas kontaktu so zemou, letová fáza,
frekvencia krokov, asymetria a uhly v kĺboch. Biometrika (HRV, recovery, RHR) a tréningy
sú doplnkový kontext, ktorý vysvetľuje, prečo technika v daný deň vyzerá tak, ako vyzerá.
Dávaj presné, akčné odporúčania. Nie generické rady — vždy vychádzaj z čísel, ktoré máš.

## PRAVIDLÁ ODPOVEDÍ
1. Vždy po slovensky, nikdy po anglicky
2. Odpovedaj stručne a konkrétne — max 3-4 odstavce
3. Ak máš dáta atleta, MUSÍŠ ich použiť (cituj konkrétne HRV, recovery %)
4. Dávaj konkrétne čísla: "bež 6×200m v 28-29s" nie "rob intervaly"
5. Nezačínaj odpoveď s "Samozrejme" ani "Určite" — choď rovno k veci
6. Ak niečo nevieš presne, povedz to a navrhni alternatívu
7. NIE SI LEKÁR. Nedávaš diagnózy ani nelieč. Ak atlét píše o bolesti, zranení, závratoch,
   búšení srdca, dlhšie zvýšenom pokojovom tepe alebo inom zdravotnom probléme, odporuč
   lekára alebo fyzioterapeuta a navrhni len bezpečnú úpravu tréningu (oddych, zníženie
   záťaže). HRV, recovery a RHR sú orientačné ukazovatele, nie zdravotný záver.
   Atléti sú často 15–19-roční — žiadne rady o diétach na chudnutie, doplnkoch výživy
   či liekoch; pri výžive len všeobecné zásady a odkaz na trénera alebo odborníka

## ODBORNÉ ZNALOSTI

### HRV interpretácia pre šprint:
- HRV >80ms = výborná forma, trénuj intenzívne
- HRV 60-80ms = dobrá forma, stredná intenzita
- HRV 40-60ms = únava, ľahký tréning alebo regenerácia
- HRV <40ms = STOP intenzívny tréning, aktívna regenerácia
- Pokles >15% oproti priemeru = varuj atleta

### Recovery (WHOOP) interpretácia:
- Zelená (67-100%) = trénovať naplno
- Žltá (34-66%) = stredná intenzita, sledovať únavu
- Červená (0-33%) = regenerácia, nič ťažké

### RHR trendy:
- Zvýšenie RHR o 5+ bpm oproti priemeru = začínajúce ochorenie alebo pretrénovanie
- Klesajúci RHR cez týždne = zlepšenie aeróbnej zdatnosti

### Technika z videa — ako čítať čísla:
- Kontakt so zemou pri maximálnej rýchlosti: elita 0,08-0,10 s, dobrý dorastenec 0,10-0,13 s,
  nad 0,15 s pri šprinte = brzdenie, noha dopadá príliš pred ťažiskom (overstriding)
- Kratší kontakt pri ROVNAKEJ dĺžke kroku = vyššia rýchlosť. Kratší kontakt za cenu
  skrátenia kroku nie je zlepšenie — vždy sa pozri na obe čísla naraz
- Frekvencia krokov pri šprinte: 4,2-5,0 kroku/s (250-300 krokov/min)
- Duty factor pri šprinte 0,20-0,30. Vyššie číslo = beh bližšie k vytrvalostnému
- Asymetria Ľ/P do 3 % je bežná, 3-5 % sleduj, nad 5 % opakovane = pozri silu,
  pohyblivosť členka/bedra alebo staršie zranenie. Jedno meranie nestačí na záver
- Vertikálna oscilácia nad ~9 cm pri šprinte = energia ide hore namiesto dopredu
- Uhol kolena pri dopade blízko 180° znamená vystretú nohu = tvrdý dopad a brzdenie

### Ako hovoriť o presnosti merania:
- Ak bolo video pod 100 fps, VŽDY povedz, že čísla sú orientačné a odporuč spomalený záber
- Ak sa metóda kostry a optický tok líšia o viac než ~25 ms, neinterpretuj rozdiely
  medzi jednotlivými krokmi — hovor len o priemere
- Nikdy nerob záver o trende z jediného videa

### 400m šprint tréning:
- Intenzity: A=>95% max, B=85-95%, C=75-85%, D=<75%
- Týždenná štruktúra: 1-2x A, 1-2x B, 1x regenerácia
- Kľúčové sedenia: špeciálna vytrvalosť (200-600m úseky), rýchlostná vytrvalosť (100-200m úseky)
- Objem pred pretekmi: znížiť o 40-60% 7-10 dní pred
- Regenerácia po závode: 3-5 dní ľahký tréning

### Výživa pre šprint:
- Pred tréningom: 3-4h pred jedlo, 1h pred ľahká sacharidová sačinka
- Po intenzívnom tréningu: proteín do 30min, sacharidy do 2h
- Hydratácia: 500ml 2h pred, 200ml každých 15min pri cvičení

## PRÍKLADY SPRÁVNYCH ODPOVEDÍ

Otázka: "Ako vyzerá môj HRV dnes?"
Správna odpoveď: "Tvoje dnešné HRV je [X]ms, čo je [nad/pod] tvojim 30-dňovým priemerom [Y]ms o [Z]%. [Ak nad priemerom:] Telo je dobre zregenerované — ideálny deň na intenzívny tréning. [Ak pod:] Odporúčam znížiť intenzitu — maximálne tempový beh v zóne 2-3."

Otázka: "Čo mám robiť dnes?"
Správna odpoveď: [vždy vychádza z aktuálnych dát recovery a HRV z kontextu]

Otázka: "Ako som na tom s technikou?"
Správna odpoveď: "Z posledného videa máš kontakt so zemou [X] ms pri frekvencii [Y] krokov/min.
[Porovnanie s pásmom pre šprint.] Asymetria [Z] % — [interpretácia]. [Ak bolo video pod 100 fps
alebo sa metódy nezhodli: upozorni na presnosť.] Konkrétne by som sa zameral na [cvičenie]." """

PR_LABELS = {'400m': '400 m', '800m': '800 m', '5k': '5 km', '10k': '10 km',
             'half': 'polmaratón', 'marathon': 'maratón'}


def _avg(values):
    return round(sum(values) / len(values), 1) if values else None


def _profile_section(user_id):
    profile = UserProfile.for_user(user_id)
    if not profile or not any([profile.name, profile.age, profile.sport, profile.goal]):
        return ''
    lines = ['\n\n## PROFIL ATLETA']
    if profile.name:
        lines.append(f'Meno: {profile.name}')
    if profile.age:
        lines.append(f'Vek: {profile.age} rokov')
    if profile.sport:
        lines.append(f'Hlavná disciplína: {profile.sport}')
    if profile.goal:
        lines.append(f'Cieľ: {profile.goal}')
    return '\n'.join(lines) + '\n'


def _strava_prs_section():
    # Rekordy len z cache – chat nesmie čakať na desiatky volaní Stravy
    prs = cached_prs(session.get('strava_access_token', ''))
    lines = [f"  {label}: {prs[key]['time']}" + (f", tempo {prs[key]['pace']}" if prs[key].get('pace') else '')
             for key, label in PR_LABELS.items() if (prs.get(key) or {}).get('time')]
    return ('\n## OSOBNÉ REKORDY (Strava)\n' + '\n'.join(lines) + '\n') if lines else ''


def _biometrics_section(logs, today):
    hrv_all = [l.hrv for l in logs if l.hrv]
    rhr_all = [l.rhr for l in logs if l.rhr]
    rec_all = [l.recovery for l in logs if l.recovery]
    hrv_w1 = [l.hrv for l in logs if l.hrv and l.date >= today - timedelta(days=7)]
    hrv_w2 = [l.hrv for l in logs if l.hrv and today - timedelta(days=14) <= l.date < today - timedelta(days=7)]
    trend = ''
    if hrv_w1 and hrv_w2:
        diff = _avg(hrv_w1) - _avg(hrv_w2)
        trend = f"{'↑' if diff > 0 else '↓'} {abs(round(diff, 1))}ms vs minulý týždeň"
    text = (f'\n### Biometrika (posledných 60 dní, {len(logs)} záznamov)\n'
            f'HRV: priemer={_avg(hrv_all)}ms | tento týždeň={_avg(hrv_w1)}ms | {trend}\n'
            f"RHR: priemer={_avg(rhr_all)}bpm | min={min(rhr_all) if rhr_all else '?'}bpm\n"
            f'Recovery: zelená={sum(r >= 67 for r in rec_all)}d | žltá={sum(34 <= r < 67 for r in rec_all)}d'
            f' | červená={sum(r < 34 for r in rec_all)}d | priemer={_avg(rec_all)}%\n\nPosledných 7 dní:')
    for log in logs[:7]:
        rec = f', Recovery={log.recovery}%' if log.recovery else ''
        zone = ('Z' if log.recovery >= 67 else 'Y' if log.recovery >= 34 else 'R') if log.recovery else ''
        text += f"\n  {log.date.strftime('%d.%m')}: HRV={log.hrv}ms{rec} {zone}, RHR={log.rhr or '?'}bpm"
    return text


def _trainings_section(train_logs):
    text = '\n\n### Tréningy (posledných 60 dní):'
    for t in train_logs:
        dur = f' {t.duration_min}min' + (f' {int(t.duration_sec)}s' if t.duration_sec else '') \
            if t.duration_min else ''
        dist = f' {t.distance_km}km' if t.distance_km else ''
        intervals = f' [{t.intervals_data}]' if t.intervals_data else ''
        notes = f' — {t.notes}' if t.notes else ''
        text += f"\n  {t.date.strftime('%d.%m')} {t.training_type}:{dist}{dur}{intervals}{notes}"
    return text


def _video_section(videos):
    text = '\n### Analýza techniky z videa\n'
    for v in videos:
        parts = [v.created_at.strftime('%d.%m.%Y')]
        if v.label:
            parts.append(v.label)
        if v.contact_ms_mean:
            sd = f' ±{v.contact_ms_sd:.0f}' if v.contact_ms_sd else ''
            parts.append(f'kontakt so zemou {v.contact_ms_mean:.0f}{sd} ms')
        if v.flight_ms_mean:
            parts.append(f'let {v.flight_ms_mean:.0f} ms')
        if v.cadence_spm:
            parts.append(f'kadencia {v.cadence_spm:.0f} krokov/min')
        if v.duty_factor_pct:
            parts.append(f'duty factor {v.duty_factor_pct:.0f} %')
        if v.asymmetry_pct is not None:
            parts.append(f'asymetria Ľ/P {v.asymmetry_pct:.1f} %')
        if v.speed_ms:
            parts.append(f'rýchlosť {v.speed_ms:.1f} m/s')
        if v.stride_length_m:
            parts.append(f'dvojkrok {v.stride_length_m:.2f} m')
        if v.fps:
            parts.append(f'(video {v.fps:.0f} fps' + (', presnosť nízka' if v.fps < 100 else '') + ')')
        text += '  ' + ' | '.join(parts) + '\n'
        try:
            findings = (json.loads(v.result_json or '{}').get('technique') or {}).get('findings', [])
        except ValueError:
            findings = []
        bad = [f for f in findings if f.get('status') in ('problem', 'pozor')]
        if bad:
            text += '    Technika – na zlepšenie: ' + '; '.join(
                f"{f['label']} {f['value_text']} ({f['status']})" for f in bad[:5]) + '\n'
    return text + ('  Referencia pre šprint: kontakt so zemou 0.09–0.13 s, kratší kontakt pri rovnakej dĺžke '
                   'kroku = vyššia rýchlosť. Asymetria nad 5 % môže naznačovať svalovú nerovnováhu.\n')


def _hurdles_section(rows):
    text = '\n### Analýza prekážok z videa\n'
    for h in rows:
        parts = [h.created_at.strftime('%d.%m.%Y'), h.discipline or '', h.label or '']
        if h.hurdles_detected:
            parts.append(f'{h.hurdles_detected} prekážok')
        if h.interval_mean_s:
            parts.append(f'medzičas {h.interval_mean_s:.2f} s')
        if h.steps_pattern:
            parts.append(f'kroky medzi prekážkami {h.steps_pattern}')
        if h.speed_between_ms_mean:
            parts.append(f'rýchlosť medzi prekážkami {h.speed_between_ms_mean:.1f} m/s')
        text += '  ' + ' | '.join(p for p in parts if p) + '\n'
    return text


def athlete_context(user_id):
    """Všetko, čo o atlétovi vieme, ako text pre systémový prompt (len jeho vlastné údaje)."""
    today = date.today()
    since = today - timedelta(days=60)
    context = _profile_section(user_id) + _strava_prs_section()

    logs = BiometricLog.query.filter(BiometricLog.user_id == user_id, BiometricLog.date >= since) \
        .order_by(BiometricLog.date.desc()).all()
    train_logs = TrainingLog.query.filter(TrainingLog.user_id == user_id, TrainingLog.date >= since) \
        .order_by(TrainingLog.date.desc()).limit(20).all()
    if logs or train_logs:
        context += '\n## AKTUÁLNE DÁTA ATLETA\n'
    if logs:
        context += _biometrics_section(logs, today)
    if train_logs:
        context += _trainings_section(train_logs)

    videos = VideoAnalysis.query.filter_by(user_id=user_id) \
        .order_by(VideoAnalysis.created_at.desc()).limit(3).all()
    if videos:
        context += _video_section(videos)
    hurdles = HurdleAnalysis.query.filter_by(user_id=user_id) \
        .order_by(HurdleAnalysis.created_at.desc()).limit(3).all()
    if hurdles:
        context += _hurdles_section(hurdles)

    if context:
        context += '\n\n[Toto sú TVOJE skutočné dáta — vždy ich použi pri odpovedi]'
    return context


# ---------------------------------------------------------------------------
# Routy
# ---------------------------------------------------------------------------
@bp.route('/ai')
@login_required
def portal():
    return render_template('ai.html', groq_ok=groq_available())


@bp.route('/api/chat', methods=['POST'])
@login_required
def chat():
    message = ((request.get_json(silent=True) or {}).get('message') or '').strip()
    if not message:
        return jsonify({'error': 'Napíš správu.'}), 400
    if len(message) > 4000:
        return jsonify({'error': 'Správa je príliš dlhá (najviac 4000 znakov).'}), 400

    try:
        context = athlete_context(g.user.id)
    except Exception:   # kontext je doplnok – chyba v ňom nesmie zablokovať odpoveď
        current_app.logger.exception('AI chat: kontext atléta zlyhal')
        context = ''
    history = ChatMessage.query.filter_by(user_id=g.user.id) \
        .order_by(ChatMessage.created_at.desc()).limit(CHAT_HISTORY_LIMIT).all()
    messages = [{'role': 'system', 'content': CHAT_SYSTEM_PROMPT + context}]
    messages += [{'role': m.role, 'content': m.content} for m in reversed(history)]
    messages.append({'role': 'user', 'content': message})

    try:
        reply, model = groq_complete(messages, max_tokens=1500)
    except AIError as e:
        return jsonify({'error': str(e)}), e.status

    db.session.add(ChatMessage(user_id=g.user.id, role='user', content=message))
    db.session.add(ChatMessage(user_id=g.user.id, role='assistant', content=reply))
    db.session.commit()
    return jsonify({'reply': reply, 'model': model})


@bp.route('/api/chat/history')
@login_required
def chat_history():
    msgs = ChatMessage.query.filter_by(user_id=g.user.id).order_by(ChatMessage.created_at.asc()).all()
    return jsonify([{'role': m.role, 'content': m.content} for m in msgs])


@bp.route('/api/chat/clear', methods=['POST'])
@login_required
def chat_clear():
    ChatMessage.query.filter_by(user_id=g.user.id).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/profile/api')
@login_required
def profile_api():
    p = UserProfile.for_user(g.user.id)
    if not p:
        return jsonify({})
    return jsonify({'name': p.name, 'age': p.age, 'sport': p.sport, 'goal': p.goal})


def _number(raw, cast, lo, hi):
    """Číslo z formulára v rozsahu lo–hi, inak None (prázdne aj nezmysel)."""
    try:
        value = cast((raw or '').strip().replace(',', '.'))
    except ValueError:
        return None
    return value if lo <= value <= hi else None


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    p = UserProfile.for_user(g.user.id)
    if request.method == 'POST':
        p = p or UserProfile.for_user(g.user.id, create=True)
        p.name = request.form.get('name', '').strip()[:100] or None
        p.age = _number(request.form.get('age'), int, 5, 100)
        p.sport = request.form.get('sport', '').strip()[:100] or None
        p.goal = request.form.get('goal', '').strip()[:200] or None
        p.height_cm = _number(request.form.get('height_cm'), float, 100, 230)
        p.updated_at = utcnow()
        db.session.commit()
        flash('Profil uložený.', 'success')
        return redirect(url_for('ai.portal'))
    return render_template('profile.html', p=p)
