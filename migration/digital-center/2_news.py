#!/usr/bin/env python3
"""
Stage 2 — move the centre's news archive into Directus `articles`.

The old site had no news nodes for the centre: `division/novyny-centru-cyfrovizaciyi-osvity`
is a single page whose «Архів новин» drop-down holds 35 dated entries separated by `<hr />`.
This splits that page back into articles, so the new page can show the same three-card news
block every кафедра has (`SharedStructureUnitNews`).

Every article is tagged with the category `centr-cyfrovizaciyi-osvity`, which the page queries
for both the news block and the «Оголошення» sidebar. The category is created on first run.

Bodies are stored as HTML (what the Directus WYSIWYG writes today), cleaned through
`../structure-pages/2_transform.py` so they use the subset the frontend's sanitizer keeps.
Inline images stay on the old host — as with `../legacy-news`, they cannot be downloaded from
here (Cloudflare blocks scripted requests), and only covers were ever imported. These entries
therefore have no cover; the news cards fall back to their placeholder.

Idempotent: articles are matched by slug, so a re-run updates in place.

Usage:
    docker ps | grep hnpu-legacy-mysql          # the dump container from ../legacy-news

    python3 2_news.py --dry-run
    python3 2_news.py --limit 3
    python3 2_news.py
"""

from __future__ import annotations

import argparse
import html as html_lib
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
NEWS_NODE_ID = 33348
LEGACY_NEWS_URL = 'https://hnpu.edu.ua/uk/division/novyny-centru-cyfrovizaciyi-osvity'
CATEGORY = ('centr-cyfrovizaciyi-osvity', 'Центр цифровізації освіти',
            'Centre for Digitalisation of Education')
ARCHIVE_MARKER = 'Архів новин'

# Prod Directus sits behind Cloudflare, which answers a bare urllib User-Agent with a challenge.
BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'application/json',
}

MONTHS = {
    'січня': 1, 'лютого': 2, 'березня': 3, 'квітня': 4, 'травня': 5, 'червня': 6,
    'липня': 7, 'серпня': 8, 'вересня': 9, 'жовтня': 10, 'листопада': 11, 'грудня': 12,
}
DATE_RE = re.compile(r'(\d{1,2})\s+(' + '|'.join(MONTHS) + r')\s+(\d{4})')
NUMERIC_DATE_RE = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{4})')

# Ukrainian → Latin, the same scheme the legacy aliases used, so slugs look like the rest.
TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e', 'є': 'ie', 'ж': 'zh',
    'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ь': '', 'ю': 'iu', 'я': 'ia', 'ъ': '', 'ы': 'y', 'э': 'e',
    'ё': 'e', '’': '', "'": '', '`': '',
}


class DirectusError(RuntimeError):
    pass


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
        request = urllib.request.Request(f'{self.base}{path}', data=data, headers=headers,
                                         method=method)
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
        headers={**BROWSER_HEADERS, 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())['data']['access_token']


def load_transform():
    """Import 2_transform.py by path — its name is not a valid module identifier."""
    spec = importlib.util.spec_from_file_location(
        'legacy_transform', HERE.parent / 'structure-pages' / '2_transform.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch_body(container: str, database: str, user: str, password: str) -> str:
    query = (f'SELECT body_value FROM drupal_field_data_body '
             f"WHERE entity_id = {NEWS_NODE_ID} AND entity_type = 'node';")
    command = ['docker', 'exec', '-i', container, 'mysql', f'-u{user}', f'-p{password}',
               '--default-character-set=utf8mb4', '--raw', '-N', '-B', database]
    result = subprocess.run(command, input=query, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'mysql failed:\n{result.stderr.strip()}')
    body = result.stdout.strip()
    if not body:
        raise SystemExit(f'node {NEWS_NODE_ID} has no body — is the dump loaded?')
    return body


def archive_entries(body: str) -> list[str]:
    """Everything after the «Архів новин» marker, split on the `<hr />` between entries."""
    start = body.find(ARCHIVE_MARKER)
    if start == -1:
        raise SystemExit(f'{ARCHIVE_MARKER!r} not found in the page body')
    archive = body[body.index(']', start) + 1:]
    # The trailing [/collapse] closes the drop-down, not an entry.
    archive = archive.replace('[/collapse]', '')
    return [chunk.strip() for chunk in re.split(r'<hr\s*/?>', archive) if chunk.strip()]


def text_of(markup: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', markup)
    return re.sub(r'\s+', ' ', html_lib.unescape(text).replace('\xa0', ' ')).strip()


def parse_date(text: str, fallback: date) -> date:
    match = DATE_RE.search(text)
    if match:
        day, month, year = int(match.group(1)), MONTHS[match.group(2)], int(match.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            pass
    match = NUMERIC_DATE_RE.search(text)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            pass
    year = re.search(r'\b(20\d{2})\b', text)
    if year:
        return date(int(year.group(1)), 12, 31)
    return fallback


TITLE_MAX = 120


# «14 грудня 2022 р.», «З 05 по 11 грудня 2022 року», «11.01.2021 року» — the archive opens
# entries with a date, which has to come off before what follows can serve as a headline.
LEADING_DATE_RE = re.compile(
    r'^\s*(?:з|від|у|в)?\s*(?:\d{1,2}\s*(?:\.\d{1,2}\.\d{4}|(?:по\s+\d{1,2}\s+)?(?:'
    + '|'.join(MONTHS) + r')\s+\d{4}))\s*(?:року|роки|р\.?)?[\s.,:;—–-]*', re.I)


def strip_leading_date(text: str) -> str:
    """Peel off the leading date (the archive sometimes repeats it twice)."""
    previous = None
    while previous != text:
        previous = text
        text = LEADING_DATE_RE.sub('', text).lstrip(' .,:;—–-')
    return text


def build_title(entry: str, when: date) -> str:
    """
    Title for an entry that never had one.

    The archive is written as «<strong>date</strong>» or «<strong>headline</strong>» followed by
    prose. A bold line that is more than a date makes the best title; otherwise the first
    sentence with the date peeled off. A fragment that starts mid-sentence (lower case) is a
    pull-quote, not a headline, so it only counts once nothing better is left.
    """
    # Only bold text near the top can be the headline: further down the archive uses bold for
    # names and emphasis inside the prose («вітаємо … <strong>Прокопенка Андрія Івановича</strong>»).
    head = strip_leading_date(text_of(entry))[:60]
    fallbacks: list[str] = []
    for bold in re.findall(r'<strong>(.*?)</strong>', entry, re.S):
        candidate = strip_leading_date(text_of(bold).strip(' .:'))
        if len(candidate) < 12 or candidate[:20] not in head:
            continue
        if candidate[:1].isupper():
            return trim(candidate)
        fallbacks.append(candidate)

    sentence = strip_leading_date(text_of(entry))
    sentence = re.split(r'(?<=[.!?])\s', sentence, maxsplit=1)[0].strip(' .,:—–-')
    if len(sentence) >= 12:
        return trim(sentence[:1].upper() + sentence[1:])
    if fallbacks:
        return trim(fallbacks[0][:1].upper() + fallbacks[0][1:])
    return f'Новини центру цифровізації освіти від {when.strftime("%d.%m.%Y")}'


def trim(text: str, limit: int = TITLE_MAX) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0]
    return f'{cut}…'


def slugify(title: str, when: date, taken: set[str]) -> str:
    lowered = title.lower()
    latin = ''.join(TRANSLIT.get(char, char) for char in lowered)
    latin = re.sub(r'[^a-z0-9]+', '-', latin).strip('-')
    base = f'{latin[:60].strip("-") or "novyna"}-{when.strftime("%Y-%m-%d")}'
    slug = base
    suffix = 2
    while slug in taken:
        slug = f'{base}-{suffix}'
        suffix += 1
    taken.add(slug)
    return slug


def build_excerpt(entry_text: str, limit: int = 220) -> str:
    if len(entry_text) <= limit:
        return entry_text
    return entry_text[:limit].rsplit(' ', 1)[0] + '…'


def parse_args() -> argparse.Namespace:
    def env(name: str, fallback: str | None = None) -> str | None:
        return (os.environ.get(name) or '').strip() or fallback

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--container', default='hnpu-legacy-mysql')
    parser.add_argument('--database', default='legacy')
    parser.add_argument('--user', default='root')
    parser.add_argument('--password', default='root')
    parser.add_argument('--url', default=env('DIRECTUS_URL', 'http://localhost:8055'))
    parser.add_argument('--token', default=env('DIRECTUS_TOKEN'))
    parser.add_argument('--email', default=env('DIRECTUS_EMAIL', 'admin@example.com'))
    parser.add_argument('--directus-password', default=env('DIRECTUS_PASSWORD', 'admin'))
    parser.add_argument('--limit', type=int, default=0, help='load at most N articles')
    parser.add_argument('--emit', metavar='PATH', nargs='?', const=str(HERE / 'articles.json'),
                        help='write the payloads to a file instead of the legacy database being '
                             'needed later; the production run reads them back with --from-json')
    parser.add_argument('--from-json', metavar='PATH',
                        help='load payloads produced by --emit; skips the legacy MySQL container, '
                             'which only exists on the developer machine')
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def build_payloads(args) -> list[dict]:
    transform = load_transform()

    entries = archive_entries(fetch_body(args.container, args.database, args.user, args.password))
    print(f'{len(entries)} archive entries', file=sys.stderr)

    payloads: list[dict] = []
    taken: set[str] = set()
    previous = date.today()
    for entry in entries:
        plain = text_of(entry)
        if len(plain) < 40:
            print(f'  · skipped a {len(plain)}-character fragment: {plain!r}', file=sys.stderr)
            continue
        when = parse_date(plain[:200], previous)
        previous = when
        title = build_title(entry, when)
        content, _images = transform.clean_body(entry)
        payloads.append({
            'slug': slugify(title, when, taken),
            'title': title,
            'excerpt': build_excerpt(plain),
            'content': content,
            'date_published': when.isoformat(),
            'status': 'published',
        })

    payloads.sort(key=lambda row: row['date_published'])
    return payloads


def main() -> int:
    args = parse_args()

    if args.from_json:
        payloads = json.loads(Path(args.from_json).read_text(encoding='utf-8'))
        print(f'{len(payloads)} payloads from {args.from_json}', file=sys.stderr)
    else:
        payloads = build_payloads(args)

    if args.limit:
        payloads = payloads[-args.limit:]

    if args.emit:
        Path(args.emit).write_text(json.dumps(payloads, ensure_ascii=False, indent=2) + '\n',
                                   encoding='utf-8')
        print(f'wrote {args.emit}', file=sys.stderr)

    for row in payloads:
        print(f'  {row["date_published"]}  {row["slug"][:52]:52}  {row["title"][:60]}')

    if args.dry_run:
        print(f'\n(dry run — {len(payloads)} articles, nothing written)')
        return 0

    token = args.token or login(args.url, args.email, args.directus_password)
    api = Directus(args.url, token)

    category_slug, category_name, category_name_en = CATEGORY
    found = api.request('GET', f'/items/categories?filter[slug][_eq]={category_slug}&fields=id')['data']
    if found:
        category_id = found[0]['id']
    else:
        category_id = api.request('POST', '/items/categories', payload={
            'slug': category_slug, 'name': category_name, 'nameEn': category_name_en,
        })['data']['id']
        print(f'+ category {category_slug}', file=sys.stderr)

    created = updated = linked = 0
    for row in payloads:
        existing = api.request(
            'GET',
            f'/items/articles?filter[slug][_eq]={row["slug"]}&fields=id,categories.categories_id',
        )['data']
        if existing:
            article_id = existing[0]['id']
            api.request('PATCH', f'/items/articles/{article_id}', payload=row)
            current = {link['categories_id'] for link in (existing[0].get('categories') or [])
                       if link.get('categories_id')}
            updated += 1
        else:
            article_id = api.request('POST', '/items/articles', payload=row)['data']['id']
            current = set()
            created += 1
        if category_id not in current:
            api.request('POST', '/items/articles_categories',
                        payload={'articles_id': article_id, 'categories_id': category_id})
            linked += 1

    print(f'\n{created} created, {updated} updated, {linked} category links added '
          f'({LEGACY_NEWS_URL})', file=sys.stderr)
    print(f'run at {datetime.now(timezone.utc).isoformat(timespec="seconds")}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
