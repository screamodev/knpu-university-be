#!/usr/bin/env python3
"""
Stage 5 — give every unit a news category and tag the articles that belong to it.

The Новини tab on a faculty page is not a separate collection: it is the shared `articles`
collection filtered by that unit's category (`newsCategorySlug` in structure.ts). This script

  1. makes sure each unit's category exists — matched on the slug it already has in Directus,
     which is transliterated from the Ukrainian name — and
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

# Unit slug → (category slug in Directus, uk name, en name).
#
# The category slugs are transliterated from the Ukrainian names, because the categories were
# seeded that way before this script existed. They must match `newsCategorySlug` in the
# frontend's app/utils/structure.ts — that is what the faculty News tab queries.
CATEGORIES = {
    'ukrainian-philology': ('navchalno-naukovyi-instytut-ukrainskoi-filolohii',
                            'ННІ української філології', 'Institute of Ukrainian Philology'),
    'special-education': ('instytut-spetsialnoyi-osvity-ta-inklyuziyi',
                          'ННІ спеціальної освіти та інклюзії',
                          'Institute of Special Education and Inclusion'),
    'history-law': ('fakultet-istoriyi-i-prava',
                    'Факультет історії і права', 'Faculty of History and Law'),
    'mathematics-informatics': ('fakultet-matematyky-informatyky-i-pryrodnychoyi-osvity',
                                'Факультет математики, інформатики і природничої освіти',
                                'Faculty of Mathematics, Computer Science and Natural Science Education'),
    'arts': ('fakultet-mystetstv', 'Факультет мистецтв', 'Faculty of Arts'),
    'foreign-philology': ('fakultet-inozemnoyi-filolohiyi',
                          'Факультет іноземної філології', 'Faculty of Foreign Philology'),
    'preschool': ('fakultet-doshkilnoyi-osvity',
                  'Факультет дошкільної освіти', 'Faculty of Preschool Education'),
    'physical-education': ('fakultet-fizychnoho-vykhovannya-i-sportu',
                           'Факультет фізичного виховання і спорту',
                           'Faculty of Physical Education and Sports'),
    'social-humanities': ('fakultet-sotsialno-humanitarnykh-nauk-i-sotsialnykh-tekhnolohiy',
                          'Факультет соціально-гуманітарних наук і соціальних технологій',
                          'Faculty of Social and Humanitarian Sciences and Social Technologies'),
    'postgraduate': ('aspirantura-i-doktorantura',
                     'Аспірантура і докторантура', 'Postgraduate and Doctoral Studies'),
    # Not a unit: «Оголошення» is university-wide, and the postgraduate page shows it on a tab of
    # its own. Kept here so the one script owns every category the migration relies on.
    'announcements': ('ogoloshennya', 'Оголошення', 'Announcements'),
    # Also not a unit: the student parliament page carries its own news feed.
    'student-parliament': ('studentskyi-parlament',
                           'Студентський парламент', 'Student Parliament'),
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
    rows = api.request('GET', '/items/categories?fields=id,slug,name&limit=-1')['data']
    by_slug = {row['slug']: row for row in rows}
    by_name = {row['name']: row for row in rows}

    category_ids: dict[str, str] = {}
    for unit, (category_slug, name, name_en) in CATEGORIES.items():
        if category_slug in by_slug:
            category_ids[unit] = by_slug[category_slug]['id']
            continue

        # `name` is unique in Directus, and an environment may already carry this category under
        # a slug someone else chose (the faculty categories arrived that way, transliterated by
        # an earlier seeding path). Adopt that row and align its slug, which is what the frontend
        # queries by — creating a second row would fail on the unique name anyway.
        clash = by_name.get(name)
        if clash:
            if args.dry_run:
                print(f'would re-slug category {clash["slug"]!r} → {category_slug!r} ({name})')
                category_ids[unit] = clash['id']
                continue
            api.request('PATCH', f'/items/categories/{clash["id"]}', payload={'slug': category_slug})
            category_ids[unit] = clash['id']
            print(f'~ category {name}: slug {clash["slug"]!r} → {category_slug!r}', file=sys.stderr)
            continue

        if args.dry_run:
            print(f'would create category {category_slug} ({name})')
            continue
        created = api.request('POST', '/items/categories',
                              payload={'slug': category_slug, 'name': name, 'nameEn': name_en})
        category_ids[unit] = created['data']['id']
        print(f'+ category {category_slug}', file=sys.stderr)

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
