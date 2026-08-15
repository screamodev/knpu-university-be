#!/usr/bin/env python3
"""
Залити на цільовий Directus файли, перелічені в карті, під тими самими uuid.

`mirror_page_files.py` качає файли з адрес, які ще лишилися в текстах. Але після мірроринга в
контенті стоїть уже `/assets/<uuid>` — тож на новому середовищі качати нема з чого, і покликання
віддають 404, хоча самі uuid у контенті правильні.

Цей скрипт іде з іншого боку: бере `files.map.json` (джерело → uuid), питає в цільового Directus,
яких ідентифікаторів там немає, і довантажує їх із першоджерела **під тим самим uuid**. Тому
статичний контент фронтенду працює однаково локально й на проді.

    export DIRECTUS_URL=http://knpu-university-directus:8055
    export DIRECTUS_TOKEN=…
    python3 sync_files_map.py --dry-run
    python3 sync_files_map.py                       # pass2/files.map.json
    python3 sync_files_map.py --map ../smc/images.map.json
    python3 sync_files_map.py --map ../razovi-rady/files.map.json --folder <uuid>

Ідемпотентний і резюмиться: те, що вже є на цілі, пропускається. Джерела, яких старий сайт більше
не віддає, лишаються незалитими — вони перелічені наприкінці.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
from pathlib import Path

from common import Directus, download, filename_for, login, present_file_ids
from mirror_page_files import DEFAULT_FOLDER, upload_with_retry

HERE = Path(__file__).parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--map', default=str(HERE / 'files.map.json'))
    parser.add_argument('--by-id', action='store_true',
                        help='карта записана навпаки, uuid → джерело (одне джерело під кількома '
                             'uuid, як у ../admissions/data/images.map.json)')
    parser.add_argument('--folder', default=DEFAULT_FOLDER)
    parser.add_argument('--limit', type=int, help='зупинитися після стількох завантажень')
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    mapping: dict[str, str] = json.loads(Path(args.map).read_text(encoding='utf-8'))
    if args.by_id:
        pairs = [(source, file_id) for file_id, source in mapping.items()]
    else:
        pairs = list(mapping.items())

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    present = present_file_ids(directus, [file_id for _, file_id in pairs])
    todo = [(url, file_id) for url, file_id in pairs if file_id not in present]
    print(f'{len(pairs)} у карті · {len(present)} уже на цілі · {len(todo)} довантажити',
          file=sys.stderr)
    if args.dry_run or not todo:
        for url, file_id in todo[:20]:
            print(f'  {file_id}  {url}')
        return 0

    uploaded = failed = 0
    missing: list[str] = []
    for index, (url, file_id) in enumerate(todo, 1):
        if args.limit and uploaded >= args.limit:
            break
        downloaded = download(url)
        if not downloaded:
            failed += 1
            missing.append(url)
            continue
        content, content_type = downloaded
        filename = filename_for(url)
        try:
            upload_with_retry(directus, content, filename, content_type, args.folder,
                              file_id=file_id)
        except urllib.error.HTTPError as exc:
            print(f'    ! upload {exc.code}: {exc.read().decode("utf-8", "replace")[:200]}',
                  file=sys.stderr)
            failed += 1
            continue
        except OSError as exc:
            print(f'    ! upload gave up: {exc}', file=sys.stderr)
            failed += 1
            continue
        uploaded += 1
        if uploaded % 25 == 0:
            print(f'  [{index}/{len(todo)}] {filename[:70]}', file=sys.stderr)

    print(f'\nuploaded={uploaded} failed={failed}', file=sys.stderr)
    if missing:
        print('джерело більше не віддає (покликання лишиться битим):', file=sys.stderr)
        for url in missing[:30]:
            print(f'  {url}', file=sys.stderr)
        if len(missing) > 30:
            print(f'  … ще {len(missing) - 30}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
