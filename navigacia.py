# -*- coding: utf-8 -*-
"""
navigacia.py – čísla do bočného menu a do karty účtu (počet zverencov, čakajúce
žiadosti, tréningy tohto týždňa). Počíta sa raz na požiadavku, len pre prihláseného,
a každý dotaz je obmedzený na vlastné údaje (zverenec) alebo potvrdených zverencov (tréner).
"""
from datetime import date, timedelta

from flask import g

from models import db, User, PlannedTraining


def _week_bounds(today):
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def nav_info():
    user = g.get('user')
    info = {'athletes': None, 'pending': None, 'week_planned': None, 'week_done': None, 'users': None}
    if user is None:
        return info
    today = date.today()
    monday, sunday = _week_bounds(today)
    try:
        if user.is_athlete:
            q = PlannedTraining.query.filter(PlannedTraining.athlete_id == user.id,
                                             PlannedTraining.date >= monday, PlannedTraining.date <= sunday)
            info['week_planned'] = q.count()
            info['week_done'] = q.filter(PlannedTraining.completed.is_(True)).count()
        elif user.is_coach:
            info['athletes'] = User.query.filter_by(coach_id=user.id, coach_confirmed=True).count()
            info['pending'] = User.query.filter_by(coach_id=user.id, coach_confirmed=False).count()
            ids = [a.id for a in User.query.filter_by(coach_id=user.id, coach_confirmed=True).with_entities(User.id).all()]
            if ids:
                q = PlannedTraining.query.filter(PlannedTraining.athlete_id.in_(ids),
                                                 PlannedTraining.date >= monday, PlannedTraining.date <= sunday)
                info['week_planned'] = q.count()
                info['week_done'] = q.filter(PlannedTraining.completed.is_(True)).count()
            else:
                info['week_planned'] = info['week_done'] = 0
        elif user.is_admin:
            info['users'] = User.query.count()
            info['athletes'] = User.query.filter_by(role='zverenec').count()
    except Exception:
        db.session.rollback()
    return info


def init_app(app):
    @app.context_processor
    def _inject_nav_info():
        return {'nav_info': nav_info()}
