# -*- coding: utf-8 -*-
"""
navigacia.py – čísla do bočného menu a do karty účtu (počet zverencov, čakajúce
žiadosti, tréningy tohto týždňa). Počíta sa raz na požiadavku, len pre prihláseného,
a každý dotaz je obmedzený na vlastné údaje (zverenec) alebo potvrdených zverencov (tréner).

Pridáva aj `asset_version` – číslo verzie CSS/JS do adresy súboru, aby prehliadač po zmene
dizajnu nenačítal starý súbor z cache.
"""
import os
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
            ids = [row.id for row in User.query.with_entities(User.id)
                   .filter_by(coach_id=user.id, coach_confirmed=True).all()]
            info['athletes'] = len(ids)
            info['pending'] = User.query.filter_by(coach_id=user.id, coach_confirmed=False).count()
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


def asset_version(static_folder):
    """Najnovší čas zmeny súborov rámu stránky (app.css, app.js) ako krátke číslo."""
    stamps = []
    for name in ('css/app.css', 'js/app.js'):
        try:
            stamps.append(int(os.path.getmtime(os.path.join(static_folder, name))))
        except OSError:
            pass
    return max(stamps, default=0)


def init_app(app):
    version = asset_version(app.static_folder)

    @app.context_processor
    def _inject_nav_info():
        return {'nav_info': nav_info(), 'asset_version': version}
