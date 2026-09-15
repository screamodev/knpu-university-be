#!/usr/bin/env python3
"""
Замінити байти вже залитих файлів (правка 15.09): Центр якості освіти надіслав виправлену версію
результатів анкети № 6 за ОП «Тифлопедагогіка. Сурдопедагогіка» 2026 року.

Файл лишається з тим самим uuid (`files.map.json`), тож посилання `/assets/<uuid>` на сторінці
«Якість освіти» не міняються і фронт перезбирати не треба. Скрипт шле нові байти в
`PATCH /files/<uuid>` лише тоді, коли розмір файла на цілі відрізняється від того, що в `files/`;
повторний запуск нічого не міняє. Якщо файла на цілі ще немає — заливає його з цим uuid.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 replace_assets.py --dry-run
    python3 replace_assets.py
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login, present_file_ids  # noqa: E402
from mirror_page_files import DEFAULT_FOLDER, upload_with_retry  # noqa: E402

HERE = Path(__file__).parent
FILES = HERE / 'files'
FILES_MAP = HERE / 'files.map.json'


def replace(directus: Directus, file_id: str, content: bytes, filename: str) -> None:
    content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    boundary = f'----knpu{uuid.uuid4().hex}'
    body = b''.join([
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'.encode(),
        content,
        f'\r\n--{boundary}--\r\n'.encode(),
    ])
    directus.request('PATCH', f'/files/{file_id}', raw=body,
                     content_type=f'multipart/form-data; boundary={boundary}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--folder', default=DEFAULT_FOLDER)
    parser.add_argument('--directus-url',
                        default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    mapping: dict[str, dict] = json.loads(FILES_MAP.read_text(encoding='utf-8'))
    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)
    present = present_file_ids(directus, mapping.keys())

    failed = 0
    for file_id, meta in mapping.items():
        name = meta['name']
        path = FILES / name
        if not path.exists():
            print(f'  ! {name}: файл має лежати в files/, а його там немає', file=sys.stderr)
            failed += 1
            continue
        content = path.read_bytes()

        if file_id not in present:
            print(f'  + {name}: на цілі немає, заливаю', file=sys.stderr)
            if not args.dry_run:
                upload_with_retry(directus, content, name,
                                  mimetypes.guess_type(name)[0] or 'application/octet-stream',
                                  args.folder, file_id=file_id)
            continue

        current = directus.get(f'/files/{file_id}?fields=filesize') or {}
        if int(current.get('filesize') or 0) == len(content):
            print(f'  = {name}: уже нова версія ({len(content)} байт)', file=sys.stderr)
            continue
        print(f'  ~ {name}: {current.get("filesize")} → {len(content)} байт', file=sys.stderr)
        if not args.dry_run:
            replace(directus, file_id, content, name)

    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
