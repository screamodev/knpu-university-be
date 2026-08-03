#!/usr/bin/env python3
"""
Upload partner logos into Directus and attach them to the `partners` rows.

The partner rows themselves are seeded by `snapshots/seed-content.sh` (four organisations the
client listed); their logos are not part of the seed because they are binary. This script takes
`logos.json` — a `{ "<partners.slug>": "<image url>" }` map — downloads each image and points
`partners.logo` at the uploaded file.

Like the faculty image loader it writes a committed `logos.map.json` (source URL → file id) and
uploads with an explicit `id`, so the same logo keeps the same uuid in every environment and a
re-run is a no-op.

Usage:
    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin

    python3 load_logos.py --dry-run
    python3 load_logos.py
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).parent
FOLDER_NAME = 'partners'

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'image/avif,image/webp,image/*,*/*;q=0.8',
    'Accept-Language': 'uk,en;q=0.8',
}


class DirectusError(RuntimeError):
    pass


def env(name: str, fallback: str | None = None) -> str | None:
    value = (os.environ.get(name) or '').strip()
    return value or fallback


class Directus:
    def __init__(self, base_url: str, token: str) -> None:
        self.base = base_url.rstrip('/')
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None,
                raw_body: bytes | None = None, content_type: str | None = None) -> dict:
        headers = {**BROWSER_HEADERS, 'Authorization': f'Bearer {self.token}',
                   'Accept': 'application/json'}
        data = raw_body
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        elif content_type:
            headers['Content-Type'] = content_type
        request = urllib.request.Request(f'{self.base}{path}', data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise DirectusError(f'{method} {path} → HTTP {exc.code}: '
                                f'{exc.read().decode("utf-8", "replace")[:300]}') from None
        return json.loads(body) if body else {}


def login(base_url: str, email: str, password: str) -> str:
    request = urllib.request.Request(
        f'{base_url.rstrip("/")}/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode('utf-8'),
        headers={**BROWSER_HEADERS, 'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())['data']['access_token']


def multipart(filename: str, content: bytes, content_type: str, fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f'----knpu{uuid.uuid4().hex}'
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    # The file part must come last: Directus applies the preceding fields to it.
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'.encode())
    parts.append(content)
    parts.append(f'\r\n--{boundary}--\r\n'.encode())
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


def download(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip()
        return response.read(), content_type


def ensure_folder(api: Directus) -> str | None:
    existing = api.request('GET', f'/folders?filter[name][_eq]={FOLDER_NAME}&fields=id&limit=1')['data']
    if existing:
        return existing[0]['id']
    return api.request('POST', '/folders', payload={'name': FOLDER_NAME})['data']['id']


def filename_for(url: str) -> str:
    name = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit('/', 1)[-1])
    return name or 'logo.png'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--logos', default=str(HERE / 'logos.json'))
    parser.add_argument('--map', dest='map_path', default=str(HERE / 'logos.map.json'))
    parser.add_argument('--url', default=env('DIRECTUS_URL', 'http://localhost:8055'))
    parser.add_argument('--token', default=env('DIRECTUS_TOKEN'))
    parser.add_argument('--email', default=env('DIRECTUS_EMAIL', 'admin@example.com'))
    parser.add_argument('--password', default=env('DIRECTUS_PASSWORD', 'admin'))
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logos = {slug: url for slug, url in
             json.loads(Path(args.logos).read_text(encoding='utf-8')).items()
             if not slug.startswith('_')}

    map_path = Path(args.map_path)
    mapping: dict[str, str] = json.loads(map_path.read_text(encoding='utf-8')) if map_path.exists() else {}

    if not str(args.url).startswith(('http://', 'https://')):
        print(f'! DIRECTUS_URL is {args.url!r} — it must start with http:// or https://', file=sys.stderr)
        return 2

    if args.dry_run:
        for slug, url in logos.items():
            print(f'{slug:32} {mapping.get(url, "<new id>")}  ←  {url}')
        return 0

    token = args.token or login(args.url, args.email, args.password)
    api = Directus(args.url, token)
    folder = ensure_folder(api)

    attached = skipped = failed = 0
    for slug, url in logos.items():
        rows = api.request('GET', f'/items/partners?filter[slug][_eq]={slug}&fields=id,logo&limit=1')['data']
        if not rows:
            print(f'! no partner with slug {slug!r} — skipped', file=sys.stderr)
            failed += 1
            continue
        partner = rows[0]

        file_id = mapping.get(url) or str(uuid.uuid4())
        exists = api.request('GET', f'/files?filter[id][_eq]={file_id}&fields=id&limit=1')['data']

        if not exists:
            try:
                content, content_type = download(url)
            except (urllib.error.URLError, urllib.error.HTTPError) as exc:
                print(f'! download failed for {slug}: {exc}', file=sys.stderr)
                failed += 1
                continue

            filename = filename_for(url)
            if not content_type or content_type == 'application/octet-stream':
                content_type = mimetypes.guess_type(filename)[0] or 'image/png'

            fields = {'id': file_id, 'title': f'{slug} logo'}
            if folder:
                fields['folder'] = folder
            body, multipart_type = multipart(filename, content, content_type, fields)
            api.request('POST', '/files', raw_body=body, content_type=multipart_type)

        mapping[url] = file_id

        if partner.get('logo') == file_id:
            skipped += 1
            continue

        api.request('PATCH', f'/items/partners/{partner["id"]}', payload={'logo': file_id})
        attached += 1
        print(f'{slug:32} → {file_id}')

    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'\nattached={attached} already-set={skipped} failed={failed}', file=sys.stderr)
    return 0 if not failed else 1


if __name__ == '__main__':
    raise SystemExit(main())
