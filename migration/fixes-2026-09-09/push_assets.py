#!/usr/bin/env python3
"""
Залити файли правок 09.09: документи спеціалізованої вченої ради Д 64.053.08 і фотографії
для сторінок історії, гуртожитків, галереї, мистецьких колективів та асоціації випускників.

Дві категорії файлів:

* документи ради — публічні теки на Google Drive, у карті стоїть `drive_id`, скрипт качає їх
  сам і кладе поруч у `files/` (PDF у .gitignore);
* фотографії — вже зменшені до вебформату (довша сторона 2000 px, JPEG). Оригінали на Drive
  важать 230 МБ, тож качати їх під час деплою немає сенсу: байти лежать у `files/` в git.

uuid кожного файла детермінований (uuid5 від імені), тож `/assets/<uuid>` у текстах сторінок
збігається на локалі й на проді.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 push_assets.py --dry-run
    python3 push_assets.py

Ідемпотентний: те, що вже є на цілі, пропускається.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
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
    url = f'https://drive.usercontent.google.com/download?id={drive_id}&export=download'
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=600) as response:
        body = response.read()
    if body[:4] != b'%PDF':
        raise OSError('Drive віддав не PDF — імовірно, теку закрили')
    return body


def local_copy(name: str, drive_id: str | None) -> bytes:
    path = FILES / name
    if path.exists() and path.stat().st_size > 1024:
        return path.read_bytes()
    if not drive_id:
        raise OSError(f'{name}: файл має лежати в files/, а його там немає')
    content = fetch_from_drive(drive_id)
    FILES.mkdir(exist_ok=True)
    path.write_bytes(content)
    return content


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
    todo = [(file_id, meta) for file_id, meta in mapping.items() if file_id not in present]
    print(f'{len(mapping)} у карті · {len(present)} уже на цілі · {len(todo)} залити',
          file=sys.stderr)
    if args.dry_run or not todo:
        for file_id, meta in todo:
            print(f'  {file_id}  {meta["name"]}')
        return 0

    uploaded = failed = 0
    for file_id, meta in todo:
        name = meta['name']
        try:
            content = local_copy(name, meta.get('drive_id'))
        except (urllib.error.HTTPError, OSError) as exc:
            print(f'  ! {name}: {exc}', file=sys.stderr)
            failed += 1
            continue
        content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
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
