# -*- coding: utf-8 -*-
"""
pravne.py – verejné informačné stránky: Ochrana osobných údajov, Podmienky používania
(vrátane platieb a vrátenia peňazí – appka je bezplatná) a Cookies.

Sú prístupné bez prihlásenia a odkazuje na ne päta každej stránky. Kontakt na
prevádzkovateľa sa neberie z kódu, ale z premennej prostredia
ATLETCOACH_KONTAKT_EMAIL (.env), aby v repozitári nebola žiadna súkromná adresa;
bez nej ostáva ako kontakt repozitár na GitHube.
"""
import os

from flask import Blueprint, render_template

bp = Blueprint('pravne', __name__)

GITHUB_URL = 'https://github.com/scalyeu/maturitny_projekt'
# Dátum poslednej zmeny textov – ukazuje sa na stránkach a mení sa pri každej úprave.
VERZIA = '20. októbra 2026'


@bp.app_context_processor
def _pravne_context():
    """Päta a právne stránky: kontakt (ak je nastavený), odkaz na repozitár, dátum verzie."""
    email = (os.getenv('ATLETCOACH_KONTAKT_EMAIL') or '').strip()
    return {'kontakt_email': email or None, 'github_url': GITHUB_URL, 'pravne_verzia': VERZIA}


@bp.route('/ochrana-udajov')
def ochrana_udajov():
    return render_template('pravne/ochrana_udajov.html')


@bp.route('/podmienky')
def podmienky():
    return render_template('pravne/podmienky.html')


@bp.route('/cookies')
def cookies():
    return render_template('pravne/cookies.html')
