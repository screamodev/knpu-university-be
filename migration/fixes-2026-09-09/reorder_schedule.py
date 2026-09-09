#!/usr/bin/env python3
"""
Поставити заочну форму в кінець списку графіка освітнього процесу.

Після 08.09 список на /education/schedule розбитий підзаголовками (поле `documents.group`),
але порядок лишився старий: заочний графік стояв між денною формою й наказами. Клієнт попросив
09.09 опустити його вниз, після наказів.

Скрипт перенумеровує `order` у розділі `education-schedule` за порядком груп:

    Денна форма → Накази → Заочна форма → усе інше

Всередині групи зберігається наявний порядок (order, далі дата). Ідемпотентний: якщо номери
вже такі, нічого не пишеться.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 reorder_schedule.py --dry-run
    python3 reorder_schedule.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login  # noqa: E402

SECTION = 'education-schedule'
GROUP_ORDER = ['Денна форма', 'Накази', 'Заочна форма']


def group_rank(group: str | None) -> int:
    name = (group or '').strip()
    return GROUP_ORDER.index(name) if name in GROUP_ORDER else len(GROUP_ORDER)


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
        f'/items/documents?limit=-1&fields=id,title,order,group,documentDate,status'
        f'&filter[section][_eq]={SECTION}') or []
    live = [row for row in rows if row.get('status') == 'published']
    if not live:
        print(f'! у розділі {SECTION} немає опублікованих рядків', file=sys.stderr)
        return 1

    live.sort(key=lambda row: (group_rank(row.get('group')),
                               row.get('order') or 0,
                               row.get('documentDate') or ''))

    changed = skipped = 0
    for position, row in enumerate(live, start=1):
        if row.get('order') == position:
            skipped += 1
            continue
        print(f'  {row.get("order")} → {position}  [{row.get("group") or "—"}] {row["title"][:60]}')
        changed += 1
        if not args.dry_run:
            directus.request('PATCH', f'/items/documents/{row["id"]}', payload={'order': position})

    print(f'changed={changed} skipped={skipped}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
