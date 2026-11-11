#!/usr/bin/env python3
"""
Замінити організаційно-структурну схему на сторінці /university/structure (розділ документів
`university-structure`): стара «станом на 01.10.2026 року» → нова «станом на 05.11.2026 року»
(лист «СТРУКТУРА», В. Плахтєєва, 11.11).

Міняється файл і назва ТОГО САМОГО рядка `documents` (id з проду), тож порядок і розділ лишаються.
Якщо такого рядка на цілі немає (свіжа локальна база) — створюється з тим самим id.
Перед запуском має бути залитий PDF: `push_assets.py`.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 patch_chart.py --dry-run
    python3 patch_chart.py

Ідемпотентний: якщо рядок уже вказує на новий файл і має нову назву — нічого не робить.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login, present_file_ids  # noqa: E402

HERE = Path(__file__).parent
FILES_MAP = HERE / 'files.map.json'

ROW_ID = '0d1c82cb-7456-4373-9b79-1d6b10d02a91'   # рядок схеми на проді
SECTION = 'university-structure'
TITLE = 'Організаційно-структурна схема (станом на 05.11.2026 року)'


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

    mapping: dict[str, dict] = json.loads(FILES_MAP.read_text(encoding='utf-8'))
    (file_id,) = [fid for fid, meta in mapping.items() if meta['name'] == 'struktura-2026-11-05.pdf']

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    if file_id not in present_file_ids(directus, [file_id]):
        print(f'! файла {file_id} ще немає на цілі — спершу push_assets.py', file=sys.stderr)
        return 1

    try:
        row = directus.get(f'/items/documents/{ROW_ID}')
    except urllib.error.HTTPError as exc:
        if exc.code not in (403, 404):
            raise
        row = None

    if row is None:
        print(f'рядка {ROW_ID} немає — створюю з тим самим id', file=sys.stderr)
        payload = {'id': ROW_ID, 'status': 'published', 'section': SECTION, 'title': TITLE,
                   'file': file_id, 'order': 1}
        if not args.dry_run:
            directus.request('POST', '/items/documents', payload)
        return 0

    if row.get('file') == file_id and row.get('title') == TITLE:
        print('уже оновлено — нічого робити', file=sys.stderr)
        return 0

    print(f'було: {row.get("title")!r} · файл {row.get("file")}', file=sys.stderr)
    print(f'буде: {TITLE!r} · файл {file_id}', file=sys.stderr)
    if not args.dry_run:
        directus.request('PATCH', f'/items/documents/{ROW_ID}', {'file': file_id, 'title': TITLE})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
