#!/usr/bin/env python3
"""
Розкласти документи графіка освітнього процесу по підзаголовках.

Клієнт попросив, щоб `/education/schedule` читався не одним списком, а розділами за формою
навчання: спершу денна, потім заочна (вечірню додадуть, коли навчальний відділ надішле
графік), накази — окремим блоком у кінці. Підзаголовок живе в полі `documents.group`, тож далі
редактор міняє його сам в адмінці.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_TOKEN=…
    python3 set_schedule_groups.py --dry-run
    python3 set_schedule_groups.py

Ідемпотентний: рядок, у якого потрібне значення вже стоїть, пропускається.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login  # noqa: E402

SECTION = 'education-schedule'

DAY = ('Денна форма', 'Full-time')
PART_TIME = ('Заочна форма', 'Part-time')
ORDERS = ('Накази', 'Orders')


def group_for(title: str) -> tuple[str, str] | None:
    lowered = title.lower()
    if lowered.startswith('наказ'):
        return ORDERS
    if 'заочн' in lowered:
        return PART_TIME
    if 'графік освітнього процесу' in lowered:
        return DAY
    return None


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

    rows = directus.get(
        f'/items/documents?limit=-1&fields=id,title,order,group,groupEn'
        f'&filter[section][_eq]={SECTION}') or []
    if not rows:
        print(f'! у розділі {SECTION} немає рядків — нічого робити', file=sys.stderr)
        return 1

    changed = skipped = unknown = 0
    for row in sorted(rows, key=lambda item: (item.get('order') or 0, item['title'])):
        pair = group_for(row['title'])
        if pair is None:
            unknown += 1
            print(f'  ? без підзаголовка: {row["title"][:70]}')
            continue
        group, group_en = pair
        if row.get('group') == group and row.get('groupEn') == group_en:
            skipped += 1
            continue
        print(f'  → {group}: {row["title"][:70]}')
        changed += 1
        if not args.dry_run:
            directus.request('PATCH', f'/items/documents/{row["id"]}',
                             payload={'group': group, 'groupEn': group_en})

    print(f'changed={changed} skipped={skipped} unknown={unknown}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
