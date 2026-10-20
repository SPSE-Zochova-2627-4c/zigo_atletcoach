# -*- coding: utf-8 -*-
"""
plan_text.py
============
Rozbor týždenného plánu, ako ho tréner píše do správy – voľný text bez dátumov:

    Pondelok
    15:00 novy sprint rozcvicenie od A do Z
    kontrolny start na 150m
    16:00 objemovci
    30 az 40x 26,5m kopec
    Marsal Mandak 3x3x26,5m na 92%
    Utorok
    17:00 objemovci
    Tlaky na ramená s veľkou osou v stoji 10x2
    Bulharské drepy 8a8x2
    ...
    Sobota volno

Výstup je strom deň → blok (čas, skupina / mená) → položky (cvik, beh, iné),
z ktorého si tréner v náhľade odklikne, komu čo patrí.  Všetko je bez AI a bez
Flasku, aby sa to dalo otestovať samostatne (test_plan_text.py) a aby bol
výsledok vždy rovnaký.

Pravidlá:
  * riadok, ktorý začína názvom dňa (aj bez diakritiky: „Stvrtok“, „Nedela“,
    skratky Po/Ut/St/Št/Pi/So/Ne), otvára deň; „volno“ za názvom = voľný deň,
  * riadok s časom „15:00“ otvára blok; zvyšok riadku je názov bloku,
  * skupiny („objemovci“, „všetci“) a mená / prezývky zverencov sa hľadajú v
    názve bloku aj v položkách; riadok len s menom a výkonom je vlastný blok,
  * „10x2“, „8a8x2“ → sila (opakovania × série, „a“ = na každú stranu),
    „30 az 40x 26,5m“, „3x3x26,5m na 92%“, „10 az 12x400m“ → beh,
    ostatné → iné (ostáva ako text).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

DAYS = ['pondelok', 'utorok', 'streda', 'stvrtok', 'piatok', 'sobota', 'nedela']
DAY_SHORT = {'po': 0, 'ut': 1, 'st': 2, 'stv': 3, 'pi': 4, 'so': 5, 'ne': 6}
ALL_WORDS = ('vsetci', 'vsetky', 'kazdy', 'cela skupina', 'vsetci spolu')
REST_WORDS = ('volno', 'volne', 'pauza', 'oddych', 'regeneracia')

RE_TIME = re.compile(r'^(\d{1,2})[:.](\d{2})\b\s*(.*)$')
# „10x2“, „8a8x2“, „12x10“ – ale nie „30 az 40x 26,5m“ (za x nasleduje vzdialenosť v m)
RE_SETS = re.compile(r'(?<![\d,.])(\d+)(?:a(\d+))?\s*x\s*(\d+)(?!\s*[,.]?\d*\s*m\b)(?!\s*x)')
# „30 az 40x 26,5m“, „3x3x26,5m“, „10 az 12x400m“, „6x150 m“
RE_RUN = re.compile(r'(\d+)(?:\s*(?:az|-|–|do)\s*(\d+))?\s*x\s*(?:(\d+)\s*x\s*)?(\d+(?:[,.]\d+)?)\s*m\b')
RE_PCT = re.compile(r'(\d{2,3})\s*%')
RE_KM = re.compile(r'(\d+)\s*x\s*(\d+(?:[,.]\d+)?)\s*km\b')
RE_MIN = re.compile(r'\d\s*x\s*\d+\s*min\b')
RE_DIST = re.compile(r'(?:na|z)\s*(\d+)\s*m\b')


def norm(text: str) -> str:
    """Bez diakritiky, malé písmená, orezané – na porovnávanie."""
    text = unicodedata.normalize('NFKD', text or '')
    return ''.join(c for c in text if not unicodedata.combining(c)).lower().strip()


def day_index(line: str) -> Tuple[Optional[int], str]:
    """(index dňa 0–6, zvyšok riadku) ak riadok otvára deň, inak (None, '')."""
    words = norm(line).rstrip(':').split()
    if not words:
        return None, ''
    head = words[0].rstrip(':.,')
    if head in DAYS:
        return DAYS.index(head), ' '.join(words[1:])
    if head in DAY_SHORT and len(words) <= 2:
        return DAY_SHORT[head], ' '.join(words[1:])
    return None, ''


def classify(line: str) -> Dict[str, Any]:
    """Riadok plánu → položka {kind, text, exercise?, reps?, sets?, distance_m?, ...}."""
    raw = line.strip()
    n = norm(raw)
    item: Dict[str, Any] = {'kind': 'ine', 'text': raw[:200]}
    km = RE_KM.search(n)
    if km:
        reps, dist_km = km.groups()
        item.update(kind='beh', reps=int(reps), reps_max=None, sets=None,
                    distance_m=float(dist_km.replace(',', '.')) * 1000)
        return item
    if RE_MIN.search(n):
        return item                     # „2x30 min“ – čas, nie série; ostáva ako text
    m = RE_RUN.search(n)
    if m:
        lo, hi, sets, dist = m.groups()
        item.update(kind='beh', reps=int(lo), reps_max=int(hi) if hi else None,
                    sets=int(sets) if sets else None,
                    distance_m=float(dist.replace(',', '.')))
        p = RE_PCT.search(n)
        if p:
            item['intensity_pct'] = int(p.group(1))
        return item
    m = RE_SETS.search(n)
    if m:
        reps, per_side, sets = m.groups()
        exercise = raw[:m.start()].strip(' -–:·') or raw
        item.update(kind='sila', exercise=exercise[:120], reps=int(reps),
                    per_side=bool(per_side), sets=int(sets))
        return item
    d = RE_DIST.search(n)
    if d:
        item.update(kind='beh', distance_m=float(d.group(1)))
        return item
    return item


class Matcher:
    """
    Hľadá v riadku skupiny a ľudí.  `groups` = {normalizovaný názov: pôvodný názov},
    `people` = [(id, [varianty mena])] – prezývka, krstné meno, priezvisko, username.
    """

    def __init__(self, groups: Dict[str, str], people: Sequence[Tuple[Any, Sequence[str]]]):
        self.groups = {norm(k): v for k, v in groups.items() if k}
        self.people = []
        for pid, names in people:
            variants = {norm(x) for x in names if x and len(norm(x)) >= 3}
            self.people.append((pid, variants))

    def find(self, line: str) -> Tuple[List[str], List[Any], bool]:
        n = norm(line)
        padded = f' {n} '
        groups = [orig for key, orig in self.groups.items() if f' {key} ' in padded]
        everyone = any(f' {w} ' in padded for w in ALL_WORDS)
        people = [pid for pid, variants in self.people
                  if any(re.search(r'(?<![\w])' + re.escape(v) + r'(?![\w])', n) for v in variants)]
        return groups, people, everyone


def parse(text: str, matcher: Optional[Matcher] = None) -> Dict[str, Any]:
    """Text plánu → {'intro': [riadky pred prvým dňom], 'days': [...]}."""
    matcher = matcher or Matcher({}, [])
    intro: List[str] = []
    days: List[Dict[str, Any]] = []
    cur_day: Optional[Dict[str, Any]] = None
    cur_block: Optional[Dict[str, Any]] = None

    def new_block(time_text, title, groups, people, everyone):
        blk = {'time': time_text, 'title': (title or '').strip()[:160] or None,
               'groups': groups, 'people': people, 'everyone': everyone, 'items': []}
        cur_day['blocks'].append(blk)
        return blk

    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        di, rest = day_index(line)
        if di is not None:
            cur_day = {'day': di, 'rest': any(w in rest for w in REST_WORDS), 'note': rest or None,
                       'blocks': []}
            days.append(cur_day)
            cur_block = None
            continue
        if cur_day is None:
            intro.append(line)
            continue
        t = RE_TIME.match(line)
        if t:
            hh, mm, rest = t.groups()
            if 0 <= int(hh) < 24 and 0 <= int(mm) < 60:
                groups, people, everyone = matcher.find(rest)
                cur_block = new_block(f'{int(hh):02d}:{mm}', rest, groups, people, everyone)
                # „16:00 strecing mobilita“ – názov bez skupiny je zároveň prvá položka
                if rest.strip() and not groups and not people and not everyone:
                    cur_block['items'].append(classify(rest))
                continue
        groups, people, everyone = matcher.find(line)
        if people and (cur_block is None or set(cur_block['people']) != set(people)):
            # riadok pre konkrétnych ľudí („Marsal Mandak 3x3x26,5m“) = vlastný blok
            cur_block = new_block(None, line, groups, people, everyone)
            cur_block['items'].append(classify(line))
            continue
        if cur_block is None:
            cur_block = new_block(None, None, groups, people, everyone)
        if groups and not cur_block['groups']:
            cur_block['groups'] = groups
        if everyone:
            cur_block['everyone'] = True
        # riadok, ktorý je len názov skupiny („objemovci“), nie je položka
        if norm(line) in {norm(g) for g in groups} and not cur_block['title']:
            cur_block['title'] = line
            continue
        cur_block['items'].append(classify(line))
    return {'intro': intro, 'days': days}


def block_title(block: Dict[str, Any]) -> str:
    """Názov tréningu do kalendára: názov bloku, inak prvá položka, inak „Tréning“."""
    if block.get('title'):
        return block['title']
    if block.get('items'):
        return block['items'][0]['text']
    return 'Tréning'
