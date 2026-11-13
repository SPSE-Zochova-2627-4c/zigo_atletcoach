# -*- coding: utf-8 -*-
"""
formaty.py – slovenské formáty dátumov pre šablóny.

    {{ d|den_mesiac }}           → „4. novembra“
    {{ (od, do)|rozsah_dni }}    → „2. – 8. novembra“  /  „28. októbra – 3. novembra“
    {{ d|tyzden }}               → „45. týždeň“ (ISO číslo týždňa)
"""

MESIACE_GENITIV = ('januára', 'februára', 'marca', 'apríla', 'mája', 'júna',
                   'júla', 'augusta', 'septembra', 'októbra', 'novembra', 'decembra')


def den_mesiac(d):
    if d is None:
        return ''
    return f'{d.day}. {MESIACE_GENITIV[d.month - 1]}'


def rozsah_dni(pair):
    start, end = pair
    if start.month == end.month and start.year == end.year:
        return f'{start.day}. – {end.day}. {MESIACE_GENITIV[end.month - 1]}'
    return f'{den_mesiac(start)} – {den_mesiac(end)}'


def tyzden(d):
    return f'{d.isocalendar()[1]}. týždeň'


def init_app(app):
    app.add_template_filter(den_mesiac)
    app.add_template_filter(rozsah_dni)
    app.add_template_filter(tyzden)
