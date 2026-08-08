#!/usr/bin/env python3
"""
Rename an article category, keeping its slug.

The slug is what the site filters and links on (`/news?category=<slug>`, the news blocks of the
unit pages), so a category can be relabelled but never re-slugged. Used to turn «Студентський
парламент» into «Студентське самоврядування» without breaking the student-government page.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 rename_category.py --slug studentskyi-parlament \
        --name 'Студентське самоврядування' --name-en 'Student government' --dry-run
    python3 rename_category.py --slug studentskyi-parlament \
        --name 'Студентське самоврядування' --name-en 'Student government'
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse

from common import Directus, login


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--slug', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--name-en')
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    query = urllib.parse.urlencode({
        'fields': 'id,name,nameEn,slug',
        'filter[slug][_eq]': args.slug,
        'limit': '1',
    })
    rows = directus.get(f'/items/categories?{query}') or []
    if not rows:
        print(f'! no category with slug {args.slug!r}', file=sys.stderr)
        return 1

    row = rows[0]
    payload = {'name': args.name}
    if args.name_en and 'nameEn' in row:
        payload['nameEn'] = args.name_en

    print(f'{row["slug"]}: {row["name"]!r} → {args.name!r}')
    if args.dry_run:
        print('dry run — nothing written.')
        return 0

    directus.request('PATCH', f'/items/categories/{row["id"]}', payload=payload)
    print('done.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
