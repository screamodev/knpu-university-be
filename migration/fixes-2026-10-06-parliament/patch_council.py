#!/usr/bin/env python3
"""
Правки 06.10 (Студентський Парламент): новий логотип і заміна двох PDF.

* `student_council_info.emblem` → новий логотип (`student-parliament-logo.png`);
* документи розділу `student-council` «Контакти студентського самоврядування» і «Голови
  факультетів» отримують новий файл, решта полів документа не міняється.

Спершу `push_assets.py` — файли мають бути вже на цілі. Ідемпотентний: те, що вже вказує на
новий файл, пропускається.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 patch_council.py --dry-run
    python3 patch_council.py
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from bundle import file_id  # noqa: E402
from common import Directus, login  # noqa: E402

LOGO_ID = file_id('student-parliament-logo.png')
# id рядків `documents` на проді (вони ж на локалі після `pass2/load.py`).
DOCUMENTS = {
    '1a5cdd86-2466-4d94-aed5-dd7cd1461b73': ('Контакти студентського самоврядування',
                                             file_id('kontakty-studentskoho-samovriaduvannia.pdf')),
    '2bfb3861-b42d-4401-b9eb-78e1b49c1f13': ('Голови факультетів',
                                             file_id('holovy-fakultetiv.pdf')),
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

    info = directus.get('/items/student_council_info') or {}
    if current_id(info.get('emblem')) == LOGO_ID:
        print('емблема: вже новий логотип')
    else:
        print(f'емблема: {current_id(info.get("emblem"))} → {LOGO_ID}')
        if not args.dry_run:
            directus.request('PATCH', '/items/student_council_info', payload={'emblem': LOGO_ID})

    for doc_id, (title, new_file) in DOCUMENTS.items():
        try:
            row = directus.get(f'/items/documents/{doc_id}')
        except urllib.error.HTTPError as exc:
            # Directus відповідає 403 і на запис, якого немає (порожня локальна база).
            if exc.code not in (403, 404):
                raise
            row = None
        if not row:
            print(f'! «{title}»: рядка {doc_id} немає на цій цілі — пропущено', file=sys.stderr)
            continue
        if current_id(row.get('file')) == new_file:
            print(f'«{title}»: вже новий файл')
            continue
        print(f'«{title}»: {current_id(row.get("file"))} → {new_file}')
        if not args.dry_run:
            directus.request('PATCH', f'/items/documents/{doc_id}', payload={'file': new_file})

    print('dry run — nothing written.' if args.dry_run else 'done.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
