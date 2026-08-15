#!/usr/bin/env python3
"""
Stage 3 — write the centre's pages into the frontend's static content.

One file per tab of `/education/quality`: every Joomla page mapped to that tab becomes a section,
in the order the site listed them. The frontend renders them through `SharedStaticPageBody`, the
same way the other migrated prose works.

Files are still linked to `smc.hnpu.edu.ua` here; `../pass2/mirror_page_files.py` re-hosts them
afterwards and rewrites the links to `/assets/<uuid>`. Banner images survive this stage on
purpose — `../pass2/tidy_legacy_html.py` cleans them up last, and must be re-run after every
re-emit.

Joomla's `{spoiler title=… opened=0}` blocks become collapsible sections here, so the drop-downs
of the old site stay drop-downs and every document keeps the name it had there. (`tidy` used to
flatten them into file lists, which is what the client asked us to undo.)

    python3 3_emit_pages.py --dry-run
    python3 3_emit_pages.py
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_TARGET = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'pages'

SPOILER_OPEN_RE = re.compile(r'\{spoiler\s*(?P<attrs>[^}]*)\}', re.I)
SPOILER_CLOSE_RE = re.compile(r'\{\s*/\s*spoiler\s*\}', re.I)
TITLE_RE = re.compile(r'title\s*=\s*(?P<title>.*?)(?:\s+opened\s*=|$)', re.I | re.S)
TAG_RE = re.compile(r'<[^>]+>')


def spoiler_title(attrs: str) -> str:
    match = TITLE_RE.search(attrs or '')
    raw = match.group('title') if match else ''
    return html_mod.unescape(TAG_RE.sub('', raw)).strip() or 'Документи'


def trim(markup: str) -> str:
    """Drop the paragraph shrapnel Joomla left around a marker."""
    markup = re.sub(r'^(?:\s|&nbsp;|</p>|<br\s*/?>)+', '', markup)
    markup = re.sub(r'(?:\s|&nbsp;|<p>|<br\s*/?>)+$', '', markup)
    return markup.strip()


def split_spoilers(markup: str) -> list[dict]:
    """
    Joomla body → sections: plain prose between the markers, one collapsible section per
    `{spoiler}`. Nested spoilers become that section's `children`, which is what
    `SharedStaticPageBody` renders as a drop-down inside a drop-down.
    """
    sections: list[dict] = []
    stack: list[dict] = []
    position = 0

    def emit(html: str) -> None:
        html = trim(html)
        if not html:
            return
        if stack:
            stack[-1]['html'] = trim(f'{stack[-1].get("html", "")} {html}')
        else:
            sections.append({'html': html})

    while position < len(markup):
        opening = SPOILER_OPEN_RE.search(markup, position)
        closing = SPOILER_CLOSE_RE.search(markup, position)
        if not opening and not closing:
            emit(markup[position:])
            break

        first = min((m for m in (opening, closing) if m), key=lambda m: m.start())
        emit(markup[position:first.start()])
        position = first.end()

        if first is opening:
            section = {'heading': spoiler_title(first.group('attrs')), 'collapsible': True, 'html': ''}
            if stack:
                stack[-1].setdefault('children', []).append(section)
            else:
                sections.append(section)
            stack.append(section)
        elif stack:
            stack.pop()

    for section in sections:
        section['html'] = trim(section.get('html', ''))
        for child in section.get('children', []):
            child['html'] = trim(child.get('html', ''))
    return [s for s in sections if s.get('html') or s.get('children')]


def sections_of(entry: dict) -> list[dict]:
    """The page's own heading, then its body split on the drop-down markers."""
    parts = split_spoilers(entry['html'])
    if not parts:
        return [{'heading': entry['title'], 'html': entry['html']}]
    if parts[0].get('collapsible'):
        return [{'heading': entry['title'], 'html': ''}, *parts]
    parts[0] = {'heading': entry['title'], **parts[0]}
    return parts


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
            'sections': [section for entry in entries for section in sections_of(entry)],
            'sourceUrls': [entry['sourceUrl'] for entry in entries],
            'capturedAt': date.today().isoformat(),
        }
        chars = sum(len(entry['html']) for entry in entries)
        files = len({url for entry in entries for url in entry['files']})
        drops = sum(1 for section in payload['sections'] if section.get('collapsible'))
        print(f'{slug:<34} {len(payload["sections"]):>3} section(s) ({drops:>3} drop-down), '
              f'{chars:>7} chars, {files:>4} file link(s)', file=sys.stderr)
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
