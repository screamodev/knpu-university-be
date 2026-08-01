#!/usr/bin/env python3
"""
Stage 1 — pull the faculty pages out of the Drupal 7 dump.

Every faculty page and every page behind its sidebar menu is a `division` node, and the sidebar
itself is a Drupal field (`field_usefulness`) on the landing node — so the whole thing comes out
of the dump and nothing has to be scraped.

For each unit in `units.map.json` this writes:

  * `menu.draft.json` — the sidebar of each landing page (label + href + resolved nid), the raw
    material for the hand-edited `tabs.map.json`
  * `pages.raw.jsonl`  — one row per referenced node: title, body, dean, address block

Usage:
    python3 1_extract.py
    python3 1_extract.py --only arts
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent

# Sidebar menus were written years ago and still link to aliases that have since been renamed
# (`istoriya-pryrodnychogo-fakultetu` → `istoriya-fakultetu-pryrodnychoyi-…`). The dump only
# keeps the current alias, so the old one is resolved by following the site's own redirect.
BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'uk,en;q=0.8',
}

LINK_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r'<[^>]+>')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--container', default='hnpu-legacy-mysql')
    parser.add_argument('--database', default='legacy')
    parser.add_argument('--user', default='root')
    parser.add_argument('--password', default='root')
    parser.add_argument('--units', default=str(HERE / 'units.map.json'))
    parser.add_argument('--only', default=None, help='restrict to one unit slug')
    parser.add_argument('--out', default=str(HERE / 'pages.raw.jsonl'))
    parser.add_argument('--menu-out', default=str(HERE / 'menu.draft.json'))
    parser.add_argument('--redirects', default=str(HERE / 'alias.redirects.json'),
                        help='cache of renamed alias → current alias')
    parser.add_argument('--no-network', action='store_true',
                        help='skip redirect resolution and use only the cache')
    return parser.parse_args()


def mysql(args: argparse.Namespace, query: str) -> list[str]:
    """Run a query and return raw output lines. `--raw` keeps JSON_OBJECT output intact."""
    command = [
        'docker', 'exec', '-i', args.container,
        'mysql', f'-u{args.user}', f'-p{args.password}',
        '--default-character-set=utf8mb4', '-N', '--raw',
        args.database,
    ]
    result = subprocess.run(command, input=query, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = '\n'.join(l for l in result.stderr.splitlines() if 'Using a password' not in l)
        raise SystemExit(f'mysql failed:\n{stderr}')
    return [line for line in result.stdout.splitlines() if line.strip()]


def rows_as_json(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f'! skipped an unparsable row: {exc}', file=sys.stderr)
    return out


# Only the main site holds `division` nodes; lms./journals./smc. are separate applications.
SITE_HOSTS = {'hnpu.edu.ua', 'www.hnpu.edu.ua'}
# Uploaded files live under sites/default/files and are links, not pages.
FILE_PATH_RE = re.compile(r'^sites/|\.(pdf|docx?|xlsx?|pptx?|zip|jpe?g|png)$', re.I)


def _path_of(href: str) -> str | None:
    """Path of a link that points at the main site, else None."""
    value = html.unescape((href or '').strip())
    if not value or value.startswith(('mailto:', 'tel:', '#')):
        return None
    value = re.sub(r'^https?:', '', value)
    if value.startswith('//'):
        host, _, rest = value[2:].partition('/')
        if host not in SITE_HOSTS:
            return None
        value = '/' + rest
    if not value.startswith('/'):
        return None
    value = value.split('#')[0].split('?')[0]
    return re.sub(r'^/(uk|en)(/|$)', '/', value).strip('/') or None


def normalise_alias(href: str) -> str | None:
    """`//hnpu.edu.ua/uk/division/x`, `/uk/division/x`, `division/x` → `division/x`."""
    path = _path_of(href)
    if path is None or FILE_PATH_RE.search(path):
        return None
    return path


def is_external(href: str) -> bool:
    """True when the entry should stay a link instead of becoming a migrated page."""
    path = _path_of(href)
    return path is None or bool(FILE_PATH_RE.search(path))


def resolve_redirect(alias: str, timeout: int = 20) -> str | None:
    """Follow the live site's redirect for a renamed alias; returns the current alias."""
    url = f'https://hnpu.edu.ua/uk/{alias}'
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final = response.geturl()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    path = re.sub(r'^https?://[^/]+/', '', final).split('#')[0].split('?')[0]
    path = re.sub(r'^(uk|en)/', '', path).strip('/')
    return path if path and path != alias else None


def menu_items(menu_html: str) -> list[dict]:
    items = []
    for match in LINK_RE.finditer(menu_html or ''):
        href = match.group(1)
        label = html.unescape(TAG_RE.sub('', match.group(2))).strip()
        label = re.sub(r'\s+', ' ', label)
        if not label:
            continue
        items.append({
            'label': label,
            'href': html.unescape(href.strip()),
            'alias': normalise_alias(href),
            'external': is_external(href),
        })
    return items


def main() -> int:
    args = parse_args()
    units = json.loads(Path(args.units).read_text(encoding='utf-8'))['units']
    if args.only:
        units = {args.only: units[args.only]}

    wanted_aliases = {alias for unit in units.values() for alias in unit['legacy']}

    # ---- landing nodes + their sidebar menus ---------------------------------
    alias_list = ','.join(f"'{a}'" for a in sorted(wanted_aliases))
    landing_rows = rows_as_json(mysql(args, f"""
      SELECT JSON_OBJECT(
        'alias', a.alias, 'nid', n.nid, 'language', n.language, 'tnid', n.tnid,
        'title', n.title, 'menu', m.field_usefulness_value
      )
      FROM drupal_url_alias a
      JOIN drupal_node n ON CONCAT('node/', n.nid) = a.source
      LEFT JOIN drupal_field_data_field_usefulness m
             ON m.entity_id = n.nid AND m.entity_type = 'node'
      WHERE a.alias IN ({alias_list});
    """))
    by_alias = {row['alias']: row for row in landing_rows}

    menu_draft: dict[str, dict] = {}
    referenced: set[str] = set()
    for slug, unit in units.items():
        menu_draft[slug] = {'legacy': unit['legacy'], 'pages': {}}
        for alias in unit['legacy']:
            landing = by_alias.get(alias)
            if not landing:
                print(f'! {slug}: alias {alias!r} not found in the dump', file=sys.stderr)
                continue
            items = menu_items(landing.get('menu') or '')
            menu_draft[slug]['pages'][alias] = {
                'nid': landing['nid'],
                'title': landing['title'],
                'menu': items,
            }
            referenced.add(alias)
            referenced.update(item['alias'] for item in items if item['alias'])

    # ---- renamed aliases -----------------------------------------------------
    known = set()
    if referenced:
        in_list = ','.join(f"'{a}'" for a in sorted(referenced))
        known = {line.strip() for line in mysql(args, f"SELECT alias FROM drupal_url_alias WHERE alias IN ({in_list});")}

    redirects_path = Path(args.redirects)
    redirects: dict[str, str | None] = (
        json.loads(redirects_path.read_text(encoding='utf-8')) if redirects_path.exists() else {})
    unresolved = sorted(referenced - known)
    if unresolved and not args.no_network:
        print(f'Resolving {len(unresolved)} renamed aliases against the live site…', file=sys.stderr)
        for alias in unresolved:
            if alias in redirects:
                continue
            redirects[alias] = resolve_redirect(alias)
        redirects_path.write_text(json.dumps(redirects, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    for unit in menu_draft.values():
        for page in unit['pages'].values():
            for item in page['menu']:
                target = redirects.get(item['alias'] or '')
                if target:
                    item['redirectedFrom'] = item['alias']
                    item['alias'] = target
                    referenced.add(target)

    Path(args.menu_out).write_text(
        json.dumps(menu_draft, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    resolved_targets = {target for target in redirects.values() if target}
    still_missing = sorted(
        a for a in referenced
        if a not in known and a not in resolved_targets and not redirects.get(a)
    )
    if still_missing:
        print(f'! {len(still_missing)} aliases have no node and no redirect: '
              f'{", ".join(still_missing[:5])}…', file=sys.stderr)

    # ---- bodies of every referenced page -------------------------------------
    referenced_list = ','.join(f"'{a}'" for a in sorted(referenced))
    page_rows = rows_as_json(mysql(args, f"""
      SELECT JSON_OBJECT(
        'alias', a.alias,
        'nid', n.nid,
        'type', n.type,
        'language', n.language,
        'tnid', n.tnid,
        'status', n.status,
        'title', n.title,
        'body', b.body_value,
        'chief', c.field_chief_value,
        'address', ad.field_address_value
      )
      FROM drupal_url_alias a
      JOIN drupal_node n ON CONCAT('node/', n.nid) = a.source
      LEFT JOIN drupal_field_data_body b
             ON b.entity_id = n.nid AND b.entity_type = 'node' AND b.bundle = n.type
      LEFT JOIN drupal_field_data_field_chief c
             ON c.entity_id = n.nid AND c.entity_type = 'node'
      LEFT JOIN drupal_field_data_field_address ad
             ON ad.entity_id = n.nid AND ad.entity_type = 'node'
      WHERE a.alias IN ({referenced_list});
    """))

    # English twins of the landing pages (sub-pages are almost never translated).
    tnids = {row['tnid'] for row in page_rows if row.get('tnid')}
    if tnids:
        page_rows += rows_as_json(mysql(args, f"""
          SELECT JSON_OBJECT(
            'alias', (SELECT a.alias FROM drupal_url_alias a
                      WHERE a.source = CONCAT('node/', n.nid) ORDER BY a.pid DESC LIMIT 1),
            'nid', n.nid, 'type', n.type, 'language', n.language, 'tnid', n.tnid,
            'status', n.status, 'title', n.title,
            'body', b.body_value, 'chief', c.field_chief_value, 'address', ad.field_address_value
          )
          FROM drupal_node n
          LEFT JOIN drupal_field_data_body b
                 ON b.entity_id = n.nid AND b.entity_type = 'node' AND b.bundle = n.type
          LEFT JOIN drupal_field_data_field_chief c
                 ON c.entity_id = n.nid AND c.entity_type = 'node'
          LEFT JOIN drupal_field_data_field_address ad
                 ON ad.entity_id = n.nid AND ad.entity_type = 'node'
          WHERE n.tnid IN ({','.join(str(t) for t in sorted(tnids))})
            AND n.language = 'en';
        """))

    seen: set[int] = set()
    with Path(args.out).open('w', encoding='utf-8') as handle:
        for row in page_rows:
            if row['nid'] in seen:
                continue
            seen.add(row['nid'])
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')

    print(
        f'Units: {len(units)}  landing pages: {len(referenced_list.split(","))} referenced aliases\n'
        f'Wrote {len(seen)} nodes → {args.out}\n'
        f'Wrote sidebar menus → {args.menu_out}',
        file=sys.stderr,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
