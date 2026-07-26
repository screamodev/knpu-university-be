#!/usr/bin/env python3
"""
Stage 3 — load the transformed articles into Directus.

Everything goes through the REST API rather than SQL: uploads have to create
`directus_files` rows *and* storage objects, and the API keeps ids, hooks and
permissions consistent. The load is **idempotent** — articles are matched by
`slug`, so a second run updates instead of duplicating, and covers already
uploaded are reused via `covers.map.json`.

Usage (local):
    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 3_load.py --dry-run
    python3 3_load.py --limit 10        # trial run
    python3 3_load.py                   # everything

Usage (prod): same, with DIRECTUS_URL/credentials (or DIRECTUS_TOKEN) pointing
at production. Always do a --dry-run first.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_CATEGORY_SLUG = 'university-news'

# Production sits behind Cloudflare, which answers "error code: 1010" (banned browser
# signature) to urllib's default User-Agent. Presenting normal browser headers clears it.
BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9,uk;q=0.8',
}


class DirectusError(RuntimeError):
    pass


class Directus:
    def __init__(self, base_url: str, token: str) -> None:
        self.base = base_url.rstrip('/')
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None,
                raw_body: bytes | None = None, content_type: str | None = None) -> dict:
        url = f'{self.base}{path}'
        data = raw_body
        headers = {**BROWSER_HEADERS, 'Authorization': f'Bearer {self.token}'}
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        elif content_type:
            headers['Content-Type'] = content_type

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', 'replace')[:500]
            raise DirectusError(f'{method} {path} → HTTP {exc.code}: {detail}') from None
        except urllib.error.URLError as exc:
            raise DirectusError(f'{method} {path} → {exc.reason}') from None
        return json.loads(body) if body else {}

    def get(self, path: str) -> dict:
        return self.request('GET', path)


def login(base_url: str, email: str, password: str) -> str:
    req = urllib.request.Request(
        f'{base_url.rstrip("/")}/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode('utf-8'),
        headers={**BROWSER_HEADERS, 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read())['data']['access_token']
    except urllib.error.HTTPError as exc:
        raise DirectusError(f'login failed: HTTP {exc.code} {exc.read().decode("utf-8", "replace")[:200]}') from None


def download(url: str, timeout: int = 60) -> tuple[bytes, str]:
    """Fetch a legacy asset. The old host is http-only (its certificate expired)."""
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip()
        return response.read(), content_type


def multipart_body(field_name: str, filename: str, content: bytes, content_type: str,
                   extra_fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f'----knpu{uuid.uuid4().hex}'
    parts: list[bytes] = []
    for key, value in extra_fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode('utf-8')
        )
    # The file part must come last: Directus applies preceding fields to it.
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'.encode('utf-8')
    )
    parts.append(content)
    parts.append(f'\r\n--{boundary}--\r\n'.encode('utf-8'))
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


def env(name: str, fallback: str | None = None) -> str | None:
    """`docker run -e VAR=$UNSET` passes an *empty* value, so treat blank as unset."""
    value = (os.environ.get(name) or '').strip()
    return value or fallback


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--in', dest='src', default=str(HERE / 'articles.json'))
    parser.add_argument('--url', default=env('DIRECTUS_URL', 'http://localhost:8055'))
    parser.add_argument('--token', default=env('DIRECTUS_TOKEN'))
    parser.add_argument('--email', default=env('DIRECTUS_EMAIL', 'admin@example.com'))
    parser.add_argument('--password', default=env('DIRECTUS_PASSWORD', 'admin'))
    parser.add_argument('--category-slug', default=DEFAULT_CATEGORY_SLUG,
                        help='category assigned to every migrated article')
    parser.add_argument('--limit', type=int, default=0, help='only process the first N articles')
    parser.add_argument('--skip-covers', action='store_true', help='do not upload cover images')
    parser.add_argument('--dry-run', action='store_true', help='report what would happen, change nothing')
    parser.add_argument('--covers-map', default=str(HERE / 'covers.map.json'))
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Fail loudly on a blank/typo'd target instead of building a relative URL.
    if not str(args.url).startswith(('http://', 'https://')):
        print(
            f'! DIRECTUS_URL is {args.url!r} — it must start with http:// or https://\n'
            '  If you passed -e DIRECTUS_URL=$PROD_URL, that variable is empty in this shell.\n'
            '  Check with:  echo $PROD_URL',
            file=sys.stderr,
        )
        return 2

    articles = json.loads(Path(args.src).read_text(encoding='utf-8'))
    if args.limit:
        articles = articles[: args.limit]

    if args.token:
        print(f'Authenticating to {args.url} with a static token', file=sys.stderr)
    else:
        print(f'No DIRECTUS_TOKEN given — logging in to {args.url} as {args.email}', file=sys.stderr)

    try:
        token = args.token or login(args.url, args.email, args.password)
        api = Directus(args.url, token)
        me = api.get('/users/me?fields=email')
    except (DirectusError, urllib.error.URLError) as exc:
        print(
            f'! Could not authenticate against {args.url}\n'
            f'  {exc}\n'
            + ('  This is Cloudflare, not Directus: code 1010 = blocked browser signature.\n'
               '  Add a WAF skip rule for your IP, or run the loader from the prod host itself.\n'
               if 'error code: 1010' in str(exc) or 'Cloudflare' in str(exc) else '')
            + '  Common causes:\n'
            '    - DIRECTUS_URL/DIRECTUS_TOKEN are empty in this shell (check: echo $PROD_URL $PROD_TOKEN)\n'
            '    - the token is wrong, expired, or has no access to articles/files\n'
            '    - running against localhost from a container: use http://host.docker.internal:8055',
            file=sys.stderr,
        )
        return 2

    categories = api.get(f'/items/categories?filter[slug][_eq]={args.category_slug}&fields=id,name&limit=1')['data']
    if not categories:
        print(f'! category {args.category_slug!r} not found in {args.url}', file=sys.stderr)
        return 1
    category_id = categories[0]['id']
    print(f'Directus {args.url} as {me["data"]["email"]}; category {categories[0]["name"]!r}', file=sys.stderr)

    covers_map_path = Path(args.covers_map)
    covers_map: dict[str, str] = json.loads(covers_map_path.read_text()) if covers_map_path.exists() else {}

    created = updated = skipped_cover = failed_cover = 0

    for index, article in enumerate(articles, start=1):
        slug = article['slug']

        existing = api.get(f'/items/articles?filter[slug][_eq]={slug}&fields=id,cover&limit=1')['data']
        existing_item = existing[0] if existing else None

        # ---- cover -----------------------------------------------------
        cover_id = existing_item.get('cover') if existing_item else None
        source = article.get('cover_source_url')
        if source and not args.skip_covers and not cover_id:
            cover_id = covers_map.get(source)
            if not cover_id and not args.dry_run:
                try:
                    content, content_type = download(source)
                    filename = source.rsplit('/', 1)[-1][:200] or f'{slug}.jpg'
                    if not content_type or content_type == 'application/octet-stream':
                        content_type = mimetypes.guess_type(filename)[0] or 'image/jpeg'
                    body, ct = multipart_body(
                        'file', filename, content, content_type,
                        {'title': article['title'][:255]},
                    )
                    result = api.request('POST', '/files', raw_body=body, content_type=ct)
                    cover_id = result['data']['id']
                    covers_map[source] = cover_id
                    covers_map_path.write_text(json.dumps(covers_map, ensure_ascii=False, indent=2))
                except (urllib.error.URLError, DirectusError, KeyError, TimeoutError) as exc:
                    failed_cover += 1
                    print(f'  ! cover failed for {slug}: {exc}', file=sys.stderr)
                    cover_id = None
        elif not source:
            skipped_cover += 1

        # ---- article ---------------------------------------------------
        payload = {
            'title': article['title'],
            'slug': slug,
            'excerpt': article['excerpt'],
            'content': article['content'],
            'status': article['status'],
            'date_published': article['date_published'],
            'category': category_id,
        }
        if cover_id:
            payload['cover'] = cover_id

        action = 'update' if existing_item else 'create'
        if args.dry_run:
            print(f'[{index}/{len(articles)}] would {action}: {slug} '
                  f'({len(article["content"])} chars, cover={"yes" if cover_id or source else "no"})')
        else:
            if existing_item:
                api.request('PATCH', f'/items/articles/{existing_item["id"]}', payload=payload)
                updated += 1
            else:
                api.request('POST', '/items/articles', payload=payload)
                created += 1
            if index % 25 == 0:
                print(f'  … {index}/{len(articles)}', file=sys.stderr)
            time.sleep(0.02)  # keep the API comfortable

    print(
        f'\nDone. created={created} updated={updated} '
        f'articles_without_image={skipped_cover} cover_failures={failed_cover}',
        file=sys.stderr,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
