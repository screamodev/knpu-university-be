#!/usr/bin/env python3
"""
Division pages with a plain list of files → rows for the `documents` collection.

`sources.json` maps a `documents.section` to the legacy page it comes from. Options per section:

    keepLinks   keep non-file links (Google Docs/Drive, other sites) as `externalUrl`
    route       [{"match": "<regex on the title>", "section": "<other section>"}] — send some
                links of the page to a different section (e.g. графіки → education-schedule)
    manual      rows written by hand, for pages whose links are unlabelled images
    note        why the section looks the way it does; carried into the README, not into Directus

    python3 extract_documents.py
    python3 extract_documents.py --only academic-office education-schedule
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from common import DATA, HERE, fetch, is_file_url, links_of, write_json

# Internal pages of the old site are never re-hosted: they either became pages here or are
# lists that get rewritten every year.
SELF_HOSTS = ('hnpu.edu.ua', 'smc.hnpu.edu.ua')


def is_internal_page(url: str) -> bool:
    return any(host in url for host in SELF_HOSTS) and not is_file_url(url)


def extract(section: str, config: dict) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()

    for entry in config.get('manual', []):
        rows.append({
            'section': section,
            'title': entry['title'],
            'order': len(rows) + 1,
            '_file': entry['url'],
        })
        seen.add(entry['url'])

    if not config.get('manual'):
        routes = [(re.compile(rule['match']), rule['section']) for rule in config.get('route', [])]
        page = fetch(config['url'])
        for title, url in links_of(page, config['url']):
            if not title or url in seen or is_internal_page(url):
                continue
            if not is_file_url(url) and not config.get('keepLinks'):
                continue
            seen.add(url)

            target = section
            for pattern, other in routes:
                if pattern.search(title):
                    target = other
                    break

            row = {'section': target, 'title': title, 'order': 0}
            if is_file_url(url):
                row['_file'] = url
            else:
                row['externalUrl'] = url
            rows.append(row)

    # `order` is per section, and mirrors the position on the legacy page.
    counters: dict[str, int] = {}
    for row in rows:
        counters[row['section']] = counters.get(row['section'], 0) + 1
        row['order'] = counters[row['section']]

    for target, count in counters.items():
        files = sum(1 for row in rows if row['section'] == target and row.get('_file'))
        print(f'  {target}: {count} rows ({files} files)', file=sys.stderr)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', nargs='*')
    args = parser.parse_args()

    sources = json.loads((HERE / 'sources.json').read_text(encoding='utf-8'))
    rows: list[dict] = []
    for section, config in sources.items():
        if args.only and section not in args.only:
            continue
        print(f'{section} ← {config["url"]}', file=sys.stderr)
        rows.extend(extract(section, config))

    write_json(DATA / 'documents.json', {
        'batches': [{
            'collection': 'documents',
            'identity': ['section', 'title'],
            'rows': rows,
        }],
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
