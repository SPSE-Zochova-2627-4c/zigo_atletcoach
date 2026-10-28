"""
Databázové modely AtletCoach.

`db` sa vytvára tu bez aplikácie a v app.py sa pripojí cez `db.init_app(app)`,
aby si modely mohli importovať aj blueprinty (trener.py, planovanie.py, …)
bez toho, že by importovali app.py – to by skončilo kruhovým importom.

Názvy tabuliek sú vypísané explicitne, aby sa pri presune z app.py nezmenili
a existujúca database.db ostala čitateľná.
"""
import json
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

ROLES = ('zverenec', 'trener', 'admin')
ROLE_LABELS = {'zverenec': 'Zverenec', 'trener': 'Tréner', 'admin': 'Administrátor'}


# -----------------------------
# Používatelia
# -----------------------------
class User(db.Model):
    """Účet – zverenec, tréner alebo administrátor."""
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default='zverenec')
    full_name = db.Column(db.String(120), nullable=True)
    # Pre zverenca: jeho tréner. Tréner cez tento vzťah vidí údaje zverenca.
    coach_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    # Tréner vidí údaje zverenca až keď zverenec vzťah potvrdí (alebo účet vytvoril tréner/admin).
    # Predvolene False: zabudnutý príznak radšej nič neukáže, než by ukázal cudzie videá.
    coach_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    world_athletics_id = db.Column(db.String(32), nullable=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    # Tréningová skupina („objemovci“, „ados group“) a prezývka („Zigo“) – podľa nich
    # sa riadky týždenného plánu z textu trénera priradia správnym zverencom.
    group_name = db.Column(db.String(60), nullable=True)
    nickname = db.Column(db.String(60), nullable=True)
    # Kedy používateľ odsúhlasil Podmienky používania a Ochranu osobných údajov.
    # None = ešte nie (účet založil tréner/admin) – pri prvom prihlásení sa súhlas vyžiada.
    terms_accepted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    coach = db.relationship('User', remote_side=[id], foreign_keys=[coach_id],
                            backref=db.backref('athletes', lazy='select'))

    # --- heslo ---
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash or '', password or '')

    # --- rola ---
    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_coach(self):
        return self.role == 'trener'

    @property
    def is_athlete(self):
        return self.role == 'zverenec'

    @property
    def role_label(self):
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def display_name(self):
        return self.full_name or self.username

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class RaceResult(db.Model):
    """Výsledok z pretekov; osobný rekord = min(result_s) na disciplínu (nepočíta sa do DB)."""
    __tablename__ = 'race_result'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    discipline = db.Column(db.String(40), nullable=False)
    result_s = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    competition = db.Column(db.String(160), nullable=True)
    place = db.Column(db.String(20), nullable=True)
    wind = db.Column(db.Float, nullable=True)
    source = db.Column(db.String(20), nullable=False, default='manual')   # manual | world_athletics | stopky
    note = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    athlete = db.relationship('User', foreign_keys=[user_id],
                              backref=db.backref('race_results', lazy='select'))
    author = db.relationship('User', foreign_keys=[created_by])

    @property
    def result_text(self):
        """11.23 → '11.23', 125.4 → '2:05.40' – na zobrazenie v tabuľkách."""
        s = self.result_s or 0.0
        if s < 60:
            return f'{s:.2f}'
        m, sec = divmod(s, 60)
        return f'{int(m)}:{sec:05.2f}'


class PlannedTraining(db.Model):
    """Tréning, ktorý trénér naplánoval zverencovi; zverenec ho označí za splnený."""
    __tablename__ = 'planned_training'
    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    athlete_note = db.Column(db.Text, nullable=True)
    training_log_id = db.Column(db.Integer, db.ForeignKey('training_log.id'), nullable=True)
    # Týždenný plán z textu: všetky tréningy z jedného vloženia zdieľajú batch_id
    # (dá sa zmazať celý týždeň naraz); time_text je čas začiatku „15:00“ z textu.
    batch_id = db.Column(db.String(36), nullable=True, index=True)
    time_text = db.Column(db.String(5), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    athlete = db.relationship('User', foreign_keys=[athlete_id],
                              backref=db.backref('planned_trainings', lazy='select'))
    coach = db.relationship('User', foreign_keys=[coach_id])
    training_log = db.relationship('TrainingLog', foreign_keys=[training_log_id])
    items = db.relationship('PlanItem', backref='plan', order_by='PlanItem.position',
                            cascade='all, delete-orphan', lazy='select')

    @property
    def title_with_time(self):
        return f'{self.time_text} {self.title}' if self.time_text else self.title


class PlanItem(db.Model):
    """
    Jedna položka naplánovaného tréningu: cvik v posilňovni („Bulharské drepy 8a8x2“),
    bežecký úsek („10 až 12x400m“) alebo voľný text. Zverenec k nej zapíše, čo reálne
    spravil: kilá na každú sériu (sila) alebo časy úsekov (beh) do result_json.
    """
    __tablename__ = 'plan_item'
    KINDS = ('beh', 'sila', 'ine')
    MAX_SLOTS = 12          # najviac políčok na zápis (série / úseky) pri jednej položke

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('planned_training.id'), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    kind = db.Column(db.String(8), nullable=False, default='ine')
    text = db.Column(db.String(200), nullable=False)        # riadok z textu trénera / zverenca
    exercise = db.Column(db.String(120), nullable=True)     # názov cviku (sila)
    reps = db.Column(db.Integer, nullable=True)             # opakovania (sila) / počet úsekov (beh)
    reps_max = db.Column(db.Integer, nullable=True)         # horná hranica rozsahu „10 až 12x“
    per_side = db.Column(db.Boolean, nullable=False, default=False)   # „8a8“ = na každú stranu
    sets = db.Column(db.Integer, nullable=True)             # série
    distance_m = db.Column(db.Float, nullable=True)
    intensity_pct = db.Column(db.Integer, nullable=True)
    result_json = db.Column(db.Text, nullable=True)         # [kg na sériu] alebo [s na úsek]
    result_note = db.Column(db.String(200), nullable=True)
    added_by_athlete = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @property
    def results(self):
        """Zapísané hodnoty ako zoznam čísel (None = prázdne políčko)."""
        if not self.result_json:
            return []
        try:
            vals = json.loads(self.result_json)
        except ValueError:
            return []
        return [v if isinstance(v, (int, float)) else None for v in vals]

    @property
    def slots(self):
        """Koľko políčok na zápis má položka: sila = série, beh = úseky (× série), inak 0."""
        if self.kind == 'sila':
            n = self.sets or 1
        elif self.kind == 'beh':
            n = (self.reps_max or self.reps or 1) * (self.sets or 1)
        else:
            n = 0
        return max(0, min(n, self.MAX_SLOTS))

    @property
    def unit(self):
        return 'kg' if self.kind == 'sila' else ('s' if self.kind == 'beh' else '')

    @property
    def has_results(self):
        return any(v is not None for v in self.results)

    @property
    def best(self):
        """Najlepší výkon: najväčšie kilá (sila) alebo najkratší čas (beh)."""
        vals = [v for v in self.results if v is not None]
        if not vals:
            return None
        return max(vals) if self.kind == 'sila' else min(vals)


# -----------------------------
# Pôvodné modely (presunuté z app.py) + user_id
# -----------------------------
class BiometricLog(db.Model):
    __tablename__ = 'biometric_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    hrv = db.Column(db.Float, nullable=False)
    recovery = db.Column(db.Integer, nullable=True)
    rhr = db.Column(db.Integer, nullable=True)


class TrainingLog(db.Model):
    __tablename__ = 'training_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    training_type = db.Column(db.String(100), nullable=False)
    distance_km = db.Column(db.Float, nullable=True)
    duration_min = db.Column(db.Float, nullable=True)
    duration_sec = db.Column(db.Float, nullable=True)
    intervals_data = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)


class StravaToken(db.Model):
    __tablename__ = 'strava_token'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    athlete_id = db.Column(db.String(64), nullable=True, index=True)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class ChatMessage(db.Model):
    __tablename__ = 'chat_message'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class UserProfile(db.Model):
    __tablename__ = 'user_profile'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    name = db.Column(db.String(100), nullable=True)
    age = db.Column(db.Integer, nullable=True)
    sport = db.Column(db.String(100), nullable=True)
    goal = db.Column(db.String(200), nullable=True)
    height_cm = db.Column(db.Float, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class VideoAnalysis(db.Model):
    """Uložený výsledok analýzy techniky z videa."""
    __tablename__ = 'video_analysis'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    original_name = db.Column(db.String(255), nullable=True)
    stored_name = db.Column(db.String(255), nullable=True)
    overlay_name = db.Column(db.String(255), nullable=True)
    label = db.Column(db.String(120), nullable=True)

    fps = db.Column(db.Float, nullable=True)
    duration_s = db.Column(db.Float, nullable=True)
    athlete_height_cm = db.Column(db.Float, nullable=True)

    steps_detected = db.Column(db.Integer, nullable=True)
    contact_ms_mean = db.Column(db.Float, nullable=True)
    contact_ms_sd = db.Column(db.Float, nullable=True)
    flight_ms_mean = db.Column(db.Float, nullable=True)
    cadence_spm = db.Column(db.Float, nullable=True)
    duty_factor_pct = db.Column(db.Float, nullable=True)
    asymmetry_pct = db.Column(db.Float, nullable=True)
    speed_ms = db.Column(db.Float, nullable=True)
    stride_length_m = db.Column(db.Float, nullable=True)

    result_json = db.Column(db.Text, nullable=True)


class HurdleAnalysis(db.Model):
    """Uložený výsledok analýzy prekážkového behu z videa."""
    __tablename__ = 'hurdle_analysis'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    original_name = db.Column(db.String(255), nullable=True)
    stored_name = db.Column(db.String(255), nullable=True)
    overlay_name = db.Column(db.String(255), nullable=True)
    label = db.Column(db.String(120), nullable=True)
    discipline = db.Column(db.String(20), nullable=True)

    fps = db.Column(db.Float, nullable=True)
    duration_s = db.Column(db.Float, nullable=True)
    athlete_height_cm = db.Column(db.Float, nullable=True)

    hurdles_detected = db.Column(db.Integer, nullable=True)
    interval_mean_s = db.Column(db.Float, nullable=True)
    interval_sd_s = db.Column(db.Float, nullable=True)
    steps_pattern = db.Column(db.String(120), nullable=True)
    flight_ms_mean = db.Column(db.Float, nullable=True)
    landing_contact_ms_mean = db.Column(db.Float, nullable=True)
    speed_between_ms_mean = db.Column(db.Float, nullable=True)

    result_json = db.Column(db.Text, nullable=True)


# Tabuľky, ktoré existovali pred zavedením účtov a potrebujú doplniť user_id.
# app._ensure_columns() ich prejde a chýbajúce stĺpce pridá cez ALTER TABLE.
LEGACY_USER_TABLES = (
    'biometric_log', 'training_log', 'chat_message', 'user_profile',
    'video_analysis', 'hurdle_analysis', 'strava_token',
)
