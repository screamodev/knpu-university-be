#!/usr/bin/env python3
"""
Перенести файли договорів зі старого сайту й підмінити адреси в `data/agreements.json`.

`1_extract.py` зберігає в `sourceUrl` адресу, на яку в реєстрі вказує назва договору. Переважно це
PDF на hnpu.edu.ua — після вимкнення старого сайту такі покликання помруть, тож файли треба забрати
до себе. Покликання на Google Drive лишаємо як є: ці файли ведуть самі підрозділи.

Скрипт качає кожен файл, вантажить у Directus і записує в рядок `url = /assets/<uuid>`, а пару
«джерело → uuid» — у `data/files.map.json`, щоб `../pass2/sync_files_map.py` долив те саме на прод.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_TOKEN=…
    python3 3_mirror.py --dry-run
    python3 3_mirror.py
    python3 ../pass2/sync_files_map.py --map ../agreements/data/files.map.json   # на проді

Ідемпотентний: те, що вже в карті, вдруге не качається.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, download, filename_for, login  # noqa: E402
from mirror_page_files import DEFAULT_FOLDER, upload_with_retry  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / 'data'
AGREEMENTS = DATA / 'agreements.json'
FILES_MAP = DATA / 'files.map.json'

MIRROR_HOSTS = ('hnpu.edu.ua', 'www.hnpu.edu.ua')


def needs_mirror(url: str) -> bool:
    return bool(url) and any(f'//{host}/' in url for host in MIRROR_HOSTS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--folder', default=DEFAULT_FOLDER)
    parser.add_argument('--limit', type=int, help='зупинитися після стількох завантажень')
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    rows = json.loads(AGREEMENTS.read_text(encoding='utf-8'))
    mapping: dict[str, str] = json.loads(FILES_MAP.read_text(encoding='utf-8')) if FILES_MAP.exists() else {}

    todo = sorted({row['sourceUrl'] for row in rows
                   if needs_mirror(row.get('sourceUrl', '')) and row['sourceUrl'] not in mapping})
    external = sum(1 for row in rows if row.get('sourceUrl') and not needs_mirror(row['sourceUrl']))
    print(f'{len(rows)} договорів · {len(mapping)} уже перенесено · {len(todo)} звантажити · '
          f'{external} лишаються на Google Drive', file=sys.stderr)

    if not args.dry_run and todo:
        token = args.token or login(args.directus_url, args.email, args.password)
        directus = Directus(args.directus_url, token)

        uploaded = failed = 0
        missing: list[str] = []
        for index, url in enumerate(todo, 1):
            if args.limit and uploaded >= args.limit:
                break
            downloaded = download(url)
            if not downloaded:
                failed += 1
                missing.append(url)
                continue
            content, content_type = downloaded
            try:
                file_id = upload_with_retry(directus, content, filename_for(url), content_type,
                                            args.folder)
            except (urllib.error.HTTPError, OSError) as exc:
                print(f'    ! {url}: {exc}', file=sys.stderr)
                failed += 1
                continue
            mapping[url] = file_id
            uploaded += 1
            if uploaded % 25 == 0:
                print(f'  [{index}/{len(todo)}] {filename_for(url)[:70]}', file=sys.stderr)
                FILES_MAP.write_text(json.dumps(mapping, ensure_ascii=False, indent=1) + '\n',
                                     encoding='utf-8')

        FILES_MAP.write_text(json.dumps(mapping, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'\nuploaded={uploaded} failed={failed}', file=sys.stderr)
        if missing:
            print('старий сайт більше не віддає (покликання приберемо):', file=sys.stderr)
            for url in missing[:20]:
                print(f'  {url}', file=sys.stderr)

    # Адреса в рядку: своя копія, якщо перенесли; чужий хост — як є; мертве покликання — прибрати.
    changed = dropped = 0
    for row in rows:
        source = row.get('sourceUrl') or ''
        if not source:
            row['url'] = ''
            continue
        if needs_mirror(source):
            file_id = mapping.get(source)
            url = f'/assets/{file_id}' if file_id else ''
            if not file_id:
                dropped += 1
        else:
            url = source
        if row.get('url') != url:
            row['url'] = url
            changed += 1

    if args.dry_run:
        print(f'dry run: оновилося б {changed} рядків, без файла лишилося б {dropped}', file=sys.stderr)
        return 0

    AGREEMENTS.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'оновлено рядків: {changed}; без файла: {dropped}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
