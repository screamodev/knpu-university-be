#!/usr/bin/env python3
"""
Прибрати з сайту документи, які клієнт визнав нечинними (список правок від 17.08.2026).

Два з них лишалися після міграції старого сайту:

* «Методичні рекомендації щодо силабусу навчальних дисциплін» — стояли двома рядками, на
  сторінках центру забезпечення якості освіти («Нормативна база» й «Освітні програми»);
* «Порядок проведення моніторингових досліджень у ХНПУ імені Г.С. Сковороди» — втратив чинність,
  на сайті лишається чинне «Положення про порядок…» з іншим файлом.

Клієнт просив прибрати і рядки, і самі файли з файлосховища. Пошук іде по id файла, а не по id
рядка: рядки `documents` на кожному середовищі свої, а файли лежать під тими самими id (див.
`pass2/files.map.json`).

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_TOKEN=…            # або DIRECTUS_EMAIL / DIRECTUS_PASSWORD
    python3 remove_obsolete_documents.py --dry-run
    python3 remove_obsolete_documents.py

Ідемпотентний: якщо рядків і файлів уже немає, скрипт нічого не робить.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login  # noqa: E402

# id файла → як він зветься у списку правок (для звіту в консоль)
OBSOLETE_FILES = {
    '3338f3dd-a8e4-4c74-aaaf-5a4a5205576e': 'Методичні рекомендації щодо силабусу навчальних дисциплін',
    '0b4782df-6505-4c8b-b22c-d45bdb91681a': 'Порядок проведення моніторингових досліджень',
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    file_ids = ','.join(OBSOLETE_FILES)
    rows = directus.get(
        '/items/documents?limit=-1&fields=id,title,section,file'
        f'&filter[file][_in]={file_ids}'
    ) or []

    for row in rows:
        print(f'- documents {row["id"]} [{row["section"]}] {row["title"][:70]}')
        if not args.dry_run:
            directus.request('DELETE', f'/items/documents/{row["id"]}')

    present = directus.get(f'/files?limit=-1&fields=id,filename_download&filter[id][_in]={file_ids}') or []
    for item in present:
        print(f'- file {item["id"]} {item["filename_download"]}')
        if not args.dry_run:
            directus.request('DELETE', f'/files/{item["id"]}')

    if not rows and not present:
        print('нічого видаляти — уже прибрано.')
    print('готово.' if not args.dry_run else 'сухий прогін — нічого не записано.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f'! {exc.code}: {exc.read().decode("utf-8", "replace")[:500]}', file=sys.stderr)
        raise SystemExit(1)
