#!/usr/bin/env python3
"""
Точкові правки у вкладках підрозділів, які редактори вже ведуть в адмінці (`structure_pages`).

Для таких вкладок статичний JSON фронту — лише запасний варіант, тож правку треба внести і в
рядок Directus. Кожна правка — заміна одного фрагмента: якщо фрагмента вже немає, а нового
тексту ще немає — скрипт повідомляє й нічого не пише (редактор міг переписати абзац).
Повторний запуск нічого не міняє.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 patch_structure_pages.py --dry-run
    python3 patch_structure_pages.py
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login  # noqa: E402

# (підрозділ, вкладка, було, стало)
PATCHES = [
    # Правка 16.09, п. 18: «Аспіранти-іноземні громадяни» веде на окрему сторінку.
    (
        'postgraduate', 'students',
        '<p><strong>Аспіранти-іноземні громадяни</strong></p>',
        '<p><strong><a href="/university/structure/postgraduate-foreign-students">'
        'Аспіранти-іноземні громадяни</a></strong></p>',
    ),
    # Правки аспірантури (17.09): «Аспіранти-громадяни України» — окрема сторінка…
    (
        'postgraduate', 'students',
        '<p><strong>Аспіранти-громадяни України</strong></p>',
        '<p><strong><a href="/university/structure/postgraduate-ukrainian-students">'
        'Аспіранти-громадяни України</a></strong></p>',
    ),
    # …а «Дисципліни вільного вибору» з вкладки прибрати.
    (
        'postgraduate', 'students',
        '<p><strong><a href="/education/quality?tab=students">Дисципліни вільного вибору</a></strong></p>\n',
        '',
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directus-url',
                        default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    failed = 0
    for unit, tab, old, new in PATCHES:
        query = urllib.parse.urlencode({
            'filter[unit_slug][_eq]': unit, 'filter[tab][_eq]': tab, 'fields': 'id,body', 'limit': 1,
        })
        rows = directus.get(f'/items/structure_pages?{query}') or []
        if not rows:
            print(f'  = {unit}/{tab}: рядка в адмінці немає, сайт бере статичний JSON', file=sys.stderr)
            continue
        row = rows[0]
        body = row.get('body') or ''
        if (new and new in body) or (not new and old not in body):
            print(f'  = {unit}/{tab}: уже виправлено', file=sys.stderr)
            continue
        if body.count(old) != 1:
            print(f'  ! {unit}/{tab}: фрагмент не знайдено ({body.count(old)} збігів) — виправте вручну',
                  file=sys.stderr)
            failed += 1
            continue
        print(f'  ~ {unit}/{tab}', file=sys.stderr)
        if not args.dry_run:
            directus.request('PATCH', f'/items/structure_pages/{row["id"]}',
                             payload={'body': body.replace(old, new)})
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
