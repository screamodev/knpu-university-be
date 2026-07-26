#!/usr/bin/env python3
"""
Stage 1 — extract legacy news from the Drupal 7 dump.

Reads from a throwaway MySQL container that holds the legacy database (see
README.md for how it is created) and writes one JSON object per line to
`news.raw.jsonl`. Nothing is transformed here: keeping the raw pull separate
means stages 2 and 3 can be re-run without touching the 300 MB dump again.

Usage:
    python3 1_extract.py                      # last 5 years, default container
    python3 1_extract.py --since 2021-07-25
    python3 1_extract.py --all                # every news node
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent

# `bundle = n.type` keeps us on the node's own body row; the dump has exactly one
# body row (language 'und', delta 0) per news node, but the join stays explicit.
QUERY = """
SELECT JSON_OBJECT(
  'nid', n.nid,
  'title', n.title,
  'created', n.created,
  'changed', n.changed,
  'status', n.status,
  'author', u.name,
  'alias', (
    SELECT a.alias FROM drupal_url_alias a
    WHERE a.source = CONCAT('node/', n.nid)
    ORDER BY a.pid DESC LIMIT 1
  ),
  'format', b.body_format,
  'summary', b.body_summary,
  'body', b.body_value
)
FROM drupal_node n
LEFT JOIN drupal_field_data_body b
       ON b.entity_id = n.nid AND b.entity_type = 'node' AND b.bundle = n.type
LEFT JOIN drupal_users u ON u.uid = n.uid
WHERE n.type = '{node_type}'{since_clause}
ORDER BY n.created ASC;
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--container', default='hnpu-legacy-mysql', help='docker container running the legacy MySQL')
    parser.add_argument('--database', default='legacy')
    parser.add_argument('--user', default='root')
    parser.add_argument('--password', default='root')
    parser.add_argument('--node-type', default='new', help="Drupal content type holding news (default: 'new')")
    parser.add_argument('--since', default=None, help='YYYY-MM-DD; defaults to five years ago')
    parser.add_argument('--all', action='store_true', help='ignore --since and take every news node')
    parser.add_argument('--out', default=str(HERE / 'news.raw.jsonl'))
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.all:
        since_clause = ''
        window = 'all news'
    else:
        since = args.since or (datetime.now(timezone.utc) - timedelta(days=5 * 365)).strftime('%Y-%m-%d')
        since_clause = f" AND n.created >= UNIX_TIMESTAMP('{since}')"
        window = f'created >= {since}'

    query = QUERY.format(node_type=args.node_type, since_clause=since_clause)

    # --raw disables the CLI's own backslash escaping; JSON_OBJECT already escapes
    # newlines and quotes, so every row arrives as exactly one line of valid JSON.
    command = [
        'docker', 'exec', '-i', args.container,
        'mysql', f'-u{args.user}', f'-p{args.password}',
        '--default-character-set=utf8mb4', '-N', '--raw',
        args.database,
    ]

    print(f'Extracting {args.node_type!r} nodes ({window}) from {args.container}…', file=sys.stderr)
    result = subprocess.run(command, input=query, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = '\n'.join(l for l in result.stderr.splitlines() if 'Using a password' not in l)
        print(f'mysql failed:\n{stderr}', file=sys.stderr)
        return 1

    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f'! skipped an unparsable row: {exc}', file=sys.stderr)

    out_path = Path(args.out)
    with out_path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')

    missing_body = sum(1 for r in rows if not r.get('body'))
    missing_alias = sum(1 for r in rows if not r.get('alias'))
    unpublished = sum(1 for r in rows if r.get('status') != 1)
    print(
        f'Wrote {len(rows)} rows to {out_path}\n'
        f'  without body:  {missing_body}\n'
        f'  without alias: {missing_alias}\n'
        f'  unpublished:   {unpublished}',
        file=sys.stderr,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
