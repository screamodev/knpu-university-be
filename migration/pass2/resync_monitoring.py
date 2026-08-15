#!/usr/bin/env python3
"""
Bring already-loaded `monitoring_surveys` rows in line with a fresh `data/monitoring.json`.

`load.py` is create-only: a row whose identity is already there is skipped, so a re-extraction
that *corrects* a field (the напрям a survey belongs to, a heading that was cut off before its
name, a research group) never reaches Directus. This script patches those fields in place,
matching on `number`, and leaves everything else — files, results, order — untouched.

Run it before `load.py` when the extractor changed, so that the loader then only creates the
surveys that are genuinely new.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 resync_monitoring.py --dry-run
    python3 resync_monitoring.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from common import Directus, login

HERE = Path(__file__).parent

# Fields the extractor owns. `formUrl` is included because the legacy page sometimes carries the
# same form twice, once with a stray non-breaking space glued to the address.
FIELDS = ('area', 'title', 'researchGroup', 'formUrl')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('payload', nargs='?', default=str(HERE / 'data' / 'monitoring.json'))
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    envelope = json.loads(Path(args.payload).read_text(encoding='utf-8'))
    batch = next(b for b in envelope['batches'] if b['collection'] == 'monitoring_surveys')
    wanted = {row['number']: row for row in batch['rows']}

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    current = directus.get('/items/monitoring_surveys?limit=-1&fields=id,number,'
                           + ','.join(FIELDS)) or []

    patched = missing = 0
    for row in current:
        source = wanted.get(row['number'])
        if not source:
            print(f'  ? {row["number"]}: no longer on the legacy page', file=sys.stderr)
            missing += 1
            continue
        changes = {field: source.get(field) for field in FIELDS
                   if (source.get(field) or None) != (row.get(field) or None)}
        if not changes:
            continue
        summary = ', '.join(f'{field}: {row.get(field)!r} → {value!r}'[:120]
                            for field, value in changes.items())
        print(f'  ~ {row["number"]}: {summary}', file=sys.stderr)
        if not args.dry_run:
            directus.request('PATCH', f'/items/monitoring_surveys/{row["id"]}', payload=changes)
        patched += 1

    new = [number for number in wanted if number not in {row['number'] for row in current}]
    print(f'\npatched={patched} unchanged={len(current) - patched - missing} '
          f'not-on-page={missing} new={len(new)} ({", ".join(new) or "—"})', file=sys.stderr)
    print('dry run — nothing written' if args.dry_run else 'done; now run load.py to add the new ones',
          file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
