#!/usr/bin/env python3
"""
Stage 8 — repair a unit whose migrated content picked up another unit's pages.

`units.map.json` listed the legacy alias `fac-prirodn` under both `special-education` and
`mathematics-informatics`, so the фізико-математичний факультет page ended up carrying the
природничий факультет's sections — including its «Деканат», which showed the wrong four people
under the фізмат dean's contact card.

Two independent repairs, both idempotent and both working on the emitted FE content only (no
legacy database, no Directus):

  --drop-shared <other-unit>   remove every section whose html also appears in the same tab of
                               the other unit, and drop that unit's legacy URL from `sourceUrls`.
                               A section that carried the other unit's `people` goes with it.

  --move-people <from>:<to>    lift the «Деканат» block out of one tab and attach it as `people`
                               to the first section of another tab (the faculty pages show the
                               deanery on `home`, while the legacy markup had it inside the
                               «Структура факультету» page). Uses the parsers of stage 6.

    python3 8_fix_unit_content.py --unit mathematics-informatics \
        --drop-shared special-education --move-people structure:home --dry-run
    python3 8_fix_unit_content.py --unit mathematics-informatics \
        --drop-shared special-education --move-people structure:home
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_CONTENT = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'structure'


def load_stage6():
    """Import 6_extract_people.py by path — its name is not a valid module identifier."""
    spec = importlib.util.spec_from_file_location('stage6', HERE / '6_extract_people.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fingerprint(html: str) -> str:
    """Compare sections by their text, ignoring whitespace the two emits may differ in."""
    return re.sub(r'\s+', ' ', html or '').strip()


def drop_shared(content: Path, unit: str, other: str, dry_run: bool) -> int:
    other_dir = content / other
    if not other_dir.is_dir():
        print(f'! no such unit: {other}', file=sys.stderr)
        return 0

    dropped = 0
    for path in sorted((content / unit).glob('*.json')):
        twin = other_dir / path.name
        if not twin.exists():
            continue

        theirs = {fingerprint(section.get('html', '')) for section in read(twin).get('sections', [])}
        payload = read(path)
        keep = [s for s in payload.get('sections', []) if fingerprint(s.get('html', '')) not in theirs]
        removed = len(payload.get('sections', [])) - len(keep)
        if not removed:
            continue

        # The other unit's legacy page is no longer a source of this one.
        sources = [url for url in payload.get('sourceUrls', []) if 'fac-prirodn' not in url]
        print(f'  {path.name}: -{removed} section(s), {len(keep)} left')
        dropped += removed
        if dry_run:
            continue
        payload['sections'] = keep
        if sources:
            payload['sourceUrls'] = sources
        write(path, payload)

    return dropped


def move_people(content: Path, unit: str, source_tab: str, target_tab: str, dry_run: bool) -> bool:
    stage6 = load_stage6()
    source_path = content / unit / f'{source_tab}.uk.json'
    target_path = content / unit / f'{target_tab}.uk.json'
    if not source_path.exists() or not target_path.exists():
        print(f'! missing {source_path.name} or {target_path.name}', file=sys.stderr)
        return False

    target = read(target_path)
    if any(section.get('people') for section in target.get('sections', [])):
        print(f'  {target_path.name}: already has people — skipped')
        return False

    source = read(source_path)
    for section in source.get('sections', []):
        people, remaining_html, heading = stage6.extract(section.get('html', ''))
        if not people:
            continue
        names = ', '.join(person['name'] for person in people)
        print(f'  {source_tab} → {target_tab}: {len(people)} people ({names})')
        if dry_run:
            return True

        section['html'] = remaining_html
        first = target['sections'][0]
        first['people'] = people
        first['peopleHeading'] = heading or 'Деканат'
        write(source_path, source)
        write(target_path, target)
        return True

    print(f'  {source_path.name}: no «Деканат» block found')
    return False


def drop_source_urls(content: Path, unit: str, pattern: str, dry_run: bool) -> int:
    """Forget legacy URLs that no longer feed this unit (their sections were dropped)."""
    matcher = re.compile(pattern)
    removed = 0
    for path in sorted((content / unit).glob('*.json')):
        payload = read(path)
        sources = payload.get('sourceUrls') or []
        keep = [url for url in sources if not matcher.search(url)]
        if len(keep) == len(sources):
            continue
        print(f'  {path.name}: -{len(sources) - len(keep)} sourceUrl(s)')
        removed += len(sources) - len(keep)
        if dry_run:
            continue
        payload['sourceUrls'] = keep
        write(path, payload)
    return removed


def normalise_people_heading(content: Path, unit: str, dry_run: bool) -> None:
    """The legacy heading is set in caps («ДЕКАНАТ ФІЗИКО-МАТЕМАТИЧНОГО ФАКУЛЬТЕТУ»)."""
    for path in sorted((content / unit).glob('*.json')):
        payload = read(path)
        changed = False
        for section in payload.get('sections', []):
            heading = section.get('peopleHeading')
            if heading and heading != 'Деканат' and heading.lower().startswith('деканат'):
                section['peopleHeading'] = 'Деканат'
                changed = True
        if not changed:
            continue
        print(f'  {path.name}: peopleHeading → «Деканат»')
        if not dry_run:
            write(path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--unit', required=True)
    parser.add_argument('--content', default=str(DEFAULT_CONTENT))
    parser.add_argument('--drop-shared', metavar='UNIT')
    parser.add_argument('--move-people', metavar='FROM:TO')
    parser.add_argument('--drop-source-urls', metavar='REGEX',
                        help='remove sourceUrls matching this pattern (the pages whose sections '
                             'were just dropped)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    content = Path(args.content)
    if not (content / args.unit).is_dir():
        print(f'! no such unit: {args.unit}', file=sys.stderr)
        return 1

    if args.drop_shared:
        print(f'drop-shared {args.unit} ↔ {args.drop_shared}')
        total = drop_shared(content, args.unit, args.drop_shared, args.dry_run)
        print(f'  {total} section(s) {"would be " if args.dry_run else ""}removed')

    if args.move_people:
        source_tab, _, target_tab = args.move_people.partition(':')
        print(f'move-people {source_tab} → {target_tab}')
        move_people(content, args.unit, source_tab, target_tab, args.dry_run)

    if args.drop_source_urls:
        print(f'drop-source-urls /{args.drop_source_urls}/')
        total = drop_source_urls(content, args.unit, args.drop_source_urls, args.dry_run)
        print(f'  {total} url(s) {"would be " if args.dry_run else ""}removed')

    normalise_people_heading(content, args.unit, args.dry_run)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
