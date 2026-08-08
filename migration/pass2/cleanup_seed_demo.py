#!/usr/bin/env python3
"""
Remove the demo content `snapshots/seed-content.sh` left behind, and links back to the old site.

Three things this deletes, each behind its own flag (nothing runs without `--yes`):

  --seed-orders    `university_orders` rows whose file is a seeded stub (`university-order-001-2024.pdf`,
                   116 bytes). These are why «Накази» showed «Failed to load PDF document».
  --seed-files     files that are seed placeholders: under 2 KB and named like the seeder's
                   fixtures (`gallery-campus-*`, `news-cover-*`, `event-cover-*`, `memorial-entry-*`,
                   `financial-report-*`, `university-order-*`).
  --legacy-links   `documents` rows whose `externalUrl` is a *page* on hnpu.edu.ua — those pages are
                   being replaced by this site, so the row is a dead end. Rows linking to a file are
                   left alone.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 cleanup_seed_demo.py --seed-orders --seed-files --legacy-links      # lists, deletes nothing
    python3 cleanup_seed_demo.py --seed-orders --seed-files --legacy-links --yes

Against production use a static `DIRECTUS_TOKEN`, and read the printed list before adding `--yes`:
deletion there is irreversible.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.parse

from common import Directus, login

SEED_FILE_RE = re.compile(
    r'^(university-order-\d+-\d{4}|gallery-campus-[a-z]|news-cover-[a-z]|event-cover-[a-z]'
    r'|memorial-entry-[a-z]|financial-report-\d{4}|partner-logo-[a-z]|programme-cover-[a-z])\.',
    re.I)
SEED_MAX_BYTES = 2048

FILE_URL_RE = re.compile(r'\.(pdf|docx?|xlsx?|pptx?|rtf|odt|zip|jpe?g|png)(\?|$)', re.I)


def seed_orders(directus: Directus) -> list[tuple[str, str]]:
    query = urllib.parse.urlencode({
        'fields': 'id,title,documentFile.filename_download,documentFile.filesize',
        'limit': '-1',
    })
    rows = directus.get(f'/items/university_orders?{query}') or []
    found = []
    for row in rows:
        file = row.get('documentFile') or {}
        name = file.get('filename_download') or ''
        if SEED_FILE_RE.match(name) or (file and int(file.get('filesize') or 0) < SEED_MAX_BYTES):
            found.append((row['id'], f'{row["title"]} ({name})'))
    return found


def seed_files(directus: Directus) -> list[tuple[str, str]]:
    query = urllib.parse.urlencode({
        'fields': 'id,filename_download,filesize',
        'filter[filesize][_lt]': str(SEED_MAX_BYTES),
        'limit': '-1',
    })
    rows = directus.get(f'/files?{query}') or []
    return [(row['id'], f'{row["filename_download"]} ({row["filesize"]} B)')
            for row in rows if SEED_FILE_RE.match(row.get('filename_download') or '')]


def legacy_links(directus: Directus) -> list[tuple[str, str]]:
    query = urllib.parse.urlencode({
        'fields': 'id,section,title,externalUrl',
        'filter[externalUrl][_contains]': 'hnpu.edu.ua',
        'limit': '-1',
    })
    rows = directus.get(f'/items/documents?{query}') or []
    return [(row['id'], f'{row["section"]}: {row["title"][:60]} → {row["externalUrl"]}')
            for row in rows if not FILE_URL_RE.search(row['externalUrl'].split('#')[0])]


def delete(directus: Directus, path: str, ids: list[str]) -> None:
    for start in range(0, len(ids), 50):
        directus.request('DELETE', path, payload=ids[start:start + 50])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--seed-orders', action='store_true')
    parser.add_argument('--seed-files', action='store_true')
    parser.add_argument('--legacy-links', action='store_true')
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--yes', action='store_true', help='actually delete')
    args = parser.parse_args()

    if not (args.seed_orders or args.seed_files or args.legacy_links):
        parser.error('pick at least one of --seed-orders / --seed-files / --legacy-links')

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    jobs = []
    if args.seed_orders:
        jobs.append(('/items/university_orders', 'seeded orders', seed_orders(directus)))
    if args.seed_files:
        jobs.append(('/files', 'seed placeholder files', seed_files(directus)))
    if args.legacy_links:
        jobs.append(('/items/documents', 'documents linking to old-site pages', legacy_links(directus)))

    for path, label, rows in jobs:
        print(f'\n== {label}: {len(rows)}')
        for _, description in rows:
            print(f'   {description}')
        if not rows or not args.yes:
            continue
        delete(directus, path, [row_id for row_id, _ in rows])
        print(f'   deleted {len(rows)}')

    if not args.yes:
        print('\ndry run — nothing deleted; re-run with --yes', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
