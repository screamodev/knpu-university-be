#!/usr/bin/env python3
"""
Stage 7 — take faculty categories off university-wide news.

`5_tag_news.py` tags an article when a unit's phrase appears anywhere in its title or body. That
is right for «Студенти факультету мистецтв здобули…» and wrong for «Засідання Виконавчої ради»,
which simply lists every faculty in passing — such an article ends up in the news feed of all of
them at once.

The rule here: an article carrying `--threshold` or more unit categories is university-wide, so
its unit categories are removed. A unit named in the **title** is a deliberate signal and is kept
— that alone is enough to keep «Тиждень факультету мистецтв» on the right page.

Non-unit categories («Новини університету», «Оголошення», …) are never touched, and neither are
articles below the threshold.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 7_fix_overtagged.py --dry-run
    python3 7_fix_overtagged.py
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

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'application/json',
}


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
        request = urllib.request.Request(f'{self.base}{path}', data=data,
                                         headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'{method} {path} → HTTP {exc.code}: '
                               f'{exc.read().decode("utf-8", "replace")[:300]}') from None
        return json.loads(body) if body else {}


def login(base_url: str, email: str, password: str) -> str:
    request = urllib.request.Request(
        f'{base_url.rstrip("/")}/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode('utf-8'),
        headers={**BROWSER_HEADERS, 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())['data']['access_token']


def env(name: str, fallback: str | None = None) -> str | None:
    return (os.environ.get(name) or '').strip() or fallback


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--keywords', default=str(HERE / 'news.keywords.json'))
    parser.add_argument('--threshold', type=int, default=3,
                        help='this many unit categories on one article means university-wide '
                             '(default: 3)')
    parser.add_argument('--url', default=env('DIRECTUS_URL', 'http://localhost:8055'))
    parser.add_argument('--token', default=env('DIRECTUS_TOKEN'))
    parser.add_argument('--email', default=env('DIRECTUS_EMAIL', 'admin@example.com'))
    parser.add_argument('--password', default=env('DIRECTUS_PASSWORD', 'admin'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    # `5_tag_news.py` owns the unit → category mapping; import it rather than restating it.
    import importlib.util
    spec = importlib.util.spec_from_file_location('tag_news', HERE / '5_tag_news.py')
    tag_news = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tag_news)
    unit_slugs = {slug for slug, _, _ in tag_news.CATEGORIES.values()}

    keywords = json.loads(Path(args.keywords).read_text(encoding='utf-8'))['units']

    token = args.token or login(args.url, args.email, args.password)
    api = Directus(args.url, token)

    categories = api.request('GET', '/items/categories?fields=id,slug,name&limit=-1')['data']
    by_id = {row['id']: row for row in categories}
    # unit slug → the phrases that would have matched it
    phrases_for = {slug: keywords.get(unit, [])
                   for unit, (slug, _, _) in tag_news.CATEGORIES.items()}

    articles = api.request(
        'GET', '/items/articles?fields=id,title,categories.id,categories.categories_id&limit=-1',
    )['data']
    print(f'{len(articles)} articles scanned', file=sys.stderr)

    removed = affected = 0
    for article in articles:
        links = []
        for link in article.get('categories') or []:
            raw = link.get('categories_id')
            category_id = raw if isinstance(raw, str) else (raw or {}).get('id')
            category = by_id.get(category_id)
            if category and category['slug'] in unit_slugs:
                links.append((link['id'], category))

        if len(links) < args.threshold:
            continue

        title = (article.get('title') or '').lower()
        doomed = [(link_id, category) for link_id, category in links
                  if not any(phrase.lower() in title
                             for phrase in phrases_for.get(category['slug'], []))]
        if not doomed:
            continue

        kept = len(links) - len(doomed)
        affected += 1
        print(f'\n{article["title"][:70]}  ({len(links)} units, keeping {kept})', file=sys.stderr)
        for link_id, category in doomed:
            print(f'    − {category["name"]}', file=sys.stderr)
            if not args.dry_run:
                api.request('DELETE', f'/items/articles_categories/{link_id}')
            removed += 1

    verb = 'Would remove' if args.dry_run else 'Removed'
    print(f'\n{verb} {removed} category link(s) from {affected} article(s)', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
