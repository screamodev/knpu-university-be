#!/usr/bin/env python3
"""
Stage 3 — copy the images referenced by the faculty pages into Directus.

The legacy host serves them over plain HTTP and will eventually be switched off, so every
picture is downloaded and uploaded into a `structure-pages` folder. The mapping
`source URL → Directus file id` is cached in `images.map.json`; stage 4 uses it to rewrite
`<img src>` to `/assets/<uuid>`.

The cache is **environment specific** — file ids from a local Directus do not exist in
production. Move or delete it when switching targets.

Usage:
    export DIRECTUS_URL=http://host.docker.internal:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 3_load_images.py --dry-run
    python3 3_load_images.py --limit 20
    python3 3_load_images.py
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).parent
FOLDER_NAME = 'structure-pages'

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


def download(url: str, timeout: int = 60) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip()
        return response.read(), content_type


def ensure_folder(api: Directus) -> str | None:
    existing = api.request('GET', f'/folders?filter[name][_eq]={FOLDER_NAME}&fields=id&limit=1')['data']
    if existing:
        return existing[0]['id']
    return api.request('POST', '/folders', payload={'name': FOLDER_NAME})['data']['id']


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--images', default=str(HERE / 'images.list.json'))
    parser.add_argument('--map', dest='map_path', default=str(HERE / 'images.map.json'))
    parser.add_argument('--url', default=env('DIRECTUS_URL', 'http://localhost:8055'))
    parser.add_argument('--token', default=env('DIRECTUS_TOKEN'))
    parser.add_argument('--email', default=env('DIRECTUS_EMAIL', 'admin@example.com'))
    parser.add_argument('--password', default=env('DIRECTUS_PASSWORD', 'admin'))
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    urls = json.loads(Path(args.images).read_text(encoding='utf-8'))
    map_path = Path(args.map_path)
    mapping: dict[str, str] = json.loads(map_path.read_text(encoding='utf-8')) if map_path.exists() else {}

    todo = [url for url in urls if url not in mapping]
    if args.limit:
        todo = todo[: args.limit]

    print(f'{len(urls)} images referenced · {len(mapping)} already uploaded · {len(todo)} to do',
          file=sys.stderr)
    if args.dry_run or not todo:
        for url in todo[:20]:
            print(f'would upload {url}')
        return 0

    if not str(args.url).startswith(('http://', 'https://')):
        print(f'! DIRECTUS_URL is {args.url!r} — it must start with http:// or https://', file=sys.stderr)
        return 2

    token = args.token or login(args.url, args.email, args.password)
    api = Directus(args.url, token)
    folder = ensure_folder(api)

    uploaded = failed = 0
    for index, url in enumerate(todo, start=1):
        try:
            content, content_type = download(url)
            filename = url.rsplit('/', 1)[-1][:200] or 'image.jpg'
            if not content_type or content_type == 'application/octet-stream':
                content_type = mimetypes.guess_type(filename)[0] or 'image/jpeg'
            if not content_type.startswith('image/'):
                raise ValueError(f'not an image ({content_type})')
            fields = {'title': filename}
            if folder:
                fields['folder'] = folder
            body, boundary = multipart(filename, content, content_type, fields)
            result = api.request('POST', '/files', raw_body=body, content_type=boundary)
            mapping[url] = result['data']['id']
            uploaded += 1
        except (urllib.error.URLError, DirectusError, ValueError, KeyError, TimeoutError, OSError) as exc:
            failed += 1
            print(f'  ! {url}: {exc}', file=sys.stderr)
        if index % 25 == 0:
            map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'  … {index}/{len(todo)}', file=sys.stderr)

    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'\nDone. uploaded={uploaded} failed={failed} → {map_path}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
