#!/usr/bin/env python3
"""
Залити `data/programmes.json` у колекцію `programmes`.

Кожна ОП стає окремою сторінкою `/programs/<slug>`: заголовок, рівень, спеціальність, роки
затвердження з покликанням на файл програми й адреса для відгуків. Тіло сторінки збирається тут же
у HTML — сторінка ОП уміє показувати і блоки, і HTML.

Ідемпотентний за `slug`: наявні записи оновлюються, нові створюються. Тексту, якого немає в
джерелі (опис, тривалість, форма навчання, обкладинка), скрипт не вигадує — це наповнює редактор.

    DIRECTUS_URL=http://localhost:8055 DIRECTUS_TOKEN=... python3 2_load.py --dry-run
    DIRECTUS_URL=http://localhost:8055 DIRECTUS_TOKEN=... python3 2_load.py
"""

from __future__ import annotations

import argparse
import html
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
COLLECTION = 'programmes'

LEVEL_NAMES = {
    'bachelor': 'перший (бакалаврський) рівень вищої освіти',
    'master': 'другий (магістерський) рівень вищої освіти',
    'graduate': 'третій (освітньо-науковий) рівень вищої освіти',
}

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
        request = urllib.request.Request(f'{self.base}{path}', data=data, headers=headers,
                                         method=method)
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


def body_html(row: dict) -> str:
    """Тіло сторінки ОП: рівень і спеціальність, роки з файлами, адреса для відгуків."""
    # Рівень уже стоїть у шапці сторінки й у полі опису, тож у тілі його не повторюємо.
    parts: list[str] = []
    if row.get('specialty'):
        parts.append(f'<p><strong>Спеціальність:</strong> {html.escape(row["specialty"])}</p>')

    parts.append('<h2>Освітня програма за роками</h2>')
    parts.append('<ul>')
    for version in row['versions']:
        parts.append(f'<li><a href="{version["file"]}">Освітня програма {version["year"]} року</a></li>')
    parts.append('</ul>')

    if row.get('email'):
        address = html.escape(row['email'])
        parts.append('<p>Відгуки та пропозиції щодо освітньої програми приймаються на електронну '
                     f'адресу <a href="mailto:{address}">{address}</a>.</p>')
    return '\n'.join(parts)


def payload_of(row: dict) -> dict:
    latest = row['versions'][0]['year']
    description = (f'{LEVEL_NAMES[row["level"]].capitalize()}. Чинна редакція — {latest} рік.')
    return {
        'slug': row['slug'],
        'title': row['title'],
        'level': row['level'],
        'description': description,
        'content': body_html(row),
        'status': row.get('status', 'published'),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL', 'http://localhost:8055'))
    parser.add_argument('--token', default=os.environ.get('DIRECTUS_TOKEN'))
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL'))
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD'))
    parser.add_argument('--prune', action='store_true',
                        help='прибрати з колекції програми, яких уже немає в джерелі')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or (login(args.directus_url, args.email, args.password)
                           if args.email and args.password else None)
    if not token:
        parser.error('потрібен DIRECTUS_TOKEN або DIRECTUS_EMAIL + DIRECTUS_PASSWORD')

    client = Directus(args.directus_url, token)
    rows = json.loads((DATA / 'programmes.json').read_text(encoding='utf-8'))

    query = urllib.parse.urlencode({'fields': 'id,slug', 'limit': -1})
    existing = {item['slug']: item['id'] for item in (client.get(f'/items/{COLLECTION}?{query}') or [])}

    new = [row for row in rows if row['slug'] not in existing]
    slugs = {row['slug'] for row in rows}
    gone = [(slug, item_id) for slug, item_id in existing.items() if slug not in slugs]
    print(f'{len(rows)} програм у файлі, {len(existing)} у базі, {len(new)} до створення, '
          f'{len(rows) - len(new)} до оновлення, {len(gone)} зайвих'
          f'{"" if args.prune else " (лишаться — потрібен --prune)"}')
    if args.dry_run:
        return 0

    if args.prune:
        for slug, item_id in gone:
            try:
                client.request('DELETE', f'/items/{COLLECTION}/{item_id}')
            except urllib.error.HTTPError as error:
                print(f'  ! видалення {slug}: {error.code}', file=sys.stderr)
            time.sleep(0.02)
        if gone:
            print(f'видалено {len(gone)}')

    created = updated = failed = 0
    for row in rows:
        payload = payload_of(row)
        try:
            if row['slug'] in existing:
                client.request('PATCH', f'/items/{COLLECTION}/{existing[row["slug"]]}', payload)
                updated += 1
            else:
                client.request('POST', f'/items/{COLLECTION}', payload)
                created += 1
        except urllib.error.HTTPError as error:
            failed += 1
            print(f'  ! {row["slug"]}: {error.code} {error.read()[:200]!r}', file=sys.stderr)
        time.sleep(0.03)

    print(f'створено {created}, оновлено {updated}, помилок {failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
