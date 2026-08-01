#!/usr/bin/env python3
"""
Stage 1 — read the newspaper archive off the old site.

The legacy archive page is a better source than the SQL dump: the dump stops at № 343-344
(March 2025) while the page runs to the current issue, and every link carries a human label
(`№ 8-9 (349-350) вересень 2025`) that already contains the issue number, the continuous number
and the month. So nothing has to be guessed from the PDF filenames, which come in eight
inconsistent formats.

Writes `issues.json`: one object per issue with `number`, `serial`, `issueDate`, `label` and the
absolute PDF URL. Pure and read-only — re-run it whenever a new issue is published.

Usage:
    python3 1_fetch.py
    python3 1_fetch.py --report
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ARCHIVE_URL = 'https://hnpu.edu.ua/uk/arhiv-vydannya-uchytel'

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'uk,en;q=0.8',
}

BODY_RE = re.compile(r'<div class="field field-name-body.*?</div>\s*</div>\s*</div>', re.S)
LINK_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
TAG_RE = re.compile(r'<[^>]+>')

# `№ 8-9 (349-350) вересень 2025` — spacing around the dashes is inconsistent, hence the \s*.
LABEL_RE = re.compile(r'^№\s*(\d+(?:\s*[-–]\s*\d+)?)\s*\(\s*(\d+(?:\s*[-–]\s*\d+)?)\s*\)\s*(.*)$')

MONTHS = {
    'січ': 1, 'лют': 2, 'бере': 3, 'квіт': 4, 'трав': 5, 'черв': 6,
    'лип': 7, 'серп': 8, 'вере': 9, 'жовт': 10, 'листоп': 11, 'груд': 12,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', default=ARCHIVE_URL)
    parser.add_argument('--out', default=str(HERE / 'issues.json'))
    parser.add_argument('--report', action='store_true')
    return parser.parse_args()


def absolutise(href: str) -> str:
    value = html.unescape(href.strip())
    if value.startswith('//'):
        return f'https:{value}'
    if value.startswith('/'):
        return f'https://hnpu.edu.ua{value}'
    return value


def clean_label(markup: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(TAG_RE.sub('', markup))).strip()


def parse_label(label: str) -> dict | None:
    match = LABEL_RE.match(label)
    if not match:
        return None
    number = re.sub(r'\s*[-–]\s*', '-', match.group(1))
    serial = re.sub(r'\s*[-–]\s*', '-', match.group(2))
    rest = match.group(3).lower()

    year = re.search(r'(20\d\d)', rest)
    month = next((value for prefix, value in MONTHS.items() if prefix in rest), None)
    if not year or not month:
        return None
    return {
        'number': number,
        'serial': serial,
        'issueDate': f'{year.group(1)}-{month:02d}-01',
    }


def main() -> int:
    args = parse_args()

    request = urllib.request.Request(args.url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        page = response.read().decode('utf-8', 'replace')

    body = BODY_RE.search(page)
    if not body:
        print('! could not find the page body — the legacy markup changed', file=sys.stderr)
        return 1

    issues: list[dict] = []
    skipped: list[str] = []
    seen_urls: dict[str, str] = {}

    for href, markup in LINK_RE.findall(body.group(0)):
        label = clean_label(markup)
        url = absolutise(href)
        if not url.lower().endswith('.pdf'):
            continue
        parsed = parse_label(label)
        if not parsed:
            skipped.append(label)
            continue
        issue = {**parsed, 'label': label, 'sourceUrl': url}
        if url in seen_urls:
            # Their archive links two different issues to one file; keep both rows and report it.
            issue['duplicateOf'] = seen_urls[url]
        else:
            seen_urls[url] = issue['serial']
        issues.append(issue)

    issues.sort(key=lambda item: (item['issueDate'], item['serial']), reverse=True)
    Path(args.out).write_text(json.dumps(issues, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    duplicates = [i for i in issues if 'duplicateOf' in i]
    # Their archive has at least one link pointing at a PDF from a different year; the filename
    # is only a hint, so this is reported, never "corrected".
    mismatched = [
        i for i in issues
        if (found := re.search(r'(20\d\d)', i['sourceUrl'].rsplit('/', 1)[-1]))
        and found.group(1) != i['issueDate'][:4]
    ]
    years = sorted({i['issueDate'][:4] for i in issues})
    print(
        f'{len(issues)} issues → {args.out}\n'
        f'  years:      {years[0]}–{years[-1]}\n'
        f'  duplicates: {len(duplicates)}\n'
        f'  year mismatch between label and filename: {len(mismatched)}\n'
        f'  skipped:    {len(skipped)}',
        file=sys.stderr,
    )
    for label in skipped:
        print(f'  ! unparsed label: {label}', file=sys.stderr)
    for issue in mismatched:
        print(f'  ! {issue["label"]} links to {issue["sourceUrl"].rsplit("/", 1)[-1]} '
              f'— filename says a different year', file=sys.stderr)
    for issue in duplicates:
        print(f'  ! № {issue["serial"]} reuses the PDF of № {issue["duplicateOf"]}: '
              f'{issue["sourceUrl"].rsplit("/", 1)[-1]}', file=sys.stderr)
    if args.report:
        for issue in issues:
            print(f'  {issue["issueDate"]}  №{issue["number"]:>6} ({issue["serial"]:>7})  '
                  f'{issue["sourceUrl"].rsplit("/", 1)[-1]}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
