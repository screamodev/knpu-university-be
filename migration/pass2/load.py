#!/usr/bin/env python3
"""
Generic loader for the pass-2 payloads.

Every `extract_*.py` emits the same envelope, so one loader covers all of them:

    {
      "batches": [
        {
          "collection": "accreditation_dossiers",
          "identity": ["academicYear", "programmeTitle"],   # what makes a row unique
          "folder": "<directus folder uuid>",               # optional, for uploads
          "rows": [
            {"_ref": "d1", "academicYear": "2019-2020", "programmeTitle": "…"}
          ]
        },
        {
          "collection": "accreditation_dossier_files",
          "identity": ["dossier", "kind"],
          "parent": {"field": "dossier", "from": "_parent"},
          "rows": [
            {"_parent": "d1", "kind": "expert-report", "_file": "https://…/zvit.pdf"}
          ]
        }
      ]
    }

Row keys starting with `_` are directives, everything else is written as-is:

  `_file`      — URL to download and re-host; becomes the row's `file` field
  `_fileField` — write the uploaded id to this field instead of `file`
  `_ref`       — name this row so child batches can point at it
  `_parent`    — the `_ref` of the parent row

Idempotent and resumable: rows already present (matched on `identity`) are skipped, and
uploads are cached in `files.map.json` keyed by source URL, so an interrupted run picks up
where it stopped. Keep a separate map file per environment (local vs prod).

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 load.py data/contingent.json --dry-run
    python3 load.py data/contingent.json --limit 20
    python3 load.py data/contingent.json

Against production use a **static** token (`DIRECTUS_TOKEN`) — a login token expires after
15 minutes and these runs take much longer.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
from pathlib import Path

from common import Directus, download, filename_for, login, present_file_ids, upload

HERE = Path(__file__).parent


def load_map(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def save_map(path: Path, data: dict[str, str]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def identity_of(row: dict, keys: list[str]) -> tuple:
    return tuple(str(row.get(key) or '') for key in keys)


def existing_rows(directus: Directus, collection: str, keys: list[str]) -> dict[tuple, str]:
    fields = ','.join(['id'] + keys)
    query = urllib.parse.urlencode({'fields': fields, 'limit': '-1'})
    rows = directus.get(f'/items/{collection}?{query}') or []
    return {identity_of(row, keys): row['id'] for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('payload', help='JSON emitted by an extract_*.py script')
    parser.add_argument('--map', default=str(HERE / 'files.map.json'))
    # «Документи», created by snapshots/bootstrap-editor-experience.sh.
    parser.add_argument('--folder', default='3e5f21c7-8b04-4d92-a6f1-27c48ab5d301')
    parser.add_argument('--limit', type=int, help='stop after creating this many rows')
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    envelope = json.loads(Path(args.payload).read_text(encoding='utf-8'))
    batches = envelope['batches']

    if args.dry_run:
        for batch in batches:
            files = sum(1 for row in batch['rows'] if row.get('_file'))
            print(f'{batch["collection"]:<32} {len(batch["rows"]):>4} rows, {files:>4} downloads')
        return 0

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    map_path = Path(args.map)
    uploaded = load_map(map_path)
    present = present_file_ids(directus, uploaded.values())
    refs: dict[str, str] = {}
    created = skipped = failed = 0

    for batch in batches:
        collection = batch['collection']
        keys = batch['identity']
        folder = batch.get('folder', args.folder)
        parent = batch.get('parent')
        done = existing_rows(directus, collection, keys)
        print(f'\n== {collection}: {len(batch["rows"])} rows ({len(done)} already there)', file=sys.stderr)

        for index, row in enumerate(batch['rows'], 1):
            payload = {key: value for key, value in row.items() if not key.startswith('_')}
            payload.setdefault('status', 'published')

            if parent:
                parent_id = refs.get(row.get(parent['from']))
                if not parent_id:
                    print(f'    ! no parent for {row.get(parent["from"])}', file=sys.stderr)
                    failed += 1
                    continue
                payload[parent['field']] = parent_id

            key = identity_of(payload, keys)
            if key in done:
                skipped += 1
                if row.get('_ref'):
                    refs[row['_ref']] = done[key]
                continue

            source = row.get('_file')
            if source:
                file_id = uploaded.get(source)
                # The map is committed, so on a fresh environment it names ids that do not exist
                # there yet — re-upload those, asking for the very same uuid.
                if file_id and file_id not in present:
                    known_id, file_id = file_id, None
                else:
                    known_id = None
                if not file_id:
                    downloaded = download(source)
                    if not downloaded:
                        failed += 1
                        continue
                    content, content_type = downloaded
                    try:
                        file_id = upload(directus, content, filename_for(source), content_type,
                                         (payload.get('title') or filename_for(source))[:255], folder,
                                         file_id=known_id)
                    except urllib.error.HTTPError as exc:
                        print(f'    ! upload {exc.code}: {exc.read().decode("utf-8", "replace")[:200]}',
                              file=sys.stderr)
                        failed += 1
                        continue
                    uploaded[source] = file_id
                    present.add(file_id)
                    save_map(map_path, uploaded)
                payload[row.get('_fileField', 'file')] = file_id

            try:
                data = directus.request('POST', f'/items/{collection}', payload=payload)
            except urllib.error.HTTPError as exc:
                print(f'    ! create {exc.code}: {exc.read().decode("utf-8", "replace")[:300]}', file=sys.stderr)
                failed += 1
                continue

            done[key] = data['id']
            if row.get('_ref'):
                refs[row['_ref']] = data['id']
            created += 1
            if created % 10 == 0 or source:
                print(f'  [{index}/{len(batch["rows"])}] {str(payload.get("title") or key)[:70]}', file=sys.stderr)
            if args.limit and created >= args.limit:
                print(f'\n--limit {args.limit} reached', file=sys.stderr)
                print(f'created={created} skipped={skipped} failed={failed}', file=sys.stderr)
                return 0
            time.sleep(0.03)

    print(f'\ncreated={created} skipped={skipped} failed={failed}', file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
