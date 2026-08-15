#!/usr/bin/env python3
"""
Прибрати покликання на файли старого сайту, яких там уже немає.

`tidy_legacy_html.py` навмисно не чіпає покликань на файли — їх переносить
`mirror_page_files.py`, підмінюючи адресу на `/assets/<uuid>`. Але частину файлів старий сайт
віддає 404: перенести їх нема звідки, і в тексті лишається покликання, яке веде відвідувача на
чужу сторінку помилки. Тут такі покликання перевіряються запитом і, якщо файл справді зник,
розгортаються назад у звичайний текст — назва документа лишається, клікати нема куди.

Живі покликання скрипт не чіпає й перелічує наприкінці: їх треба долити
`mirror_page_files.py`, а не викидати.

    python3 prune_dead_file_links.py --dry-run
    python3 prune_dead_file_links.py --write --only 'pk-*'
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from tidy_legacy_html import CONTENT, FILE_EXT_RE, LEGACY_HOSTS, LINK_RE, strip_tags

HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
}


def alive(url: str, cache: dict[str, bool]) -> bool:
    if url not in cache:
        request = urllib.request.Request(url, headers=HEADERS, method='HEAD')
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                cache[url] = response.status < 400
        except urllib.error.HTTPError as exc:
            cache[url] = exc.code < 400
        except (urllib.error.URLError, OSError):
            cache[url] = False
    return cache[url]


def prune(markup: str, cache: dict[str, bool], dead: set[str], live: set[str]) -> tuple[str, int]:
    removed = 0

    def handle(match: re.Match[str]) -> str:
        nonlocal removed
        href = match.group('href')
        parts = urlsplit(href)
        if parts.netloc.lower() not in LEGACY_HOSTS or not FILE_EXT_RE.search(parts.path):
            return match.group(0)
        if alive(href, cache):
            live.add(href)
            return match.group(0)
        dead.add(href)
        removed += 1
        text = match.group('text')
        # Підпис, який сам був адресою, після зняття покликання читати нема кому.
        return '' if strip_tags(text).strip().rstrip('/') == href.rstrip('/') else text

    return LINK_RE.sub(handle, markup), removed


def walk(node, fn) -> bool:
    """Пройтися всіма рядками `html` у дереві сторінки; True, якщо щось змінилося."""
    changed = False
    if isinstance(node, dict):
        for key, value in node.items():
            if key == 'html' and isinstance(value, str):
                updated = fn(value)
                if updated != value:
                    node[key] = updated
                    changed = True
            elif walk(value, fn):
                changed = True
    elif isinstance(node, list):
        for item in node:
            if walk(item, fn):
                changed = True
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', default='*', help="взяти лише ці сторінки, напр. 'pk-*'")
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    cache: dict[str, bool] = {}
    dead: set[str] = set()
    live: set[str] = set()
    touched = removed_total = 0

    for path in sorted((CONTENT / 'pages').glob(f'{args.only}.uk.json')):
        page = json.loads(path.read_text(encoding='utf-8'))
        removed_here = 0

        def clean(markup: str) -> str:
            nonlocal removed_here
            markup, removed = prune(markup, cache, dead, live)
            removed_here += removed
            return markup

        if walk(page, clean):
            touched += 1
            removed_total += removed_here
            print(f'  {path.name}: знято {removed_here}', file=sys.stderr)
            if args.write and not args.dry_run:
                path.write_text(json.dumps(page, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')

    print(f'\nсторінок змінено={touched} знято покликань={removed_total} '
          f'(мертвих адрес {len(dead)}, живих лишилося {len(live)})', file=sys.stderr)
    for url in sorted(live):
        print(f'  живе, треба долити mirror_page_files.py: {url}', file=sys.stderr)
    if not args.write:
        print('без --write нічого не записано', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
