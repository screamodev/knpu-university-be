#!/usr/bin/env python3
"""
Залити в Directus матеріали дисциплін вільного вибору магістратури 2026/2028.

Клієнт віддав 119 PDF (опис дисципліни + презентація на кожну) текою на Google Drive, а не
старим сайтом, тож `../pass2/sync_files_map.py` їх не бачить. Тримати ~300 МБ у git теж
немає сенсу, тому тут лежить лише карта: uuid → ім'я файла + його id на Drive. Скрипт сам
качає те, чого немає локально, і заливає під тим самим uuid, під яким `/assets/<uuid>`
вже стоїть у тексті сторінки «Здобувачу» (`app/content/pages/quality-centre-students.uk.json`).

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_TOKEN=…
    python3 push_assets.py --dry-run
    python3 push_assets.py

Ідемпотентний: що вже є на цілі — пропускається, завантажені файли лежать у `files/`
(в .gitignore) і вдруге не качаються.
"""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login, present_file_ids  # noqa: E402
from mirror_page_files import DEFAULT_FOLDER, upload_with_retry  # noqa: E402

HERE = Path(__file__).parent
FILES = HERE / 'files'
FILES_MAP = HERE / 'files.map.json'
UA = 'Mozilla/5.0'


def fetch_from_drive(drive_id: str) -> bytes:
    """
    Один файл із публічної теки. Усе, що більше ~100 МБ, Google віддає не одразу, а через
    сторінку «Virus scan warning» — з неї треба ще раз піти за формою підтвердження.
    """
    url = f'https://drive.google.com/uc?export=download&id={drive_id}'
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=600) as response:
        body = response.read()
    if body[:4] != b'%PDF':
        page = body.decode('utf-8', 'replace')
        form = re.search(r'<form[^>]*action="([^"]+)"[^>]*>(.*?)</form>', page, re.S)
        if not form:
            raise OSError('Drive віддав не PDF і без форми підтвердження')
        fields = {html.unescape(name): html.unescape(value)
                  for name, value in re.findall(r'name="([^"]+)"\s+value="([^"]*)"', form.group(2))}
        confirm = html.unescape(form.group(1)) + '?' + urllib.parse.urlencode(fields)
        request = urllib.request.Request(confirm, headers={'User-Agent': UA})
        with urllib.request.urlopen(request, timeout=600) as response:
            body = response.read()
    if body[:4] != b'%PDF':
        raise OSError('Drive віддав не PDF')
    return body


def local_copy(name: str, drive_id: str) -> bytes:
    path = FILES / name
    if path.exists() and path.stat().st_size > 1024:
        return path.read_bytes()
    content = fetch_from_drive(drive_id)
    FILES.mkdir(exist_ok=True)
    path.write_bytes(content)
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--folder', default=DEFAULT_FOLDER)
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    mapping: dict[str, dict] = json.loads(FILES_MAP.read_text(encoding='utf-8'))

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    present = present_file_ids(directus, mapping.keys())
    todo = [(file_id, meta) for file_id, meta in mapping.items() if file_id not in present]
    print(f'{len(mapping)} у карті · {len(present)} уже на цілі · {len(todo)} залити', file=sys.stderr)
    if args.dry_run or not todo:
        for file_id, meta in todo:
            print(f'  {file_id}  {meta["name"]}')
        return 0

    uploaded = failed = 0
    for file_id, meta in todo:
        name = meta['name']
        try:
            content = local_copy(name, meta['drive_id'])
        except (urllib.error.HTTPError, OSError) as exc:
            print(f'  ! {name}: не завантажився з Drive: {exc}', file=sys.stderr)
            failed += 1
            continue
        content_type = mimetypes.guess_type(name)[0] or 'application/pdf'
        try:
            upload_with_retry(directus, content, name, content_type, args.folder, file_id=file_id)
        except (urllib.error.HTTPError, OSError) as exc:
            print(f'  ! {name}: {exc}', file=sys.stderr)
            failed += 1
            continue
        uploaded += 1
        print(f'  · {uploaded}/{len(todo)} {name}', file=sys.stderr)

    print(f'uploaded={uploaded} failed={failed}', file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
