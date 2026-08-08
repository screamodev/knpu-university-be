#!/usr/bin/env python3
"""
Point the migrated bodies at the re-hosted files.

`2_extract_pages.py` keeps the original `hnpu.edu.ua` hrefs in `contentHtml`, because at that
point nothing is uploaded yet. After `../pass2/load.py` has created the councils and their files,
this script swaps every legacy href for `/assets/<uuid>` — the frontend resolves that against the
Directus public URL when it renders the body.

The uuid map is read from Directus itself (`dissertation_council_files.legacyPath` → `file`), not
from `files.map.json`, so the script works the same locally and on production.

Idempotent: `/assets/…` hrefs are already rewritten and are left alone.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 3_rewrite_bodies.py --dry-run
    python3 3_rewrite_bodies.py --unlink-missing
"""

from __future__ import annotations

import argparse
import html as html_lib
import os
import re
import sys
import urllib.error
import urllib.parse

from shared import Directus, legacy_path_of, login

HREF_RE = re.compile(r'href="([^"]*)"')
ANCHOR_RE = r'<a\s[^>]*href="{href}"[^>]*>(.*?)</a>'


def fetch_all(directus: Directus, collection: str, fields: str) -> list[dict]:
    query = urllib.parse.urlencode({'fields': fields, 'limit': '-1'})
    return directus.get(f'/items/{collection}?{query}') or []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('slugs', nargs='*', help='legacySlugs to process (default: all)')
    parser.add_argument('--unlink-missing', action='store_true',
                        help='unwrap links to files that never uploaded — a dead link to a dead '
                             'host helps nobody')
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    by_path = {
        row['legacyPath']: row['file']
        for row in fetch_all(directus, 'dissertation_council_files', 'legacyPath,file')
        if row.get('legacyPath') and row.get('file')
    }
    print(f'{len(by_path)} re-hosted files', file=sys.stderr)

    councils = fetch_all(directus, 'dissertation_councils', 'id,legacySlug,contentHtml')
    if args.slugs:
        wanted = set(args.slugs)
        councils = [row for row in councils if row['legacySlug'] in wanted]

    rewritten = unlinked = touched = 0

    for council in councils:
        html = council.get('contentHtml') or ''
        if not html:
            continue

        replacements: dict[str, str] = {}
        missing: set[str] = set()
        for href in set(HREF_RE.findall(html)):
            legacy_path = legacy_path_of(html_lib.unescape(href))
            if not legacy_path:
                continue
            file_id = by_path.get(legacy_path)
            if file_id:
                replacements[href] = f'/assets/{file_id}'
            else:
                missing.add(href)

        if not replacements and not (missing and args.unlink_missing):
            continue

        for href, target in replacements.items():
            html = html.replace(f'href="{href}"', f'href="{target}"')
        rewritten += len(replacements)

        if args.unlink_missing:
            for href in missing:
                html = re.sub(ANCHOR_RE.format(href=re.escape(href)), r'\1', html, flags=re.S)
            unlinked += len(missing)

        touched += 1
        if args.dry_run:
            continue
        try:
            directus.request('PATCH', f'/items/dissertation_councils/{council["id"]}',
                             payload={'contentHtml': html})
        except urllib.error.HTTPError as exc:
            print(f'  ! patch {council["legacySlug"]}: {exc.code} '
                  f'{exc.read().decode("utf-8", "replace")[:200]}', file=sys.stderr)

    note = ' (dry run — nothing written)' if args.dry_run else ''
    print(f'councils touched={touched} links rewritten={rewritten} unlinked={unlinked}{note}',
          file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
