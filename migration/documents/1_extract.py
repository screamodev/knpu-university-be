#!/usr/bin/env python3
"""
Stage 1 — read the old site's document pages and emit one flat list of rows.

Every «Відвідувачу» page on the old site is the same thing: a body full of links, each one a PDF
plus a sentence describing it. `sources.json` maps a `documents.section` to the page it comes
from; this script turns those pages into `documents.json`, which stage 2 loads into Directus.

Nothing is fetched twice: pages are cached under `.cache/`.

    python3 1_extract.py                 # all sections
    python3 1_extract.py --only vacancies regulations
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / '.cache'

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'uk,en;q=0.8',
}

BODY_RE = re.compile(r'<div class="field field-name-body.*?</div>\s*</div>\s*</div>', re.S)
LINK_RE = re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
FILE_RE = re.compile(r'\.(pdf|docx?|xlsx?|pptx?|rtf|odt|zip|jpe?g|png)(\?|$)', re.I)

MONTHS = {
    'січня': 1, 'лютого': 2, 'березня': 3, 'квітня': 4, 'травня': 5, 'червня': 6,
    'липня': 7, 'серпня': 8, 'вересня': 9, 'жовтня': 10, 'листопада': 11, 'грудня': 12,
}
# The old site's PDFs of scanned orders were typed with Latin i/e in place of Cyrillic і/е.
LATIN_LOOKALIKES = str.maketrans({'i': 'і', 'I': 'І', 'e': 'е', 'a': 'а', 'o': 'о', 'c': 'с', 'p': 'р', 'y': 'у', 'x': 'х'})

DATE_WORDS_RE = re.compile(r'\b(\d{1,2})\s+([а-яіїєґ]+)\s+(\d{4})\b', re.I)
DATE_DOTTED_RE = re.compile(r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b')
YEAR_RE = re.compile(r'\b(19|20)\d{2}\b')


def text_of(markup: str) -> str:
    return re.sub(r'\s+', ' ', html_lib.unescape(re.sub(r'<[^>]+>', '', markup))).strip()


def fetch(url: str) -> str:
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / (re.sub(r'\W+', '_', url)[-120:] + '.html')
    if cached.exists():
        return cached.read_text(encoding='utf-8')
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode('utf-8', 'replace')
    cached.write_text(body, encoding='utf-8')
    return body


def parse_date(title: str) -> str | None:
    """Best-effort date out of the title — that is the only place the old site records one."""
    normalised = title.translate(LATIN_LOOKALIKES)

    match = DATE_WORDS_RE.search(normalised)
    if match:
        month = MONTHS.get(match.group(2).lower())
        if month:
            return f'{int(match.group(3)):04d}-{month:02d}-{int(match.group(1)):02d}'

    match = DATE_DOTTED_RE.search(title)
    if match:
        return f'{int(match.group(3)):04d}-{int(match.group(2)):02d}-{int(match.group(1)):02d}'

    # «Звіт Ректора за 2025 рік» — a bare year is a real date only in this phrasing. Titles like
    # «Концепція виховної роботи на 2021 - 2025 рр.» name a period, not a publication date, so
    # they stay undated rather than being filed under 2021.
    match = re.search(r'\bза\s+((?:19|20)\d{2})\s*(?:рік|р\.|н\.\s*р\.)', normalised, re.I)
    if match:
        return f'{match.group(1)}-01-01'
    return None


def absolute(url: str, page_url: str) -> str:
    if url.startswith('//'):
        return 'https:' + url
    return urllib.parse.urljoin(page_url, url)


def extract(section: str, config: dict) -> list[dict]:
    page_url = config['url']
    page = fetch(page_url)
    body_match = BODY_RE.search(page)
    if not body_match:
        print(f'{section}: no body — 0 rows', file=sys.stderr)
        return []

    rows: list[dict] = []
    seen: set[str] = set()
    for href, label in LINK_RE.findall(body_match.group(0)):
        title = text_of(label)
        if not title or href.startswith('mailto:') or href.startswith('#'):
            continue

        url = absolute(html_lib.unescape(href), page_url)
        is_file = bool(FILE_RE.search(urllib.parse.urlparse(url).path))
        is_own_page = 'hnpu.edu.ua' in url and not is_file
        if is_own_page and not config.get('includeInternalPages'):
            continue
        # The old markup often splits one title across two adjacent <a> tags pointing at the same
        # file (`…населенн` + `я`). Stitch those back together; a repeat further down the page is
        # a genuine duplicate and gets dropped.
        if rows and rows[-1]['sourceUrl'] == url:
            joiner = '' if title[0].islower() else ' '
            rows[-1]['title'] += joiner + title
            continue
        if url in seen:
            continue
        seen.add(url)

        rows.append({
            'section': section,
            'title': title,
            # Position on the legacy page. Most of these lists are hand-curated (and mostly
            # undated), so that order is the only meaningful one there is.
            'order': len(rows) + 1,
            'documentDate': parse_date(title),
            'sourceUrl': url,
            # A file is downloaded and re-hosted; anything else stays a link.
            'kind': 'file' if is_file else 'link',
        })

    print(f'{section}: {len(rows)} rows '
          f'({sum(1 for r in rows if r["kind"] == "file")} files, '
          f'{sum(1 for r in rows if not r["documentDate"])} without a date)', file=sys.stderr)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', nargs='*', help='limit to these sections')
    parser.add_argument('--out', default=str(HERE / 'documents.json'))
    args = parser.parse_args()

    sources = json.loads((HERE / 'sources.json').read_text(encoding='utf-8'))
    rows: list[dict] = []
    for section, config in sources.items():
        if args.only and section not in args.only:
            continue
        rows.extend(extract(section, config))

    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'→ {args.out}: {len(rows)} rows', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
