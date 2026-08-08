#!/usr/bin/env python3
"""
Stage 3 — write the centre's pages into the frontend's static content.

One file per tab of `/education/quality`: every Joomla page mapped to that tab becomes a section,
in the order the site listed them. The frontend renders them through `SharedStaticPageBody`, the
same way the other migrated prose works.

Files are still linked to `smc.hnpu.edu.ua` here; `../pass2/mirror_page_files.py` re-hosts them
afterwards and rewrites the links to `/assets/<uuid>`.

    python3 3_emit_pages.py --dry-run
    python3 3_emit_pages.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_TARGET = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'pages'

TAB_TITLES = {
    'documents': 'Документи центру забезпечення якості освіти',
    'regulations': 'Нормативна база центру забезпечення якості освіти',
    'students': 'Здобувачу',
    'quality': 'Якість освіти',
    'programmes': 'Освітні програми',
    'accreditation': 'Акредитація освітніх програм',
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', default=str(HERE / 'data' / 'pages.json'))
    parser.add_argument('--target', default=str(DEFAULT_TARGET))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    pages = json.loads(Path(args.input).read_text(encoding='utf-8'))
    by_tab: dict[str, list[dict]] = defaultdict(list)
    for page in pages:
        by_tab[page['tab']].append(page)

    target = Path(args.target)
    for tab, entries in sorted(by_tab.items()):
        slug = f'quality-centre-{tab}'
        payload = {
            'title': TAB_TITLES.get(tab, tab),
            'sections': [{'heading': entry['title'], 'html': entry['html']} for entry in entries],
            'sourceUrls': [entry['sourceUrl'] for entry in entries],
            'capturedAt': date.today().isoformat(),
        }
        chars = sum(len(entry['html']) for entry in entries)
        files = len({url for entry in entries for url in entry['files']})
        print(f'{slug:<34} {len(entries):>2} section(s), {chars:>7} chars, {files:>4} file link(s)',
              file=sys.stderr)
        if args.dry_run:
            continue
        out = target / f'{slug}.uk.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    if not args.dry_run:
        print(f'→ {target}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
