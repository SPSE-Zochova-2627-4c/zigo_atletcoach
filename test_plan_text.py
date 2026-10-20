# -*- coding: utf-8 -*-
"""
test_plan_text.py
=================
Rozbor týždenného plánu z textu trénera (plan_text.py) na skutočnej správe:
dni, bloky s časom, skupiny, mená, cviky (10x2, 8a8x2), behy (30 až 40x 26,5m,
3x3x26,5m na 92 %, 10 až 12x400m), voľný deň a úvodné poznámky.

Spustenie:   python test_plan_text.py
"""
import plan_text as pt

TEXT = """Dobry den,

ti co pretekali na Dorasteneckej lige volno. rocniky 2009 a 2010 posezonne tyzdnove volno plus lucia, eliska, smity

Farky a Matias su objemovci a Zigo sa chysta na medzistatne stretnutie.

Pondelok

15:00 novy sprint rozcvicenie od A do Z

kontrolny start na 150m

16:00 objemovci

30 az 40x 26,5m kopec

Marsal Mandak 3x3x26,5m na 92%

Utorok

16:00 bejby vetva mlade pusky

17:00 objemovci

Tlaky na ramená s veľkou osou v stoji 10x2
Bulharské drepy 8a8x2
Brucho (s kotúčom) 20x2
Hip thrust 10x2
Bočný plank so závažím 10a10x2
Biceps veľká tyč o stenu 15x2

Streda

15:00 novy sprint korculiarske odrazy a klus poskocny

Timo ladis s trenerom D na Majstrovstva strednej Europy

16:00
jelenaky 12x10
polovicne jelenaky 6a6x5 s ostrym kolenom hore
polovicne jelenaky 6a6x5 s aktivnym zaslapom
Odhody 3x x3 skok vzad odhid vpred

Stvrtok
17:45
objemovci 10 az 12x400m s 1min pauzou

Piatok
15:00 novy sprint kopce
16:00 strecing mobilita dychove cvicenia
izometria pevny stred

Sobota volno

Nedela
18:00 vsetci
6 razove maximum
drep tlak
"""

GROUPS = {'novy sprint': 'nový šprint', 'objemovci': 'objemovci', 'bejby vetva': 'bejby vetva'}
PEOPLE = [(1, ['Zigo', 'Tomáš', 'Žigo', 'tzigo']), (2, ['Marsal', 'Marcel', 'Maršál']),
          (3, ['Mandak', 'Mandák']), (4, ['Timo', 'Timotej']), (5, ['Farky']), (6, ['Matias'])]


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(('  [OK]   ' if cond else '  [CHYBA] ') + msg)
        ok = ok and bool(cond)

    print('\n=== Rozbor plánu trénera ===\n')
    res = pt.parse(TEXT, pt.Matcher(GROUPS, PEOPLE))
    days = {d['day']: d for d in res['days']}
    check(len(res['days']) == 7 and sorted(days) == list(range(7)), f"7 dní v poradí ({[d['day'] for d in res['days']]})")
    check(len(res['intro']) == 3, f"3 úvodné riadky ({len(res['intro'])})")
    check(days[5]['rest'] and not days[5]['blocks'], 'sobota je voľno')

    mon = days[0]['blocks']
    check(len(mon) == 3, f'pondelok má 3 bloky ({len(mon)})')
    check(mon[0]['time'] == '15:00' and mon[0]['groups'] == ['nový šprint'], 'pondelok 15:00 patrí skupine nový šprint')
    check(mon[0]['items'] and mon[0]['items'][0]['kind'] == 'beh' and mon[0]['items'][0]['distance_m'] == 150,
          'kontrolný štart na 150 m je beh na 150 m')
    it = mon[1]['items'][0] if mon[1]['items'] else {}
    check(mon[1]['groups'] == ['objemovci'] and it.get('kind') == 'beh' and it.get('reps') == 30
          and it.get('reps_max') == 40 and it.get('distance_m') == 26.5, '30 až 40x 26,5m kopec → beh 30–40 × 26,5 m')
    it = mon[2]['items'][0]
    check(sorted(mon[2]['people']) == [2, 3] and it['kind'] == 'beh' and it['sets'] == 3 and it['reps'] == 3
          and it['distance_m'] == 26.5 and it.get('intensity_pct') == 92, 'Marsal Mandak 3x3x26,5m na 92 % → vlastný blok pre dvoch')

    tue = days[1]['blocks']
    check(tue[0]['groups'] == ['bejby vetva'] and tue[1]['groups'] == ['objemovci'], 'utorok: bejby vetva a objemovci')
    sila = tue[1]['items']
    check(len(sila) == 6 and all(i['kind'] == 'sila' for i in sila), f'6 cvikov v posilňovni ({len(sila)})')
    bd = next((i for i in sila if i['exercise'].startswith('Bulharsk')), {})
    check(bd.get('reps') == 8 and bd.get('per_side') and bd.get('sets') == 2, 'Bulharské drepy 8a8x2 → 8 na stranu × 2 série')
    tl = sila[0]
    check(tl['exercise'] == 'Tlaky na ramená s veľkou osou v stoji' and tl['reps'] == 10 and tl['sets'] == 2,
          'názov cviku bez čísel, 10 × 2')

    wed = days[2]['blocks']
    timo = [b for b in wed if b['people'] == [4]]
    check(len(timo) == 1 and timo[0]['time'] is None, 'Timo má vlastný blok bez času')
    gym = [b for b in wed if b['time'] == '16:00'][0]
    check(len(gym['items']) == 4 and gym['items'][0]['kind'] == 'sila' and gym['items'][0]['sets'] == 10
          and gym['items'][0]['reps'] == 12, 'jelenaky 12x10 → 12 × 10 sérií')
    check(not gym['groups'] and not gym['people'], 'streda 16:00 nemá skupinu – tréner priradí v náhľade')

    thu = days[3]['blocks'][0]
    it = thu['items'][0]
    check(thu['time'] == '17:45' and thu['groups'] == ['objemovci'] and it['kind'] == 'beh' and it['reps'] == 10
          and it['reps_max'] == 12 and it['distance_m'] == 400, 'štvrtok 17:45 objemovci 10 až 12x400m')

    sun = days[6]['blocks'][0]
    check(sun['everyone'] and sun['time'] == '18:00' and len(sun['items']) == 2, 'nedeľa 18:00 všetci, 2 položky')
    check(pt.block_title(thu) == 'objemovci 10 az 12x400m s 1min pauzou', 'názov bloku bez názvu = prvá položka')

    print('\n=== Jednotlivé riadky ===\n')
    c = pt.classify('Drep 5x5')
    check(c['kind'] == 'sila' and c['exercise'] == 'Drep' and c['reps'] == 5 and c['sets'] == 5, 'Drep 5x5')
    c = pt.classify('6x150 m')
    check(c['kind'] == 'beh' and c['reps'] == 6 and c['distance_m'] == 150, '6x150 m')
    c = pt.classify('4x1 km')
    check(c['kind'] == 'beh' and c['reps'] == 4 and c['distance_m'] == 1000, '4x1 km')
    c = pt.classify('2x30 min klus')
    check(c['kind'] == 'ine', '2x30 min nie je séria')
    c = pt.classify('strecing mobilita')
    check(c['kind'] == 'ine' and c['text'] == 'strecing mobilita', 'voľný text ostáva')
    di, rest = pt.day_index('Štvrtok:')
    check(di == 3, 'Štvrtok s diakritikou a dvojbodkou')
    di, rest = pt.day_index('Ne voľno')
    check(di == 6 and 'volno' in rest, 'Ne voľno')
    di, _ = pt.day_index('Stanovisko trénera')
    check(di is None, '„St…“ ako začiatok slova nie je streda')

    print('\n' + ('VŠETKY KONTROLY PREŠLI' if ok else 'NIEKTORÉ KONTROLY ZLYHALI') + '\n')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
