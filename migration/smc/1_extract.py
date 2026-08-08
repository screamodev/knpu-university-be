#!/usr/bin/env python3
"""
Stage 1 — read the quality centre's Joomla dump into two payloads.

`smc.hnpu.edu.ua` ran Joomla 3; the client handed over a mysqldump of it. Only two things matter:

  * `nijst_content` — every page of the site, including «Документи» and «Зразки документів»,
    which were behind a login while pass 2 was migrating the centre;
  * inside it, article `novyny` — a single 200 KB page whose «news» are `{spoiler title=…}` blocks,
    one dated entry each.

The dump is small and these are plain `INSERT … VALUES` rows, so it is parsed here directly — no
throwaway MySQL container, unlike `../structure-pages`.

Writes `data/news.json` and `data/pages.json`; stage 2 loads the news into Directus and stage 3
emits the pages into the frontend's static content.

    python3 1_extract.py
    python3 1_extract.py --dump ../../../hnpu_smc_temp.sql
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
STRUCTURE_PAGES = HERE.parent / 'structure-pages'
DEFAULT_DUMP = HERE.parents[2] / 'hnpu_smc_temp.sql'
BASE = 'http://smc.hnpu.edu.ua/'

# Joomla's `{spoiler title=… opened=0}` … `{/spoiler}` accordion plugin.
SPOILER_RE = re.compile(r'\{spoiler\s+title=(?P<title>.*?)\s*(?:opened=\d+\s*)?\}(?P<body>.*?)\{/spoiler\}', re.S)

MONTHS = {
    'січня': 1, 'лютого': 2, 'березня': 3, 'квітня': 4, 'травня': 5, 'червня': 6,
    'липня': 7, 'серпня': 8, 'вересня': 9, 'жовтня': 10, 'листопада': 11, 'грудня': 12,
}
DATE_DOTTED_RE = re.compile(r'(\d{1,2})\s*[.,]\s*(\d{1,2})\s*[.,]\s*(\d{4})')
DATE_WORDS_RE = re.compile(r'(\d{1,2})\s+([а-яіїєґ]+)\s+(\d{4})', re.I)

# Which tab of /education/quality each page belongs to. Ids are `nijst_content.id`.
PAGE_TABS: dict[int, str] = {
    4: 'documents', 2: 'documents',
    3: 'regulations', 6: 'regulations', 7: 'regulations', 8: 'regulations',
    10: 'regulations', 12: 'regulations',
    5: 'students', 11: 'students', 15: 'students', 18: 'students', 19: 'students',
    20: 'students', 26: 'students', 29: 'students', 35: 'students', 39: 'students',
    40: 'students', 46: 'students', 47: 'students', 48: 'students', 49: 'students',
    51: 'students', 52: 'students', 66: 'students', 67: 'students', 68: 'students',
    9: 'quality', 36: 'quality', 37: 'quality',
    14: 'programmes', 22: 'programmes', 38: 'programmes', 41: 'programmes', 42: 'programmes',
    43: 'programmes', 44: 'programmes', 45: 'programmes', 53: 'programmes',
    50: 'accreditation',
}

# Pages we deliberately leave behind: superseded archives and the site's own chrome.
SKIP_IDS = {
    1,   # «Інформація оновюється!»
    13,  # «Новини» — becomes articles instead
    16,  # «Центр забезпечення якості освіти» — already migrated as the Головна tab
    17, 21, 23, 24, 25, 27, 28, 30, 31, 32, 33, 34,  # ratings/schedules archive 2017–2019
    54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65,  # per-faculty stubs of the old chart
}


def load_transform():
    """Import 2_transform.py by path — its name is not a valid module identifier."""
    spec = importlib.util.spec_from_file_location('legacy_transform', STRUCTURE_PAGES / '2_transform.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unescape(value: str) -> str:
    """Undo mysqldump's escaping of a single-quoted string."""
    return (value.replace("\\'", "'").replace('\\"', '"').replace('\\n', '\n')
            .replace('\\r', '\r').replace('\\\\', '\\'))


def split_values(chunk: str) -> list[list[str | None]]:
    """Split `(…),(…)` of an INSERT into rows of raw field values."""
    rows: list[list[str | None]] = []
    field = ''
    row: list[str | None] = []
    in_string = escaped = False
    depth = 0

    for char in chunk:
        if in_string:
            field += char
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == "'":
                in_string = False
            continue

        if char == "'":
            in_string = True
            field += char
        elif char == '(' and depth == 0:
            depth = 1
            field = ''
            row = []
        elif char == ',' and depth == 1:
            row.append(field.strip())
            field = ''
        elif char == ')' and depth == 1:
            row.append(field.strip())
            rows.append([None if value == 'NULL' else
                         unescape(value[1:-1]) if value.startswith("'") else value
                         for value in row])
            depth = 0
            field = ''
        elif depth == 1:
            field += char

    return rows


def absolutise(html: str) -> str:
    """Joomla stored links relative, and some with Windows separators (`files\\Novunu\\x.jpg`)."""
    def fix(match: re.Match[str]) -> str:
        attr, url = match.group(1), match.group(2).replace('\\', '/')
        if url.startswith(('http://', 'https://', 'mailto:', '#', '/assets/')):
            return f'{attr}="{url}"'
        return f'{attr}="{BASE}{url.lstrip("/")}"'

    return re.sub(r'\b(href|src)="([^"]+)"', fix, html)


def parse_date(text: str) -> str | None:
    # The captions were typed with stray spaces inside the date («05.0 9 .2024», «202 5»), which
    # the editor's markup then froze in place. Close the gaps between digits and separators first.
    text = re.sub(r'(?<=\d)\s+(?=[\d.,])', '', re.sub(r'(?<=[.,])\s+(?=\d)', '', text))
    match = DATE_DOTTED_RE.search(text)
    if match:
        return f'{int(match.group(3)):04d}-{int(match.group(2)):02d}-{int(match.group(1)):02d}'
    match = DATE_WORDS_RE.search(text)
    if match:
        month = MONTHS.get(match.group(2).lower())
        if month:
            return f'{int(match.group(3)):04d}-{month:02d}-{int(match.group(1)):02d}'
    return None


def strip_tags(value: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', value)).replace('&nbsp;', ' ').strip()


def file_links(html: str) -> list[str]:
    return sorted({url for url in re.findall(r'(?:href|src)="([^"]+)"', html)
                   if 'smc.hnpu.edu.ua' in url})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dump', default=str(DEFAULT_DUMP))
    parser.add_argument('--out', default=str(HERE / 'data'))
    args = parser.parse_args()

    sql = Path(args.dump).read_text(encoding='utf-8', errors='replace')
    chunks = re.findall(r'INSERT INTO `nijst_content` VALUES (.*?);\n', sql, re.S)
    if not chunks:
        print('! no `nijst_content` rows in that dump', file=sys.stderr)
        return 1

    transform = load_transform()
    articles = {int(row[0]): row for row in split_values(''.join(chunks))}
    print(f'{len(articles)} articles in the dump', file=sys.stderr)

    # ── news: the spoiler blocks of the «Новини» page ────────────────────────
    news_row = articles.get(13)
    news: list[dict] = []
    if news_row:
        source = (news_row[5] or '') + (news_row[6] or '')
        for order, match in enumerate(SPOILER_RE.finditer(source), 1):
            caption = strip_tags(match.group('title'))
            html, images = transform.clean_body(absolutise(match.group('body')))
            news.append({
                'title': caption,
                # Most captions open with the date; a few («Вітаємо…») only mention it in the text.
                'date': parse_date(caption) or parse_date(strip_tags(html)[:400]),
                'html': html,
                'images': [url for url in images if url.startswith('http')],
                'order': order,
            })
        undated = [item['title'][:60] for item in news if not item['date']]
        print(f'news entries: {len(news)}; without a parsed date: {len(undated)}', file=sys.stderr)
        for title in undated:
            print(f'    ? {title}', file=sys.stderr)

    # ── pages: everything the site still misses ──────────────────────────────
    pages: list[dict] = []
    for article_id, row in sorted(articles.items()):
        if article_id in SKIP_IDS:
            continue
        tab = PAGE_TABS.get(article_id)
        if not tab:
            print(f'    ? id {article_id} «{row[2][:50]}» has no tab — skipped', file=sys.stderr)
            continue
        html, _ = transform.clean_body(absolutise((row[5] or '') + (row[6] or '')))
        if len(strip_tags(html)) < 40 and 'href' not in html:
            continue
        pages.append({
            'id': article_id,
            'tab': tab,
            'title': row[2],
            'alias': row[3],
            'html': html,
            'files': file_links(html),
            'sourceUrl': f'{BASE}{row[3]}',
        })

    by_tab: dict[str, int] = {}
    for page in pages:
        by_tab[page['tab']] = by_tab.get(page['tab'], 0) + 1
    print(f'pages: {len(pages)} — ' + ', '.join(f'{tab}: {count}' for tab, count in sorted(by_tab.items())),
          file=sys.stderr)
    print(f'file links: {len({url for page in pages for url in page["files"]})}', file=sys.stderr)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'news.json').write_text(json.dumps(news, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'pages.json').write_text(json.dumps(pages, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'→ {out}/news.json, {out}/pages.json', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
