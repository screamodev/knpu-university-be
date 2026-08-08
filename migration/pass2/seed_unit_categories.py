#!/usr/bin/env python3
"""
Seed a news category for every кафедра, under its faculty's category.

`categories.parent` (added by `../schema/apply_schema.py`) makes the news tree roll up: a кафедра
page shows its own news and, while it has none, its faculty's; a faculty page shows its own plus
everything its кафедри publish. For that to work the categories have to exist, so editors can pick
one — this creates them.

The list lives in `data/unit_categories.json`, generated from `STRUCTURE_CHAIRS` in
`knpu-university-fe/app/utils/structure.ts`: `slug` matches the кафедра's page slug, `parentSlug`
is its faculty's existing category.

Idempotent — an existing category keeps its id and only gains the missing `parent`/`nameEn`.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 seed_unit_categories.py --dry-run
    python3 seed_unit_categories.py

On production run the same command with a static `DIRECTUS_TOKEN`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
from pathlib import Path

from common import Directus, login

HERE = Path(__file__).parent


def categories_by_slug(directus: Directus) -> dict[str, dict]:
    query = urllib.parse.urlencode({'fields': 'id,slug,name,parent', 'limit': '-1'})
    rows = directus.get(f'/items/categories?{query}') or []
    return {row['slug']: row for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', default=str(HERE / 'data' / 'unit_categories.json'))
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    wanted = json.loads(Path(args.input).read_text(encoding='utf-8'))
    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)
    existing = categories_by_slug(directus)

    created = linked = skipped = failed = 0

    for entry in wanted:
        parent = existing.get(entry['parentSlug'])
        if not parent:
            print(f'    ! no faculty category {entry["parentSlug"]!r} — {entry["slug"]} skipped',
                  file=sys.stderr)
            failed += 1
            continue

        current = existing.get(entry['slug'])
        if current and current.get('parent') == parent['id']:
            skipped += 1
            continue

        payload = {
            'name': entry['name'],
            'nameEn': entry.get('nameEn'),
            'slug': entry['slug'],
            'parent': parent['id'],
        }
        action = 'link' if current else 'create'
        print(f'{action:<7} {entry["slug"]:<58} → {entry["parentSlug"]}')
        if args.dry_run:
            continue

        try:
            if current:
                directus.request('PATCH', f'/items/categories/{current["id"]}', payload=payload)
                linked += 1
            else:
                directus.request('POST', '/items/categories', payload=payload)
                created += 1
        except urllib.error.HTTPError as exc:
            print(f'    ! {exc.code}: {exc.read().decode("utf-8", "replace")[:200]}', file=sys.stderr)
            failed += 1

    if args.dry_run:
        print('\ndry run — nothing written.', file=sys.stderr)
    else:
        print(f'\ncreated={created} linked={linked} unchanged={skipped} failed={failed}', file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
