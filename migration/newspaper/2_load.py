#!/usr/bin/env python3
"""
Stage 2 — copy the newspaper PDFs into Directus and create the issue rows.

For every entry in `issues.json`: download the PDF from the old site, upload it into the
«Газета «Учитель»» folder under a sane name, then create or update the `newspaper_issues` row.

Idempotent twice over: uploads are cached in `files.map.json` (source URL → Directus file id) and
rows are matched on `serial`, so a re-run after a new issue appears only does the new work.

`files.map.json` is **environment specific** — file ids from a local Directus do not exist in
production. Move it aside before pointing this at prod.

Usage:
    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 2_load.py --dry-run
    python3 2_load.py --limit 5
    python3 2_load.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).parent
FOLDER_ID = '7c2a5b93-4d18-4f60-8a2e-3b6d90f14c55'  # «Газета «Учитель»», see bootstrap-editor-experience.sh

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'application/pdf,*/*;q=0.8',
    'Accept-Language': 'uk,en;q=0.8',
}


class DirectusError(RuntimeError):
    pass


def env(name: str, fallback: str | None = None) -> str | None:
    return (os.environ.get(name) or '').strip() or fallback


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
            with urllib.request.urlopen(request, timeout=300) as response:
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


def multipart(filename: str, content: bytes, fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f'----knpu{uuid.uuid4().hex}'
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    # The file part must come last: Directus applies the preceding fields to it.
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: application/pdf\r\n\r\n'.encode())
    parts.append(content)
    parts.append(f'\r\n--{boundary}--\r\n'.encode())
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


def download(url: str, timeout: int = 180) -> bytes:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def asset_name(issue: dict) -> str:
    """Legacy names start with `##` and several collide; store something predictable instead."""
    return f"uchytel-{issue['serial']}-{issue['issueDate'][:7]}.pdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--issues', default=str(HERE / 'issues.json'))
    parser.add_argument('--map', dest='map_path', default=str(HERE / 'files.map.json'))
    parser.add_argument('--url', default=env('DIRECTUS_URL', 'http://localhost:8055'))
    parser.add_argument('--token', default=env('DIRECTUS_TOKEN'))
    parser.add_argument('--email', default=env('DIRECTUS_EMAIL', 'admin@example.com'))
    parser.add_argument('--password', default=env('DIRECTUS_PASSWORD', 'admin'))
    parser.add_argument('--limit', type=int, default=0, help='only the N most recent issues')
    parser.add_argument('--from-year', type=int, default=0, help='skip issues older than this year')
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    issues = json.loads(Path(args.issues).read_text(encoding='utf-8'))
    if args.from_year:
        issues = [i for i in issues if int(i['issueDate'][:4]) >= args.from_year]
    if args.limit:
        issues = issues[: args.limit]

    if not str(args.url).startswith(('http://', 'https://')):
        print(f'! DIRECTUS_URL is {args.url!r} — it must start with http:// or https://', file=sys.stderr)
        return 2

    map_path = Path(args.map_path)
    mapping: dict[str, str] = json.loads(map_path.read_text(encoding='utf-8')) if map_path.exists() else {}

    if args.dry_run:
        for index, issue in enumerate(issues, start=1):
            state = 'cached' if issue['sourceUrl'] in mapping else 'to upload'
            print(f'[{index}/{len(issues)}] № {issue["number"]} ({issue["serial"]}) '
                  f'{issue["issueDate"][:7]} — {state} — {asset_name(issue)}')
        print(f'\nDry run — {len(issues)} issues, nothing was written.', file=sys.stderr)
        return 0

    token = args.token or login(args.url, args.email, args.password)
    api = Directus(args.url, token)
    me = api.request('GET', '/users/me?fields=email')
    print(f'Directus {args.url} as {me["data"]["email"]}', file=sys.stderr)

    created = updated = failed = 0
    for index, issue in enumerate(issues, start=1):
        serial = issue['serial']
        try:
            file_id = mapping.get(issue['sourceUrl'])
            if not file_id:
                content = download(issue['sourceUrl'])
                if not content.startswith(b'%PDF'):
                    raise ValueError(f'not a PDF ({len(content)} bytes)')
                body, boundary = multipart(asset_name(issue), content, {
                    'title': f'Газета «Учитель» № {issue["number"]} ({serial})',
                    'folder': FOLDER_ID,
                })
                file_id = api.request('POST', '/files', raw_body=body, content_type=boundary)['data']['id']
                mapping[issue['sourceUrl']] = file_id
                map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

            payload = {
                'number': issue['number'],
                'serial': serial,
                'issueDate': issue['issueDate'],
                'pdfFile': file_id,
                'status': 'published',
            }
            existing = api.request(
                'GET', f'/items/newspaper_issues?filter[serial][_eq]={serial}&fields=id&limit=1')['data']
            if existing:
                api.request('PATCH', f'/items/newspaper_issues/{existing[0]["id"]}', payload=payload)
                updated += 1
            else:
                api.request('POST', '/items/newspaper_issues', payload=payload)
                created += 1
        except (urllib.error.URLError, DirectusError, ValueError, KeyError, TimeoutError, OSError) as exc:
            failed += 1
            print(f'  ! № {serial}: {exc}', file=sys.stderr)
        if index % 10 == 0:
            print(f'  … {index}/{len(issues)}', file=sys.stderr)

    print(f'\nDone. created={created} updated={updated} failed={failed}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
