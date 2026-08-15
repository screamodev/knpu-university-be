#!/usr/bin/env python3
"""
Перетворити перенесені таблиці-фотогалереї на сітку карток.

Старий сайт викладав співробітників кафедри таблицею: у кожній комірці портрет і під ним ім’я.
Ширина комірок там була фіксована, тож у нас така таблиця розсипається в один стовпчик із
величезними фото — клієнт попросив «не в стовпчик, а мозаїкою».

Скрипт знаходить такі таблиці (≥3 комірок, у кожній рівно одне зображення) і замінює їх на

    <div class="photo-grid">
      <figure><img …><figcaption>Ім’я</figcaption></figure>
      …
    </div>

Порядок комірок зберігається, тож завідувач, який на старому сайті стояв першим, лишається
першим. Підписи-заголовки на кшталт «Допоміжний персонал кафедри» виносяться окремим абзацом
перед сіткою. Ідемпотентний: таблиць після заміни не лишається, повторний запуск нічого не робить.

    python3 gridify_photo_tables.py --dry-run
    python3 gridify_photo_tables.py --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
CONTENT = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content'

CELL_RE = re.compile(r'<td\b[^>]*>(.*?)</td>', re.S)
IMG_RE = re.compile(r'<img\b[^>]*>', re.S)
TABLE_RE = re.compile(r'<table\b.*?</table>', re.S)
TAG_RE = re.compile(r'<[^>]+>')


def cell_text(cell: str) -> str:
    text = TAG_RE.sub(' ', IMG_RE.sub(' ', cell))
    return re.sub(r'&nbsp;|\s+', ' ', text).strip(' .,;:')


def cell_link(cell: str) -> str | None:
    match = re.search(r'<a\b[^>]*href="([^"]+)"', cell)
    return match.group(1) if match else None


def gridify(table: str) -> str | None:
    """→ the grid markup, or None when this table is not a photo gallery."""
    cells = CELL_RE.findall(table)
    with_photo = [cell for cell in cells if len(IMG_RE.findall(cell)) == 1]
    if len(with_photo) < 3:
        return None
    # A gallery is mostly photos: a data table with one stray image must stay a table.
    filled = [cell for cell in cells if cell_text(cell) or IMG_RE.search(cell)]
    if len(with_photo) < max(2, len(filled) * 0.6):
        return None

    captions = [cell_text(cell) for cell in cells
                if not IMG_RE.search(cell) and len(cell_text(cell)) > 12]

    figures = []
    for cell in with_photo:
        image = IMG_RE.search(cell).group(0)
        name = cell_text(cell)
        href = cell_link(cell)
        label = f'<a href="{href}">{name}</a>' if href and name else name
        caption = f'<figcaption>{label}</figcaption>' if name else ''
        figures.append(f'<figure>{image}{caption}</figure>')

    intro = ''.join(f'<p><strong>{caption}</strong></p>' for caption in captions)
    return f'{intro}<div class="photo-grid">{"".join(figures)}</div>'


def convert(markup: str) -> tuple[str, int]:
    converted = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal converted
        grid = gridify(match.group(0))
        if grid is None:
            return match.group(0)
        converted += 1
        return grid

    return TABLE_RE.sub(replace, markup), converted


def walk(node, stats: list[int]):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == 'html' and isinstance(value, str):
                cleaned, count = convert(value)
                if count:
                    node[key] = cleaned
                    stats[0] += count
            else:
                walk(value, stats)
    elif isinstance(node, list):
        for item in node:
            walk(item, stats)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--content', default=str(CONTENT))
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    total = touched = 0
    for path in sorted(Path(args.content).rglob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        stats = [0]
        walk(data, stats)
        if not stats[0]:
            continue
        touched += 1
        total += stats[0]
        print(f'  {path.relative_to(Path(args.content))}: {stats[0]} table(s)', file=sys.stderr)
        if args.write:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(f'\nfiles={touched} tables={total}'
          f'{"" if args.write else "  (dry run — nothing written)"}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
