#!/usr/bin/env python3
"""
Розклад занять дисциплін вільного вибору магістратури (правка 14.09): наявні документи — це
розклад другого року навчання, клієнт попросив так його і підписати. Розклад першого року ще не
надіслали; коли з'являться файли, редактори додадуть їх у той самий розділ із підзаголовком
«Перший рік навчання».

Скрипт ставить підзаголовок (`documents.group`) лише тим документам розділу
`free-choice-master-schedule`, у яких його ще немає. Повторний запуск нічого не міняє.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 group_master_schedule.py --dry-run
    python3 group_master_schedule.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login  # noqa: E402

SECTION = 'free-choice-master-schedule'
GROUP = 'Розклад занять 2-го року навчання'
GROUP_EN = 'Second-year schedule'


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
        f'/items/documents?filter[section][_eq]={SECTION}&fields=id,title,group&limit=-1'
    ) or []
    todo = [row for row in rows if not (row.get('group') or '').strip()]
    print(f'{len(rows)} документів у розділі · {len(todo)} без підзаголовка', file=sys.stderr)
    for row in todo:
        print(f'  ~ {(row.get("title") or "")[:80]}', file=sys.stderr)
        if not args.dry_run:
            directus.request('PATCH', f'/items/documents/{row["id"]}',
                             payload={'group': GROUP, 'groupEn': GROUP_EN})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
