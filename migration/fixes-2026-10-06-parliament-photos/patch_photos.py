#!/usr/bin/env python3
"""
Правки 06.10 (Студентський Парламент): фото голів студентських рад факультетів.

Портрети вирізані з PDF «Голови факультетів» (по одному на слайд, підписи під фото
визначають, хто є хто). `pass2/load.py` вже створених людей не оновлює, тому поле `photo`
проставляє цей скрипт за парою «група + ПІБ». Людей, яких немає на цілі, пропускає з
попередженням; уже проставлене те саме фото не чіпає.

Спершу `push_assets.py` — файли мають бути вже на цілі.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 patch_photos.py --dry-run
    python3 patch_photos.py
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from bundle import file_id  # noqa: E402
from common import Directus, login  # noqa: E402

GROUP = 'faculty-chair'
PHOTOS = {
    'Гусак Ольга Віталіївна': 'parliament-husak.jpg',
    'Мукієнко Руф Михайлівна': 'parliament-mukienko.jpg',
    'Стадник Анастасія Олексіївна': 'parliament-stadnyk.jpg',
    'Коваленко Єлизавета Миколаївна': 'parliament-kovalenko-yelyzaveta.jpg',
    'Ємельянова Вероніка Едуардівна': 'parliament-yemelianova.jpg',
    'Мовчан Анна Миколаївна': 'parliament-movchan.jpg',
    'Бабич Марія Олександрівна': 'parliament-babych.jpg',
    'Коваленко Дарина Сергіївна': 'parliament-kovalenko-daryna.jpg',
    'Бурсала Тимур Дмитрович': 'parliament-bursala.jpg',
    'Табах Софія Валеріївна': 'parliament-tabakh.jpg',
}


def current_id(value) -> str | None:
    return value.get('id') if isinstance(value, dict) else value


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

    updated = skipped = missing = 0
    for name, filename in PHOTOS.items():
        query = urllib.parse.urlencode({
            'filter[group][_eq]': GROUP, 'filter[name][_eq]': name, 'fields': 'id,photo', 'limit': 1,
        })
        rows = directus.get(f'/items/student_council_members?{query}') or []
        if not rows:
            print(f'! {name}: немає на цій цілі — пропущено', file=sys.stderr)
            missing += 1
            continue
        row, target = rows[0], file_id(filename)
        if current_id(row.get('photo')) == target:
            skipped += 1
            continue
        print(f'{name}: {current_id(row.get("photo"))} → {target}')
        if not args.dry_run:
            directus.request('PATCH', f'/items/student_council_members/{row["id"]}',
                             payload={'photo': target})
        updated += 1

    print(f'{"dry run — " if args.dry_run else ""}оновлено={updated} уже стоїть={skipped} немає={missing}')
    return 1 if missing else 0


if __name__ == '__main__':
    raise SystemExit(main())
