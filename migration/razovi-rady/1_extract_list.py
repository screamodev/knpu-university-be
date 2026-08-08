#!/usr/bin/env python3
"""
Read the index of one-time specialized academic councils and write the list of defense pages.

Source: https://hnpu.edu.ua/uk/razovi-specializovani-vcheni-rady — one long page, no pagination,
links grouped under «NNNN рік» headings. Output keeps document order, so `order` on the site can
mirror the old site's ordering.

    docker run --rm --network host -v "$(pwd)/..":/work -w /work/razovi-rady \
      python:3.12-slim python 1_extract_list.py

→ data/index.json
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse

from shared import DATA, LIST_SLUG, LIST_URL, body_of, fetch, parse_ukrainian_date, text_of, unescape, write_json

LINK_RE = re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
YEAR_RE = re.compile(r'\b((?:19|20)\d{2})\s*рік')

# The four slug shapes the archive actually uses. Everything else in the body (the sidebar, the
# «На допомогу здобувачеві» page) is navigation, not a defense.
DEFENSE_SLUG_RE = re.compile(
    r'^(?:specializovan[aeiu][^/]*|razova-specializovana[^/]*|zahyst-dysertaciyi[^/]*)$')
NOT_A_DEFENSE = {
    LIST_SLUG,
    'specializovani-vcheni-rady-universytetu',
}


def slug_of(href: str) -> str | None:
    """`//hnpu.edu.ua/uk/foo`, `/uk/foo`, `https://hnpu.edu.ua/uk/foo` → `foo`."""
    url = unescape(href).strip()
    if url.startswith('//'):
        url = 'https:' + url
    parts = urllib.parse.urlsplit(url)
    if parts.netloc and 'hnpu.edu.ua' not in parts.netloc.lower():
        return None
    path = urllib.parse.unquote(parts.path)
    match = re.match(r'^/(?:uk|en)/([^/]+)/?$', path)
    return match.group(1) if match else None


def tail_of(body: str, position: int, span: int = 120) -> str:
    """Plain text right after a link, up to the end of its paragraph or the next link."""
    rest = re.split(r'<a\s|</p>|</li>', body[position:position + span])[0]
    return text_of(rest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', default=LIST_URL)
    args = parser.parse_args()

    body = body_of(fetch(args.url))

    # Walk headings and links together so every link keeps the year heading above it.
    events = [('year', match.start(), match.group(1)) for match in YEAR_RE.finditer(body)]
    events += [('link', match.start(), (*match.groups(), tail_of(body, match.end())))
               for match in LINK_RE.finditer(body)]
    events.sort(key=lambda item: item[1])

    entries: list[dict] = []
    seen: set[str] = set()
    year: int | None = None

    for kind, _position, payload in events:
        if kind == 'year':
            year = int(payload)
            continue
        href, label_markup, tail = payload
        slug = slug_of(href)
        if not slug or slug in NOT_A_DEFENSE or not DEFENSE_SLUG_RE.match(slug) or slug in seen:
            continue
        seen.add(slug)
        label = text_of(label_markup)
        entries.append({
            'slug': slug,
            'url': f'https://hnpu.edu.ua/uk/{slug}',
            'label': label,
            'year': year,
            # The defense date is the fallback for pages that leave «Дата захисту:» blank. It sits
            # at the end of the entry — usually inside the link, sometimes just after it.
            'listDate': parse_ukrainian_date(label) or parse_ukrainian_date(tail),
        })

    without_year = [entry['slug'] for entry in entries if entry['year'] is None]
    if without_year:
        print(f'  ! {len(without_year)} entries above the first year heading '
              f'(e.g. {without_year[0]})', file=sys.stderr)

    write_json(DATA / 'index.json', entries)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
