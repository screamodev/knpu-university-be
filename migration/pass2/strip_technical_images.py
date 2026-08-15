#!/usr/bin/env python3
"""
Прибрати з перенесених сторінок технічні картинки й навігацію старого сайту.

Кафедральні сторінки принесли зі старого сайту дві речі, яких на новому сайті бути не повинно:

  * `border.png` — прозорий роздільник 2×39 px, яким Joomla малювала рамки таблиць. На нашій
    сторінці він показується як вузька сіра смужка;
  * таблицю-меню кафедри («Головна | Cпівробітники | Навчання | Лекції | Наука | Новини | Музей»),
    яка дублює вкладки самої сторінки й веде сама на себе.

Скрипт знаходить технічні зображення в Directus за розміром (сторона ≤ `--max-side`, типово 8 px),
знімає їх з усіх `html` у `app/content/**/*.json` і видаляє таблиці, які після цього лишаються
самою лише навігацією. Ідемпотентний: повторний запуск нічого не змінює.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 strip_technical_images.py --dry-run
    python3 strip_technical_images.py --write
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from common import Directus, login

HERE = Path(__file__).parent
CONTENT = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content'

# A table that is nothing but links to the department's own tabs.
NAV_WORDS = ('Головна', 'Співробітники', 'Cпівробітники', 'Навчання', 'Лекції', 'Наука',
             'Новини', 'Музей', 'Корисні посилання')


def technical_file_ids(directus: Directus, max_side: int) -> set[str]:
    query = urllib.parse.urlencode({
        'fields': 'id,width,height,filename_download',
        'limit': '-1',
        'filter[type][_starts_with]': 'image/',
    })
    rows = directus.get(f'/files?{query}') or []
    ids = set()
    for row in rows:
        width, height = row.get('width') or 0, row.get('height') or 0
        if width and height and min(width, height) <= max_side:
            ids.add(row['id'])
    return ids


def strip_images(markup: str, ids: set[str]) -> tuple[str, int]:
    removed = 0

    def drop(match: re.Match[str]) -> str:
        nonlocal removed
        if any(file_id in match.group(0) for file_id in ids):
            removed += 1
            return ''
        return match.group(0)

    return re.sub(r'<img\b[^>]*>', drop, markup), removed


def drop_nav_tables(markup: str) -> tuple[str, int]:
    """A table whose text is only tab names (and nothing else) is the old site's menu."""
    removed = 0

    def drop(match: re.Match[str]) -> str:
        nonlocal removed
        text = re.sub(r'<[^>]+>', ' ', match.group(0))
        text = re.sub(r'&nbsp;|\s+', ' ', text).strip()
        if not text:
            removed += 1
            return ''
        words = [word for word in re.split(r'[|\s]+', text) if word]
        if words and all(any(word in phrase for phrase in NAV_WORDS) for word in words):
            removed += 1
            return ''
        return match.group(0)

    return re.sub(r'<table\b.*?</table>', drop, markup, flags=re.S), removed


def tidy(markup: str, ids: set[str]) -> tuple[str, int, int]:
    markup, images = strip_images(markup, ids)
    markup, tables = drop_nav_tables(markup)
    # Paragraphs and cells left empty by the removals.
    markup = re.sub(r'<p>\s*(?:&nbsp;)?\s*</p>', '', markup)
    markup = re.sub(r'\n{3,}', '\n\n', markup)
    return markup.strip(), images, tables


def walk(node, ids: set[str], stats: list[int]):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == 'html' and isinstance(value, str):
                cleaned, images, tables = tidy(value, ids)
                if cleaned != value:
                    node[key] = cleaned
                    stats[0] += images
                    stats[1] += tables
            else:
                walk(value, ids, stats)
    elif isinstance(node, list):
        for item in node:
            walk(item, ids, stats)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--content', default=str(CONTENT))
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--max-side', type=int, default=8)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)
    ids = technical_file_ids(directus, args.max_side)
    print(f'technical images in the library: {len(ids)}', file=sys.stderr)

    total_images = total_tables = touched = 0
    for path in sorted(Path(args.content).rglob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        stats = [0, 0]
        walk(data, ids, stats)
        if not any(stats):
            continue
        touched += 1
        total_images += stats[0]
        total_tables += stats[1]
        print(f'  {path.relative_to(Path(args.content))}: '
              f'{stats[0]} image(s), {stats[1]} nav table(s)', file=sys.stderr)
        if args.write:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(f'\nfiles={touched} images={total_images} tables={total_tables}'
          f'{"" if args.write else "  (dry run — nothing written)"}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
