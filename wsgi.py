# -*- coding: utf-8 -*-
"""
wsgi.py – vstup pre produkčný server (gunicorn / waitress) pri nasadení na hosting.

    gunicorn --config gunicorn.conf.py wsgi:app

Lokálne spúšťanie (run.command, run.bat, python app.py) sa nemení – to ide cez
vývojový server vo vnútri app.py. Tu sa navyše nastaví, čo potrebuje prevádzka
za reverznou proxy hostingu (HTTPS ukončuje proxy, appka vidí http):

- ProxyFix: hlavičky X-Forwarded-Proto / -For / -Host od proxy sa berú ako
  skutočná schéma a adresa klienta, takže url_for(_external=True), presmerovania
  a obmedzenie neúspešných prihlásení podľa IP fungujú správne;
- SESSION_COOKIE_SECURE: prihlasovacia cookie sa posiela len cez HTTPS
  (vypne sa premennou ATLETCOACH_HTTPS=0, napr. pri skúšaní cez obyčajné http).
"""
import os

from werkzeug.middleware.proxy_fix import ProxyFix

from app import app

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
if os.getenv('ATLETCOACH_HTTPS', '1') == '1':
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['PREFERRED_URL_SCHEME'] = 'https'
