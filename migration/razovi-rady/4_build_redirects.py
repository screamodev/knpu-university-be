#!/usr/bin/env python3
"""
Build the `legacy_redirects` payload — the table that keeps old hnpu.edu.ua URLs alive.

Links to these defenses are recorded in the state dissertation register, so once the domain
points at the new site both shapes still have to resolve:

    /uk/specializovana-vchena-rada-df-…    → /science/dissertation-councils/<той самий slug>
    /sites/default/files/…/Dyser_….pdf     → /assets/<uuid>

Page rows come from `data/index.json`; file rows come from Directus itself, so the uuids are the
ones this environment actually has. The maps left behind by the earlier migrations are folded in
too (`--backfill`), so every legacy file the site already re-hosts survives the move, not only
this pass's.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 4_build_redirects.py
    python3 ../pass2/load.py data/legacy_redirects.json

→ data/legacy_redirects.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

from shared import (
    DATA,
    Directus,
    LIST_SLUG,
    NEW_INDEX_PATH,
    NEW_PAGE_PREFIX,
    legacy_path_of,
    login,
    write_json,
)

HERE = Path(__file__).parent

# source-url → file-uuid maps produced by the earlier passes.
BACKFILL_MAPS = [
    ('pass2', HERE.parent / 'pass2' / 'files.map.json'),
    ('structure-pages', HERE.parent / 'structure-pages' / 'images.map.json'),
    ('partners', HERE.parent / 'partners' / 'logos.map.json'),
    ('razovi-rady', HERE / 'files.map.json'),
]

# The old site served both language prefixes for every node. On the new site Ukrainian is the
# unprefixed default locale, so `/uk/…` lands on a bare path and `/en/…` keeps the visitor in
# English (the page falls back to the Ukrainian text, as everywhere else on the site).
LOCALE_PREFIXES = (('/uk/', ''), ('/en/', '/en'))


def fetch_all(directus: Directus, collection: str, fields: str) -> list[dict]:
    query = urllib.parse.urlencode({'fields': fields, 'limit': '-1'})
    return directus.get(f'/items/{collection}?{query}') or []


def uploaded_file_ids(directus: Directus) -> set[str]:
    """`directus_files` is a system collection — it answers on `/files`, not `/items/…`."""
    rows = directus.get('/files?' + urllib.parse.urlencode({'fields': 'id', 'limit': '-1'})) or []
    return {row['id'] for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--index', default=str(DATA / 'index.json'))
    parser.add_argument('--no-backfill', action='store_true',
                        help='only this pass — skip the maps of the earlier migrations')
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    args = parser.parse_args()

    entries = json.loads(Path(args.index).read_text(encoding='utf-8'))
    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    rows: list[dict] = []
    seen: set[str] = set()

    def add(legacy_path: str, *, kind: str, note: str,
            target: str | None = None, file_id: str | None = None) -> None:
        if not legacy_path or legacy_path in seen:
            return
        seen.add(legacy_path)
        rows.append({
            'legacyPath': legacy_path,
            'kind': kind,
            'targetPath': target,
            'file': file_id,
            'note': note,
            'order': len(rows) + 1,
        })

    # ── pages ────────────────────────────────────────────────────────────────
    for prefix, locale in LOCALE_PREFIXES:
        add(f'{prefix}{LIST_SLUG}', kind='page', target=f'{locale}{NEW_INDEX_PATH}',
            note='razovi-rady: перелік')
    for entry in entries:
        for prefix, locale in LOCALE_PREFIXES:
            add(f'{prefix}{entry["slug"]}', kind='page',
                target=f'{locale}{NEW_PAGE_PREFIX}{entry["slug"]}',
                note='razovi-rady: разова рада')
    pages = len(rows)

    # ── files of this pass, straight from Directus ───────────────────────────
    for row in fetch_all(directus, 'dissertation_council_files', 'legacyPath,file'):
        if row.get('legacyPath') and row.get('file'):
            add(row['legacyPath'], kind='file', file_id=row['file'], note='razovi-rady')
    own_files = len(rows) - pages

    # ── everything the earlier passes already re-hosted ──────────────────────
    backfilled = 0
    if not args.no_backfill:
        known_files = uploaded_file_ids(directus)
        for name, path in BACKFILL_MAPS:
            if not path.exists():
                continue
            before = len(rows)
            skipped = 0
            for source, file_id in json.loads(path.read_text(encoding='utf-8')).items():
                legacy_path = legacy_path_of(source)
                if not legacy_path:
                    continue
                if file_id not in known_files:
                    skipped += 1
                    continue
                add(legacy_path, kind='file', file_id=file_id, note=name)
            added = len(rows) - before
            backfilled += added
            suffix = f', {skipped} not in this environment' if skipped else ''
            print(f'  {name}: +{added}{suffix}', file=sys.stderr)

    print(f'\npages={pages} files={own_files} backfilled={backfilled} total={len(rows)}',
          file=sys.stderr)

    write_json(DATA / 'legacy_redirects.json', {
        'batches': [
            {
                'collection': 'legacy_redirects',
                'identity': ['legacyPath'],
                'rows': rows,
            },
        ],
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
