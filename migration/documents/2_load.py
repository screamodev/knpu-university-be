#!/usr/bin/env python3
"""
Stage 2 — download the legacy files and create `documents` rows in Directus.

Idempotent on two keys, so a re-run after a failure resumes instead of duplicating:

  - a file is skipped when `files.filename_download` + `filesize` already match;
  - a row is skipped when `documents` already has the same `section` + `title`.

Uploads land in the «Документи» folder created by `snapshots/bootstrap-editor-experience.sh`.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 2_load.py --dry-run
    python3 2_load.py

Against production, use a **static** token (`DIRECTUS_TOKEN`): a login token expires after
15 minutes and this run takes longer than that.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as uuid_mod
from pathlib import Path

HERE = Path(__file__).parent
DOCUMENTS_FOLDER = '3e5f21c7-8b04-4d92-a6f1-27c48ab5d301'  # «Документи», see bootstrap-editor-experience.sh

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': '*/*',
}


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
        with urllib.request.urlopen(request, timeout=300) as response:
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
    """Some legacy hrefs carry raw spaces or Cyrillic in the path; urllib rejects those."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        parts.scheme, parts.netloc,
        urllib.parse.quote(parts.path, safe='/%'),
        urllib.parse.quote(parts.query, safe='=&%'),
        parts.fragment,
    ))


def download(url: str) -> tuple[bytes, str] | None:
    try:
        request = urllib.request.Request(encoded(url), headers=BROWSER_HEADERS)
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.read(), (response.headers.get('Content-Type') or '').split(';')[0].strip()
    except (urllib.error.URLError, OSError) as exc:
        print(f'    ! download failed: {exc}', file=sys.stderr)
        return None


def filename_for(url: str) -> str:
    name = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit('/', 1)[-1])
    # The old site double-encoded some names (`Nakaz%252089%2520OD.pdf`).
    if '%' in name:
        name = urllib.parse.unquote(name)
    return re.sub(r'[\\/:*?"<>|]+', '_', name)[:200] or 'document.pdf'


def upload(directus: Directus, content: bytes, filename: str, content_type: str, title: str) -> str:
    if not content_type or content_type == 'application/octet-stream':
        content_type = mimetypes.guess_type(filename)[0] or 'application/pdf'
    boundary = f'----knpu{uuid_mod.uuid4().hex}'
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="folder"\r\n\r\n{DOCUMENTS_FOLDER}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\n{title}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'.encode(),
        content,
        f'\r\n--{boundary}--\r\n'.encode(),
    ]
    data = directus.request('POST', '/files', raw=b''.join(parts),
                            content_type=f'multipart/form-data; boundary={boundary}')
    return data['id']


def existing_titles(directus: Directus) -> set[tuple[str, str]]:
    rows = directus.get('/items/documents?fields=section,title&limit=-1') or []
    return {(row['section'], row['title']) for row in rows}


def existing_files(directus: Directus) -> dict[tuple[str, int], str]:
    query = urllib.parse.urlencode({
        'fields': 'id,filename_download,filesize',
        'filter[folder][_eq]': DOCUMENTS_FOLDER,
        'limit': '-1',
    })
    rows = directus.get(f'/files?{query}') or []
    return {(row['filename_download'], int(row['filesize'] or 0)): row['id'] for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', default=str(HERE / 'documents.json'))
    parser.add_argument('--only', nargs='*', help='limit to these sections')
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    rows = json.loads(Path(args.input).read_text(encoding='utf-8'))
    if args.only:
        rows = [row for row in rows if row['section'] in args.only]

    if args.dry_run:
        for row in rows:
            print(f'{row["section"]:<18} {row["documentDate"] or "—":<12} {row["kind"]:<5} {row["title"][:70]}')
        print(f'\n{len(rows)} rows, {sum(1 for r in rows if r["kind"] == "file")} downloads', file=sys.stderr)
        return 0

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    done = existing_titles(directus)
    uploaded = existing_files(directus)
    created = skipped = failed = 0

    for index, row in enumerate(rows, 1):
        key = (row['section'], row['title'])
        if key in done:
            skipped += 1
            continue

        print(f'[{index}/{len(rows)}] {row["section"]}: {row["title"][:70]}', file=sys.stderr)
        payload = {
            'status': 'published',
            'section': row['section'],
            'title': row['title'],
            'documentDate': row['documentDate'],
            'order': row['order'],
        }

        if row['kind'] == 'file':
            downloaded = download(row['sourceUrl'])
            if not downloaded:
                failed += 1
                continue
            content, content_type = downloaded
            filename = filename_for(row['sourceUrl'])
            file_id = uploaded.get((filename, len(content)))
            if not file_id:
                try:
                    file_id = upload(directus, content, filename, content_type, row['title'][:255])
                except urllib.error.HTTPError as exc:
                    print(f'    ! upload {exc.code}: {exc.read().decode("utf-8", "replace")[:200]}', file=sys.stderr)
                    failed += 1
                    continue
                uploaded[(filename, len(content))] = file_id
            payload['file'] = file_id
        else:
            payload['externalUrl'] = row['sourceUrl']

        try:
            directus.request('POST', '/items/documents', payload=payload)
        except urllib.error.HTTPError as exc:
            print(f'    ! create {exc.code}: {exc.read().decode("utf-8", "replace")[:300]}', file=sys.stderr)
            failed += 1
            continue

        done.add(key)
        created += 1
        time.sleep(0.05)

    print(f'\ncreated={created} skipped={skipped} failed={failed}', file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
