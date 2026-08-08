#!/usr/bin/env python3
"""
Helpers shared by the `razovi-rady` scripts.

The heavy lifting — HTTP with browser headers, the Directus client, uploads — already exists in
`../pass2/common.py`, so this module re-exports it. The only thing it replaces is the page cache:
263 defense pages should land in this folder's `.cache/`, not in pass 2's.
"""

from __future__ import annotations

import datetime
import html as html_lib
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / 'pass2'))

from common import (  # noqa: E402  (path juggling has to come first)
    BROWSER_HEADERS,
    Directus,
    body_of,
    download,
    encoded,
    filename_for,
    login,
    text_of,
    upload,
    write_json,
)

__all__ = [
    'BROWSER_HEADERS', 'Directus', 'body_of', 'download', 'encoded', 'filename_for', 'login',
    'text_of', 'upload', 'write_json',
    'CACHE', 'DATA', 'LIST_URL', 'LIST_SLUG', 'NEW_INDEX_PATH', 'NEW_PAGE_PREFIX',
    'fetch', 'legacy_path_of', 'legacy_file_url', 'is_legacy_file', 'iso_date',
    'parse_ukrainian_date', 'unescape',
]

CACHE = HERE / '.cache'
DATA = HERE / 'data'

LIST_SLUG = 'razovi-specializovani-vcheni-rady'
LIST_URL = f'https://hnpu.edu.ua/uk/{LIST_SLUG}'

# Where the archive lives on the new site.
NEW_INDEX_PATH = '/science/dissertation-councils'
NEW_PAGE_PREFIX = '/science/dissertation-councils/'

LEGACY_HOST_RE = re.compile(r'^https?://(?:www\.)?hnpu\.edu\.ua(?=/)', re.I)
LEGACY_FILES_PREFIX = '/sites/default/files/'

UKRAINIAN_MONTHS = {
    'січня': 1, 'лютого': 2, 'березня': 3, 'квітня': 4, 'травня': 5, 'червня': 6,
    'липня': 7, 'серпня': 8, 'вересня': 9, 'жовтня': 10, 'листопада': 11, 'грудня': 12,
}


def unescape(value: str) -> str:
    return html_lib.unescape(value or '')


def fetch(url: str) -> str:
    """Fetch a page once and keep it under `.cache/`, so re-runs never re-hit the old site."""
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / (re.sub(r'\W+', '_', url)[-120:] + '.html')
    if cached.exists():
        return cached.read_text(encoding='utf-8')
    request = urllib.request.Request(encoded(url), headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=90) as response:
        body = response.read().decode('utf-8', 'replace')
    cached.write_text(body, encoding='utf-8')
    return body


def legacy_path_of(url: str) -> str | None:
    """
    The old site's own path for a file, or `None` if the link points somewhere else.

    Hrefs come in three shapes on the legacy pages — absolute, protocol-relative and
    root-relative — and all three must collapse to the same key, because that key is both the
    upload cache key and the redirect we have to keep alive:

        https://hnpu.edu.ua/sites/default/files/a%20b.pdf ┐
        //hnpu.edu.ua/sites/default/files/a b.pdf         ├→ /sites/default/files/a b.pdf
        /sites/default/files/a b.pdf                      ┘
    """
    value = unescape(url).strip()
    if not value:
        return None
    if value.startswith('//'):
        value = 'https:' + value
    value = LEGACY_HOST_RE.sub('', value)
    if not value.startswith(LEGACY_FILES_PREFIX):
        return None
    path = value.split('?')[0].split('#')[0]
    # A few links in the older maps are encoded twice (`%2520` for a space). Unquote until it
    # settles, otherwise the stored key never matches what a browser asks for.
    for _ in range(3):
        unquoted = urllib.parse.unquote(path)
        if unquoted == path:
            break
        path = unquoted
    return path


def legacy_file_url(legacy_path: str) -> str:
    """The canonical download URL for a legacy path — `download()` percent-encodes it."""
    return f'https://hnpu.edu.ua{legacy_path}'


def is_legacy_file(url: str) -> bool:
    return legacy_path_of(url) is not None


def iso_date(year: int, month: int, day: int) -> str | None:
    """Only a date that exists — the old site has typos like «31.09» that Directus rejects."""
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_ukrainian_date(text: str) -> str | None:
    """«6 грудня 2025 року» or «06.12.2025» → `2025-12-06`."""
    if not text:
        return None
    match = re.search(r'(\d{1,2})\s+([а-яіїєґ]+)\s+(\d{4})', text, re.I)
    if match:
        month = UKRAINIAN_MONTHS.get(match.group(2).lower())
        if month:
            parsed = iso_date(int(match.group(3)), month, int(match.group(1)))
            if parsed:
                return parsed
    match = re.search(r'(\d{1,2})[.\s](\d{1,2})[.\s](\d{4})', text)
    if match:
        day, month, year = (int(part) for part in match.groups())
        return iso_date(year, month, day)
    return None
