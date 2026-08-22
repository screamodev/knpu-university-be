#!/usr/bin/env python3
"""
Залити в Directus файли, яких немає де взяти під час деплою.

Решта міграції качає файли зі старого сайту, тож на будь-якому середовищі їх можна взяти з
першоджерела (`../pass2/sync_files_map.py`). Тут лежать ті, з якими так не вийде: матеріали з
теки на Google Drive, доступної лише під обліковим записом університету, і кілька файлів зі
старого сайту, який то падає, то піднімається, — качати їх під час деплою ризиковано. Усі вони
лежать поруч, у `files/`, а карта `files.map.json` тримає uuid, під яким кожен уже стоїть у
текстах сторінок.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_TOKEN=…
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login, present_file_ids  # noqa: E402
from mirror_page_files import DEFAULT_FOLDER, upload_with_retry  # noqa: E402

HERE = Path(__file__).parent
FILES = HERE / 'files'
FILES_MAP = HERE / 'files.map.json'


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

    mapping: dict[str, str] = json.loads(FILES_MAP.read_text(encoding='utf-8'))
    missing = [name for name in mapping.values() if not (FILES / name).exists()]
    if missing:
        print('немає поруч із картою: ' + ', '.join(missing), file=sys.stderr)
        return 1

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    present = present_file_ids(directus, mapping.keys())
    todo = [(file_id, name) for file_id, name in mapping.items() if file_id not in present]
    print(f'{len(mapping)} у карті · {len(present)} уже на цілі · {len(todo)} залити', file=sys.stderr)
    if args.dry_run or not todo:
        for file_id, name in todo:
            print(f'  {file_id}  {name}')
        return 0

    uploaded = failed = 0
    for file_id, name in todo:
        content = (FILES / name).read_bytes()
        content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        try:
            upload_with_retry(directus, content, name, content_type, args.folder, file_id=file_id)
        except (urllib.error.HTTPError, OSError) as exc:
            print(f'  ! {name}: {exc}', file=sys.stderr)
            failed += 1
            continue
        uploaded += 1

    print(f'uploaded={uploaded} failed={failed}', file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
