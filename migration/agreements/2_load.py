#!/usr/bin/env python3
"""
Залити `data/agreements.json` у колекцію `cooperation_agreements`.

Ідемпотентно за трійкою (category, number, partner): повторний запуск не створює дублікатів,
тож його можна ганяти скільки завгодно і доливати нові рядки після повторного `1_extract.py`.

    DIRECTUS_URL=http://localhost:8055 DIRECTUS_TOKEN=... python3 2_load.py --dry-run
    DIRECTUS_URL=http://localhost:8055 DIRECTUS_TOKEN=... python3 2_load.py

На проді — внутрішня адреса й статичний токен (див. DEPLOY-2026-08-08.md):

    docker run --rm --network webnet -e DIRECTUS_URL=http://knpu-university-directus:8055 \
      -e DIRECTUS_TOKEN=... -v "$PWD":/w -w /w python:3.12-slim python 2_load.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / 'data'

COLLECTION = 'cooperation_agreements'
IDENTITY = ('category', 'number', 'partner')

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'application/json',
}


class Directus:
    def __init__(self, base: str, token: str):
        self.base = base.rstrip('/')
        self.token = token

    def request(self, method: str, path: str, payload=None):
        headers = dict(BROWSER_HEADERS, Authorization=f'Bearer {self.token}')
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
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
        headers=dict(BROWSER_HEADERS, **{'Content-Type': 'application/json'}), method='POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())['data']['access_token']


def key_of(row: dict) -> tuple:
    return tuple((row.get(field) or '').strip() for field in IDENTITY)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL', 'http://localhost:8055'))
    parser.add_argument('--token', default=os.environ.get('DIRECTUS_TOKEN'))
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL'))
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD'))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()

    token = args.token or (login(args.directus_url, args.email, args.password)
                           if args.email and args.password else None)
    if not token:
        parser.error('потрібен DIRECTUS_TOKEN або DIRECTUS_EMAIL + DIRECTUS_PASSWORD')

    client = Directus(args.directus_url, token)
    rows = json.loads((DATA / 'agreements.json').read_text(encoding='utf-8'))
    if args.limit:
        rows = rows[:args.limit]

    query = urllib.parse.urlencode({'fields': ','.join(('id',) + IDENTITY), 'limit': -1})
    existing = {key_of(row) for row in (client.get(f'/items/{COLLECTION}?{query}') or [])}

    new = [row for row in rows if key_of(row) not in existing]
    print(f'{len(rows)} рядків у файлі, {len(existing)} вже в базі, {len(new)} до створення')
    if args.dry_run or not new:
        return 0

    created = 0
    failed = 0
    for row in new:
        try:
            client.request('POST', f'/items/{COLLECTION}', row)
            created += 1
        except urllib.error.HTTPError as error:
            failed += 1
            print(f'  ! {row["category"]} №{row["number"]}: {error.code} {error.read()[:200]!r}',
                  file=sys.stderr)
        time.sleep(0.03)

    print(f'створено {created}, помилок {failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
