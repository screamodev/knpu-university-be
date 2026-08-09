#!/usr/bin/env python3
"""
Shared helpers for the pass-2 migration (Education / Science / Divisions).

Nothing here talks to Directus by itself — `load.py` does the writing, the `extract_*.py`
scripts only read the legacy sites and emit JSON.
"""

from __future__ import annotations

import html as html_lib
import json
import mimetypes
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid as uuid_mod
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / '.cache'
DATA = HERE / 'data'

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'uk,en;q=0.8',
}

# Drupal (hnpu.edu.ua) article body, and the Joomla (smc.hnpu.edu.ua) content area.
DRUPAL_BODY_RE = re.compile(r'<div class="field field-name-body.*?</div>\s*</div>\s*</div>', re.S)
JOOMLA_BODY_RE = re.compile(r'<div[^>]*itemprop="articleBody"[^>]*>(.*?)</div>\s*</div>', re.S)
LINK_RE = re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
FILE_RE = re.compile(r'\.(pdf|docx?|xlsx?|pptx?|rtf|odt|zip|jpe?g|png)(\?|$)', re.I)


def text_of(markup: str) -> str:
    return re.sub(r'\s+', ' ', html_lib.unescape(re.sub(r'<[^>]+>', '', markup))).strip()


def fetch(url: str) -> str:
    """Fetch a page once and keep it under `.cache/` so re-runs never re-hit the old site."""
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / (re.sub(r'\W+', '_', url)[-120:] + '.html')
    if cached.exists():
        return cached.read_text(encoding='utf-8')
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=90) as response:
        body = response.read().decode('utf-8', 'replace')
    cached.write_text(body, encoding='utf-8')
    return body


def body_of(page: str) -> str:
    """The editable region of a legacy page — Drupal first, then Joomla, else the whole page."""
    match = DRUPAL_BODY_RE.search(page)
    if match:
        return match.group(0)
    match = JOOMLA_BODY_RE.search(page)
    if match:
        return match.group(1)
    return page


def absolute(url: str, page_url: str) -> str:
    url = html_lib.unescape(url.strip())
    if url.startswith('//'):
        return 'https:' + url
    return urllib.parse.urljoin(page_url, url)


def is_file_url(url: str) -> bool:
    return bool(FILE_RE.search(urllib.parse.urlparse(url).path))


def links_of(page: str, page_url: str) -> list[tuple[str, str]]:
    """(title, absolute url) for every link in the page body, in document order."""
    result: list[tuple[str, str]] = []
    for href, label in LINK_RE.findall(body_of(page)):
        if href.startswith('mailto:') or href.startswith('#') or href.startswith('javascript:'):
            continue
        result.append((text_of(label), absolute(href, page_url)))
    return result


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if isinstance(payload, dict) and 'batches' in payload:
        count = sum(len(batch['rows']) for batch in payload['batches'])
    else:
        count = len(payload)
    print(f'→ {path.name}: {count} rows', file=sys.stderr)


# ── Directus side (used by load.py) ──────────────────────────────────────────

class Directus:
    def __init__(self, base: str, token: str):
        self.base = base.rstrip('/')
        self.token = token

    def request(self, method: str, path: str, payload=None, raw: bytes | None = None,
                content_type: str | None = None):
        headers = {'Authorization': f'Bearer {self.token}'}
        data = raw
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        if content_type:
            headers['Content-Type'] = content_type
        request = urllib.request.Request(f'{self.base}{path}', data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=600) as response:
            body = response.read()
        return json.loads(body)['data'] if body else None

    def get(self, path: str):
        return self.request('GET', path)


def login(base: str, email: str, password: str) -> str:
    request = urllib.request.Request(
        f'{base.rstrip("/")}/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())['data']['access_token']


def encoded(url: str) -> str:
    """Legacy hrefs carry raw spaces and Cyrillic in the path; urllib rejects those."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        parts.scheme, parts.netloc,
        urllib.parse.quote(parts.path, safe='/%'),
        urllib.parse.quote(parts.query, safe='=&%'),
        parts.fragment,
    ))


# What a real file of each kind starts with. The legacy host answers some dead links with an HTML
# error page under HTTP 200; uploading that as `.pdf` is how the site ended up with documents that
# open as «Failed to load PDF document».
MAGIC = {
    '.pdf': (b'%PDF',),
    '.jpg': (b'\xff\xd8\xff',),
    '.jpeg': (b'\xff\xd8\xff',),
    '.png': (b'\x89PNG',),
    '.zip': (b'PK\x03\x04',),
    '.doc': (b'\xd0\xcf\x11\xe0', b'PK\x03\x04'),
    '.docx': (b'PK\x03\x04',),
    '.xls': (b'\xd0\xcf\x11\xe0', b'PK\x03\x04'),
    '.xlsx': (b'PK\x03\x04',),
    '.ppt': (b'\xd0\xcf\x11\xe0', b'PK\x03\x04'),
    '.pptx': (b'PK\x03\x04',),
}

MIN_BYTES = 1024

# A few «.pdf» links are really CMS/PKCS#7 containers — the document plus its qualified electronic
# signature. DER SEQUENCE followed by the signedData OID (1.2.840.113549.1.7.2); a real document,
# not the HTML error page this guard is here to catch.
DER_SEQUENCE = b'\x30\x82'
PKCS7_SIGNED_DATA_OID = b'*\x86H\x86\xf7\r\x01\x07\x02'


def is_signed_container(content: bytes) -> bool:
    return content.startswith(DER_SEQUENCE) and PKCS7_SIGNED_DATA_OID in content[:64]


def looks_like_the_file(url: str, content: bytes) -> str | None:
    """→ reason to reject, or None when the bytes look like the extension promises."""
    if len(content) < MIN_BYTES:
        return f'only {len(content)} bytes'
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    expected = MAGIC.get(suffix)
    if expected and not content.startswith(expected):
        if suffix == '.pdf' and is_signed_container(content):
            return None
        head = content[:16].decode('utf-8', 'replace').strip()
        return f'not a {suffix[1:].upper()} (starts with {head!r})'
    return None


def download(url: str) -> tuple[bytes, str] | None:
    try:
        request = urllib.request.Request(encoded(url), headers=BROWSER_HEADERS)
        with urllib.request.urlopen(request, timeout=600) as response:
            content = response.read()
            content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip()
    except (urllib.error.URLError, OSError) as exc:
        print(f'    ! download failed: {exc}', file=sys.stderr)
        return None

    rejected = looks_like_the_file(url, content)
    if rejected:
        print(f'    ! download rejected: {rejected} — {url}', file=sys.stderr)
        return None
    return content, content_type


def filename_for(url: str) -> str:
    name = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit('/', 1)[-1])
    if '%' in name:
        name = urllib.parse.unquote(name)
    return re.sub(r'[\\/:*?"<>|]+', '_', name)[:200] or 'document.pdf'


def upload(directus: Directus, content: bytes, filename: str, content_type: str,
           title: str, folder: str | None, file_id: str | None = None) -> str:
    """
    Re-host one file. `file_id` asks Directus for that exact uuid — the maps
    (`files.map.json`, `images.map.json`) are committed, so a file keeps the same id in every
    environment and `/assets/<uuid>` inside the migrated content works on production too.
    """
    if not content_type or content_type == 'application/octet-stream':
        content_type = mimetypes.guess_type(filename)[0] or 'application/pdf'
    boundary = f'----knpu{uuid_mod.uuid4().hex}'
    parts = []
    if folder:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="folder"\r\n\r\n{folder}\r\n'.encode())
    if file_id:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="id"\r\n\r\n{file_id}\r\n'.encode())
    parts += [
        f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\n{title}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'.encode(),
        content,
        f'\r\n--{boundary}--\r\n'.encode(),
    ]
    data = directus.request('POST', '/files', raw=b''.join(parts),
                            content_type=f'multipart/form-data; boundary={boundary}')
    return data['id']


def present_file_ids(directus: Directus, ids) -> set[str]:
    """
    Which of these file ids the target already holds. A fresh environment holds none of them,
    so everything the committed map lists has to be uploaded again — with its own id.
    """
    present: set[str] = set()
    unique = [file_id for file_id in dict.fromkeys(ids) if file_id]
    for start in range(0, len(unique), 100):
        chunk = unique[start:start + 100]
        rows = directus.get('/files?fields=id&limit=-1&filter[id][_in]=' + ','.join(chunk)) or []
        present.update(row['id'] for row in rows)
    return present
