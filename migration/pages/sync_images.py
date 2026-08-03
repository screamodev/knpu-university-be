#!/usr/bin/env python3
"""
Copy the images referenced by the migrated static pages from one Directus to another, keeping
their ids.

`migrate_page.py` uploads images to whichever Directus it is pointed at and writes the resulting
`/assets/<uuid>` into the content JSON. Those files are committed with that uuid baked in, so the
same uuid has to exist in every environment — the same constraint `../structure-pages` solves
with `images.map.json`. Directus accepts an explicit `id` on upload, so this copies the bytes
across and keeps the reference valid.

    export SOURCE_URL=http://localhost:8055 SOURCE_TOKEN=…      # or SOURCE_EMAIL/SOURCE_PASSWORD
    export TARGET_URL=https://cms.example.com TARGET_TOKEN=…    # static token on prod
    python3 sync_images.py --dry-run
    python3 sync_images.py

Idempotent: a file already present on the target is skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid as uuid_mod
from pathlib import Path

HERE = Path(__file__).parent
CONTENT_ROOTS = [
    HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'pages',
    HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'structure',
]
ASSET_RE = re.compile(r'/assets/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.I)


def login(base: str, email: str, password: str) -> str:
    request = urllib.request.Request(
        f'{base.rstrip("/")}/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())['data']['access_token']


def api(base: str, token: str, path: str):
    request = urllib.request.Request(f'{base.rstrip("/")}{path}', headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())['data']


def referenced_ids(roots: list[Path]) -> set[str]:
    """Every asset uuid mentioned by the committed static content under `roots`."""
    found: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob('*.json'):
            found.update(match.lower() for match in ASSET_RE.findall(path.read_text(encoding='utf-8')))
    return found


def download(base: str, token: str, file_id: str) -> bytes:
    request = urllib.request.Request(f'{base.rstrip("/")}/assets/{file_id}',
                                     headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def upload(base: str, token: str, file_id: str, meta: dict, content: bytes) -> None:
    filename = meta.get('filename_download') or f'{file_id}.bin'
    content_type = meta.get('type') or 'application/octet-stream'
    boundary = f'----knpu{uuid_mod.uuid4().hex}'
    fields = [('id', file_id), ('title', meta.get('title') or filename)]
    if meta.get('folder'):
        fields.append(('folder', meta['folder']))

    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
             for name, value in fields]
    parts += [
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'.encode(),
        content,
        f'\r\n--{boundary}--\r\n'.encode(),
    ]
    request = urllib.request.Request(
        f'{base.rstrip("/")}/files', data=b''.join(parts),
        headers={'Authorization': f'Bearer {token}',
                 'Content-Type': f'multipart/form-data; boundary={boundary}'}, method='POST')
    with urllib.request.urlopen(request, timeout=300):
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source-url', default=os.environ.get('SOURCE_URL') or 'http://localhost:8055')
    parser.add_argument('--source-token', default=(os.environ.get('SOURCE_TOKEN') or '').strip() or None)
    parser.add_argument('--source-email', default=os.environ.get('SOURCE_EMAIL') or 'admin@example.com')
    parser.add_argument('--source-password', default=os.environ.get('SOURCE_PASSWORD') or 'admin')
    parser.add_argument('--target-url', default=os.environ.get('TARGET_URL'))
    parser.add_argument('--target-token', default=(os.environ.get('TARGET_TOKEN') or '').strip() or None)
    parser.add_argument('--path', action='append', metavar='DIR',
                        help='limit the scan to these content directories; repeatable. '
                             'Defaults to every static content root, which on a deploy means '
                             're-checking the ~1 800 faculty images already on the target.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    roots = [Path(path) for path in args.path] if args.path else CONTENT_ROOTS
    ids = sorted(referenced_ids(roots))
    print(f'{len(ids)} asset(s) referenced by the static content', file=sys.stderr)
    if not args.dry_run and not (args.target_url and args.target_token):
        print('! TARGET_URL and TARGET_TOKEN are required', file=sys.stderr)
        return 2

    source_token = args.source_token or login(args.source_url, args.source_email, args.source_password)

    copied = skipped = missing = 0
    for file_id in ids:
        try:
            meta = api(args.source_url, source_token, f'/files/{file_id}'
                       '?fields=id,filename_download,type,title,folder,filesize')
        except urllib.error.HTTPError as exc:
            print(f'  ! {file_id}: not on the source ({exc.code})', file=sys.stderr)
            missing += 1
            continue

        if args.dry_run:
            print(f'  {file_id}  {meta.get("filename_download")}  {meta.get("filesize")} B')
            continue

        try:
            api(args.target_url, args.target_token, f'/files/{file_id}?fields=id')
            skipped += 1
            continue
        except urllib.error.HTTPError as exc:
            if exc.code not in (403, 404):
                raise

        try:
            upload(args.target_url, args.target_token, file_id, meta,
                   download(args.source_url, source_token, file_id))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', 'replace')[:300]
            print(f'  ! {file_id}: upload failed HTTP {exc.code} {detail}', file=sys.stderr)
            if exc.code in (401, 403):
                print('    the target token needs create access to directus_files — use the '
                      'admin static token, not the read-only site-preview one', file=sys.stderr)
            missing += 1
            continue
        print(f'  + {file_id}  {meta.get("filename_download")}', file=sys.stderr)
        copied += 1

    if not args.dry_run:
        print(f'\ncopied={copied} skipped={skipped} missing={missing}', file=sys.stderr)
    return 1 if missing else 0


if __name__ == '__main__':
    raise SystemExit(main())
