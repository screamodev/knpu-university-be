#!/usr/bin/env python3
"""
Stage 5 — give every unit a news category and tag the articles that belong to it.

The Новини tab on a faculty page is not a separate collection: it is the shared `articles`
collection filtered by a category whose slug equals the unit slug. This script

  1. creates the missing categories (idempotent, matched by slug), and
  2. adds the category to every article whose title or body matches one of the unit's phrases
     in `news.keywords.json`.

Existing categories on an article are left alone — the M2M junction only gains rows. Re-running
is safe: a link that already exists is skipped.

Usage:
    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 5_tag_news.py --dry-run
    python3 5_tag_news.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent

# Ukrainian / English display names, keyed by unit slug. Kept here rather than read out of the
# frontend's structure.ts so this script stays dependency-free.
CATEGORY_NAMES = {
    'ukrainian-philology': ('ННІ української філології', 'Institute of Ukrainian Philology'),
    'special-education': ('ННІ спеціальної освіти та інклюзії', 'Institute of Special Education and Inclusion'),
    'history-law': ('Факультет історії і права', 'Faculty of History and Law'),
    'mathematics-informatics': ('Факультет математики, інформатики і природничої освіти',
                                'Faculty of Mathematics, Computer Science and Natural Science Education'),
    'arts': ('Факультет мистецтв', 'Faculty of Arts'),
    'foreign-philology': ('Факультет іноземної філології', 'Faculty of Foreign Philology'),
    'preschool': ('Факультет дошкільної освіти', 'Faculty of Preschool Education'),
    'physical-education': ('Факультет фізичного виховання і спорту', 'Faculty of Physical Education and Sports'),
    'social-humanities': ('Факультет соціально-гуманітарних наук і соціальних технологій',
                          'Faculty of Social and Humanitarian Sciences and Social Technologies'),
}

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'application/json',
}


class DirectusError(RuntimeError):
    pass


def env(name: str, fallback: str | None = None) -> str | None:
    return (os.environ.get(name) or '').strip() or fallback


class Directus:
    def __init__(self, base_url: str, token: str) -> None:
        self.base = base_url.rstrip('/')
        self.token = token

    def request(self, method: str, path: str, payload=None) -> dict:
        headers = {**BROWSER_HEADERS, 'Authorization': f'Bearer {self.token}'}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--keywords', default=str(HERE / 'news.keywords.json'))
    parser.add_argument('--url', default=env('DIRECTUS_URL', 'http://localhost:8055'))
    parser.add_argument('--token', default=env('DIRECTUS_TOKEN'))
    parser.add_argument('--email', default=env('DIRECTUS_EMAIL', 'admin@example.com'))
    parser.add_argument('--password', default=env('DIRECTUS_PASSWORD', 'admin'))
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    keywords = json.loads(Path(args.keywords).read_text(encoding='utf-8'))['units']

    token = args.token or login(args.url, args.email, args.password)
    api = Directus(args.url, token)

    # ---- categories ----------------------------------------------------------
    existing = {row['slug']: row['id']
                for row in api.request('GET', '/items/categories?fields=id,slug&limit=-1')['data']}
    category_ids: dict[str, str] = {}
    for slug, (name, name_en) in CATEGORY_NAMES.items():
        if slug in existing:
            category_ids[slug] = existing[slug]
            continue
        if args.dry_run:
            print(f'would create category {slug} ({name})')
            continue
        created = api.request('POST', '/items/categories',
                              payload={'slug': slug, 'name': name, 'nameEn': name_en})
        category_ids[slug] = created['data']['id']
        print(f'+ category {slug}', file=sys.stderr)

    # ---- articles ------------------------------------------------------------
    articles = api.request(
        'GET',
        '/items/articles?fields=id,slug,title,content,categories.categories_id&limit=-1',
    )['data']
    print(f'{len(articles)} articles scanned', file=sys.stderr)

    added = 0
    per_unit: dict[str, int] = {slug: 0 for slug in keywords}
    for article in articles:
        haystack = f"{article.get('title') or ''}\n{article.get('content') or ''}".lower()
        current = {
            link['categories_id'] if isinstance(link['categories_id'], str) else link['categories_id'].get('id')
            for link in (article.get('categories') or [])
            if link.get('categories_id')
        }
        for slug, phrases in keywords.items():
            if not any(phrase.lower() in haystack for phrase in phrases):
                continue
            per_unit[slug] += 1
            category_id = category_ids.get(slug)
            if not category_id or category_id in current:
                continue
            if args.dry_run:
                added += 1
                continue
            api.request('POST', '/items/articles_categories',
                        payload={'articles_id': article['id'], 'categories_id': category_id})
            added += 1

    print('\nMatches per unit:', file=sys.stderr)
    for slug, count in sorted(per_unit.items(), key=lambda item: -item[1]):
        print(f'  {slug:26} {count}', file=sys.stderr)
    print(f'\n{"Would add" if args.dry_run else "Added"} {added} category links', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
