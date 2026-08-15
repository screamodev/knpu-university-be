#!/usr/bin/env python3
"""
Stage 3 — відновити карту «адреса зображення на старому сайті → uuid у нас».

`migrate_page.py` вантажить зображення сторінки в Directus і одразу підміняє `src` на
`/assets/<uuid>`, але ніде не лишає, звідки той файл узявся. Через це на іншому середовищі
(прод) зображення нема з чого долити: у контенті стоїть uuid, якого там не існує, і сторінка
показує биті картинки. Файли-документи такої проблеми не мають — їх переносить
`../pass2/mirror_page_files.py`, який карту веде.

Скрипт зіставляє два списки в тому самому порядку: `<img>` у сирому HTML сторінки на старому
сайті й `/assets/<uuid>` у перенесеному JSON. Порядок зберігається (перенос лише підміняє
атрибут), тож пари виходять однозначні. Результат — `data/images.map.json` того самого формату,
що й `files.map.json`, тільки навпаки — ключ тут uuid, бо один банер, повторений на десятках
сторінок, лежить у Directus стільки ж разів, і зворотний ключ ці пари з'їв би. Долити на прод:

    python3 ../pass2/sync_files_map.py --by-id --map ../admissions/data/images.map.json

Використання:

    python3 3_image_map.py --dry-run
    python3 3_image_map.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CONTENT = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'pages'
PAGES = HERE / 'data' / 'pages.json'
OUT = HERE / 'data' / 'images.map.json'

HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept-Language': 'uk,en;q=0.8',
}

BODY_RE = re.compile(r'<div class="field field-name-body.*?(?=<div class="region region-footer|<footer)', re.S)
IMG_SRC_RE = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"', re.I)
# Сторінки лежать у JSON, тож лапки атрибутів у них екрановані: src=\"/assets/…\".
ASSET_RE = re.compile(r'<img\b(?:[^>]|\\")*?\bsrc=\\"/assets/([0-9a-f-]{36})\\"', re.I)


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode('utf-8', 'replace')


def basename(url: str) -> str:
    """Останній сегмент адреси — саме його Directus зберігає як `filename_download`."""
    return url.rsplit('/', 1)[-1].split('?', 1)[0]


def directus_filename(base_url: str, token: str | None, file_id: str) -> str | None:
    """Ім'я, під яким файл лежить у нас; None, якщо такого файла чи доступу немає."""
    url = f'{base_url}/files/{file_id}?fields=filename_download'
    request = urllib.request.Request(url, headers=dict(HEADERS))
    if token:
        request.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)['data']['filename_download']
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, KeyError, ValueError):
        return None


def absolute(src: str) -> str:
    if src.startswith('//'):
        return 'https:' + src
    if src.startswith('/'):
        return 'https://hnpu.edu.ua' + src
    return src


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pages', default=str(PAGES))
    parser.add_argument('--out', default=str(OUT))
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055',
                        help='звідки брати імена файлів, коли порядок картинок розійшовся')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    pages = json.loads(Path(args.pages).read_text(encoding='utf-8'))
    mapping: dict[str, str] = {}
    if Path(args.out).exists():
        mapping = json.loads(Path(args.out).read_text(encoding='utf-8'))

    matched = mismatched = skipped = 0
    for index, entry in enumerate(pages, 1):
        target = CONTENT / f'{entry["slug"]}.uk.json'
        if not target.exists():
            continue
        assets = ASSET_RE.findall(target.read_text(encoding='utf-8'))
        if not assets:
            continue
        try:
            page = fetch(entry['url'])
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            print(f'  ! {entry["slug"]}: {exc}', file=sys.stderr)
            continue
        body_match = BODY_RE.search(page)
        sources = [absolute(src) for src in IMG_SRC_RE.findall(body_match.group(0) if body_match else '')]
        # Оформлення теми та іконки модулів у тіло сторінки не входять, але потрапляють у зріз
        # регулярки — вони живуть у /sites/all/, тоді як завантажений контент у /sites/default/.
        sources = [src for src in sources
                   if src.startswith('http') and '/sites/all/' not in src]

        if len(sources) != len(assets):
            # Сторінку встигли відредагувати після переносу — порядок уже не збігається, тож
            # лишається зіставляти поіменно: Directus зберіг вихідне ім'я файла.
            mismatched += 1
            by_name = {basename(source): source for source in sources}
            unresolved = 0
            for asset in assets:
                source = by_name.get(directus_filename(args.directus_url, args.token, asset) or '')
                if source is None:
                    unresolved += 1
                    continue
                mapping[asset] = source
            print(f'  ? {entry["slug"]}: {len(sources)} на старому сайті проти {len(assets)} у нас '
                  f'— зіставлено поіменно, без пари лишилося {unresolved}', file=sys.stderr)
            continue

        for source, asset in zip(sources, assets):
            if mapping.get(asset) not in (None, source):
                skipped += 1
                continue
            mapping[asset] = source
        matched += 1
        if index % 20 == 0:
            print(f'  [{index}/{len(pages)}] {len(mapping)} пар', file=sys.stderr)
        time.sleep(0.2)

    print(f'\nсторінок зіставлено={matched} розбіжних={mismatched} суперечливих={skipped}; '
          f'усього пар: {len(mapping)}', file=sys.stderr)
    if args.dry_run:
        print('dry run — нічого не записано', file=sys.stderr)
        return 0
    Path(args.out).write_text(json.dumps(mapping, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'→ {args.out}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
