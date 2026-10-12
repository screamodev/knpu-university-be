#!/usr/bin/env python3
"""
Правка 12.10, п. 5: у розділі «Освітня екосистема» на /education/monitoring видалити з АНКЕТИ № 1
вкладену «Анкету по факультетам» — заголовок `1/0` і 10 вкладених анкет `1/1…1/10`
(створені бандлом fixes-2026-09-30). Сама анкета № 1 не чіпається.

Рядки шукаються за парою (number, title) з fixes-2026-09-30/data/monitoring-faculties.json,
тож скрипт однаково працює на локальній базі й на проді (id там різні). Рядок із результатами
або з файлом програми не видаляється — скрипт зупиняється з кодом 1.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 delete_monitoring_faculties.py --dry-run
    python3 delete_monitoring_faculties.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / 'fixes-2026-09-30' / 'data' / 'monitoring-faculties.json'


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

    expected = {row['number']: row['title']
                for batch in json.loads(DATA.read_text(encoding='utf-8'))['batches']
                for row in batch['rows']}

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    query = urllib.parse.urlencode({
        'filter[area][_eq]': 'educational-ecosystem',
        'filter[number][_in]': ','.join(expected),
        'fields': 'id,number,title,programmeFile,results.id',
        'limit': -1,
        'sort': 'order',
    })
    found = directus.get(f'/items/monitoring_surveys?{query}') or []

    todo = []
    for row in found:
        if row['title'] != expected[row['number']]:
            print(f'! {row["number"]} {row["title"]!r}: назва не збігається з бандлом 09-30, пропущено',
                  file=sys.stderr)
            return 1
        if row.get('results') or row.get('programmeFile'):
            print(f'! {row["number"]} {row["title"]!r}: є результати або файл програми, '
                  'перевірте вручну', file=sys.stderr)
            return 1
        todo.append(row)

    present = {row['number'] for row in todo}
    for number in expected:
        if number not in present:
            print(f'= {number} {expected[number]}: вже видалено', file=sys.stderr)

    for row in todo:
        print(f'- {row["number"]} {row["title"]}  ({row["id"]})', file=sys.stderr)
        if not args.dry_run:
            directus.request('DELETE', f'/items/monitoring_surveys/{row["id"]}')

    print(f'{"до видалення" if args.dry_run else "видалено"}: {len(todo)}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
