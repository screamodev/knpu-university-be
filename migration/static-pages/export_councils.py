#!/usr/bin/env python3
"""
Перекласти сторінки спеціалізованих вчених рад зі статичного контенту фронту в колекцію
`static_pages`, щоб секретарі рад самі додавали рядки таблиці захистів і гіперпосилання.

Джерело — `knpu-university-fe/app/content/pages/council-*.uk.json`: список секцій, де перша
без заголовка (профіль ради), а друга — випадаючий список «Склад ради». У Directus тіло
сторінки одне поле WYSIWYG, тож секції зшиваються в один HTML: заголовки стають `<h2>`, а
випадаючі списки — `<details><summary>` (той самий прийом, що й у `structure_pages`; TinyMCE
знає ці елементи через `extended_valid_elements`).

Результат уже закомічений у `data/static-pages.json`, тож на сервері достатньо:

    python3 pass2/load.py static-pages/data/static-pages.json --dry-run
    python3 pass2/load.py static-pages/data/static-pages.json

Перезапуск нічого не псує: `identity: ["slug"]` оновлює наявний рядок. Але тексти, які редактор
уже правив в адмінці, скрипт перетре — після першого завантаження його не ганяють.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_OUT = HERE / 'data' / 'static-pages.json'

COUNCIL_SLUGS = [
    'council-d-64-053-01',
    'council-k-64-053-05',
    'council-d-64-053-08',
]


def default_content_dir() -> Path:
    """`knpu-university-fe` лежить поруч із цим репозиторієм."""
    return HERE.resolve().parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'pages'


def section_html(section: dict) -> str:
    heading = (section.get('heading') or '').strip()
    body = (section.get('html') or '').strip()
    children = section.get('children') or []

    inner = body
    for child in children:
        inner += '\n' + section_html({**child, 'collapsible': True})

    if not heading:
        return inner
    if section.get('collapsible'):
        return f'<details><summary>{heading}</summary>\n{inner}\n</details>'
    return f'<h2>{heading}</h2>\n{inner}'


def page_body(content_dir: Path, slug: str) -> str:
    path = content_dir / f'{slug}.uk.json'
    page = json.loads(path.read_text(encoding='utf-8'))
    parts = [section_html(section) for section in page.get('sections', [])]
    return '\n'.join(part for part in parts if part.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--content', help='тека app/content/pages фронту')
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    parser.add_argument('--slugs', nargs='*', default=COUNCIL_SLUGS)
    args = parser.parse_args()

    content = Path(args.content) if args.content else default_content_dir()
    if not content.is_dir():
        raise SystemExit(
            f'немає теки зі статичним контентом: {content}\n'
            'Крок потребує репозиторію knpu-university-fe поруч — це команда для машини '
            'розробника. На сервері запускайте одразу pass2/load.py: результат експорту вже '
            'закомічено в data/static-pages.json.')

    rows = []
    for slug in args.slugs:
        body = page_body(content, slug)
        rows.append({'slug': slug, 'status': 'published', 'body': body})
        print(f'  + {slug}: {len(body)} символів', file=sys.stderr)

    payload = {'batches': [{
        'collection': 'static_pages',
        'identity': ['slug'],
        'rows': rows,
    }]}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{out}: {len(rows)} рядків', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
