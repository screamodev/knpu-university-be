#!/usr/bin/env python3
"""
Зібрати каталог освітніх програм із перенесеної сторінки центру якості освіти.

Клієнт просив, щоб кожна ОП мала власну сторінку на кшталт `/programs/computer-science-bachelor`,
а не ховалася в довгому списку вкладки «Освітні програми». Матеріал для цього вже перенесений:
`app/content/pages/quality-centre-programmes.uk.json` містить розділи «Освітні програми <рівень>
рівня вищої освіти <рік> року», а в них — блоки виду

    <p><strong>Спеціальність: А1 Освітні науки</strong></p>
    <ul>
      <li><a href="/assets/<uuid>">Освітні науки</a></li>
      <li>Відгуки та пропозиції приймаються на електронну адресу</li>
      <li><strong>liudmila_rybalko@hnpu.edu.ua</strong></li>
    </ul>

Одна ОП зустрічається кілька років поспіль — це версії однієї програми, тож вони збираються в один
запис із переліком років. Результат — `data/programmes.json` для `2_load.py`.

    python3 1_extract.py --dry-run
    python3 1_extract.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / 'data'
SOURCE = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'pages' / 'quality-centre-programmes.uk.json'

LEVELS = {
    'першого': 'bachelor',
    'другого': 'master',
    'третього': 'graduate',
}
SECTION_RE = re.compile(r'Освітні програми (першого|другого|третього)[^\d]*(\d{4}) року')
SPECIALTY_RE = re.compile(r'<p>(?P<head>.*?)</p>\s*<ul>(?P<body>.*?)</ul>', re.S)
SPECIALTY_TEXT_RE = re.compile(r'Спеціальність:\s*(?P<code>[A-ZА-ЯІЇЄҐ]?\d+)?\s*(?P<name>.*)', re.S)
LINK_RE = re.compile(r'<a\s[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<label>.*?)</a>', re.S)
# Подекуди покликання підписане не назвою ОП, а форматом файла — тоді назву дає спеціальність.
JUNK_LABELS = {'pdf', 'doc', 'docx', 'оп', 'опп', 'онп', 'завантажити', 'переглянути'}
ITEM_RE = re.compile(r'<li>(.*?)</li>', re.S)
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
TAGS_RE = re.compile(r'<[^>]+>')

# Транслітерація для slug — та сама таблиця, що в інших модулях міграції.
TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e', 'є': 'ie', 'ж': 'zh',
    'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ь': '', 'ю': 'iu', 'я': 'ia', '’': '', '\'': '',
}
LEVEL_SUFFIX = {'bachelor': 'bachelor', 'master': 'master', 'graduate': 'phd'}


def plain(markup: str) -> str:
    text = TAGS_RE.sub('', markup)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    return re.sub(r'\s+', ' ', text).strip()


CODE_PREFIX_RE = re.compile(r'^\s*(?:[A-ZА-ЯІЇЄҐ]?\s*\d+[.)]?\s*)+', re.I)


def specialty_key(name: str) -> str:
    """
    Назва спеціальності без кодів: у 2023 роках писали «012 Дошкільна освіта», у 2026 — «А2 07
    Дошкільна освіта». Це та сама спеціальність, і програми під нею не можна розводити на два
    записи лише через зміну нумерації МОН.
    """
    return CODE_PREFIX_RE.sub('', name).strip(' .').lower()


def slugify(value: str) -> str:
    value = unicodedata.normalize('NFC', value.lower())
    out = ''.join(TRANSLIT.get(char, char) for char in value)
    out = re.sub(r'[^a-z0-9]+', '-', out).strip('-')
    return re.sub(r'-{2,}', '-', out)[:80]


def sections(node, found=None) -> list[dict]:
    """Сторінка — дерево розділів; збираємо всі, що мають html."""
    found = [] if found is None else found
    if isinstance(node, dict):
        if node.get('html'):
            found.append(node)
        for key, value in node.items():
            if key != 'html':
                sections(value, found)
    elif isinstance(node, list):
        for item in node:
            sections(item, found)
    return found


def programmes_of(html: str) -> list[dict]:
    """Блоки «Спеціальність … → перелік ОП» одного року."""
    result = []
    for match in SPECIALTY_RE.finditer(html):
        head = plain(match.group('head'))
        if 'спеціальність' not in head.lower():
            continue
        parsed = SPECIALTY_TEXT_RE.search(head)
        if not parsed:
            continue
        specialty_code = (parsed.group('code') or '').strip()
        specialty_name = plain(parsed.group('name')).strip(' .')

        body = match.group('body')
        email = ''
        titles: list[tuple[str, str]] = []
        for item in ITEM_RE.findall(body):
            for link in LINK_RE.finditer(item):
                href, label = link.group('href'), plain(link.group('label'))
                if href.startswith('mailto:'):
                    email = email or href[len('mailto:'):]
                elif href.startswith('/assets/') and label:
                    titles.append((label, href))
            found = EMAIL_RE.search(plain(item))
            if found and not email:
                email = found.group(0)

        for title, href in titles:
            title = title.strip(' .')
            if title.lower().strip(' .()') in JUNK_LABELS:
                title = specialty_name
            result.append({
                'title': title,
                'file': href,
                'specialty': f'{specialty_code} {specialty_name}'.strip(),
                # Коди спеціальностей МОН змінилися (012 → А2), а назва лишилася — ключ по ній.
                'specialtyName': specialty_name,
                'email': email,
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', default=str(SOURCE))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    page = json.loads(Path(args.source).read_text(encoding='utf-8'))
    catalogue: OrderedDict[tuple[str, str], dict] = OrderedDict()

    for section in sections(page):
        match = SECTION_RE.search(section.get('heading') or '')
        if not match:
            continue
        level, year = LEVELS[match.group(1)], int(match.group(2))
        for entry in programmes_of(section['html']):
            # Ключ — рівень і назва програми: спеціальність під нею з роками перейменовували
            # («Середня освіта (Історія)» → «…(Історія та громадянська освіта)»), і це не привід
            # заводити другу сторінку тій самій ОП.
            key = (level, entry['title'].lower())
            record = catalogue.setdefault(key, {
                'slug': '',
                'title': entry['title'],
                'level': level,
                'specialty': entry['specialty'],
                'email': entry['email'],
                'versions': [],
                'status': 'published',
            })
            record['versions'].append({'year': year, 'file': entry['file'],
                                       'specialty': entry['specialty']})
            record['email'] = entry['email'] or record['email']

    rows = []
    used: set[str] = set()
    for record in catalogue.values():
        record['versions'].sort(key=lambda version: version['year'], reverse=True)
        # Спеціальність показуємо ту, під якою програма йде в найновішій редакції.
        record['specialty'] = record['versions'][0]['specialty']
        slug = f"{slugify(record['title'])}-{LEVEL_SUFFIX[record['level']]}"
        while slug in used:                     # одна назва на двох спеціальностях трапляється
            slug += '-2'
        used.add(slug)
        record['slug'] = slug
        rows.append(record)

    per_level = {level: sum(1 for row in rows if row['level'] == level)
                 for level in ('bachelor', 'master', 'graduate')}
    print(f'{len(rows)} програм: {per_level}', file=sys.stderr)
    if args.dry_run:
        for row in rows[:10]:
            years = ', '.join(str(version['year']) for version in row['versions'])
            print(f'  {row["slug"]:<50} {row["level"]:<9} {years}', file=sys.stderr)
        return 0

    DATA.mkdir(exist_ok=True)
    target = DATA / 'programmes.json'
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'→ {target}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
