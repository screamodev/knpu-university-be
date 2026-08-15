#!/usr/bin/env python3
"""
Stage 2 — перенести сторінки розділу приймальної комісії у статичний контент фронтенду.

Для кожного запису з `data/pages.json` викликає `../pages/migrate_page.py` (та сама чистка HTML,
що й для решти перенесених сторінок, зображення переїжджають у Directus) і пише
`app/content/pages/<slug>.uk.json`.

Далі робить те, чого одиночний перенос не вміє: перелінковує розділ сам на себе. Сторінки
кампанії посилаються одна на одну десятками покликань на `hnpu.edu.ua/uk/…`; за картою
`path → slug` вони стають внутрішніми адресами `/admissions/info/<slug>`, тож відвідувач не
випадає на старий сайт.

Наприкінці пише `app/content/admissions/manifest.json` — дерево розділу (поточна кампанія та
архіви за роками), з якого фронтенд будує сторінку-хаб і навігацію.

    python3 2_emit.py --limit 5      # спробувати на кількох
    python3 2_emit.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
PAGES_SCRIPT = HERE.parent / 'pages' / 'migrate_page.py'
CONTENT = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content'
DEFAULT_INPUT = HERE / 'data' / 'pages.json'

ROUTE = '/admissions/info'


def emit_one(entry: dict, dry_run: bool) -> bool:
    command = [sys.executable, str(PAGES_SCRIPT), '--slug', entry['slug'], '--url', entry['url']]
    if dry_run:
        command.append('--dry-run')
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ['—']
        print(f'  ! {entry["slug"]}: {tail[0][:110]}', file=sys.stderr)
        return False
    return True


def relink(pages: list[dict]) -> int:
    """Внутрішні покликання розділу → наші адреси."""
    by_path = {entry['path']: entry['slug'] for entry in pages}
    # Довші шляхи першими, щоб /uk/a-b не з'їв /uk/a-b-c.
    pattern = re.compile(
        r'(?:https?:)?//hnpu\.edu\.ua(' + '|'.join(
            re.escape(path) for path in sorted(by_path, key=len, reverse=True)) + r')(?![\w-])')
    changed = 0

    for entry in pages:
        path = CONTENT / 'pages' / f'{entry["slug"]}.uk.json'
        if not path.exists():
            continue
        text = path.read_text(encoding='utf-8')
        replaced = pattern.sub(lambda m: f'{ROUTE}/{by_path[m.group(1)]}', text)
        # Той самий шлях без хоста трапляється в href="/uk/…".
        replaced = re.sub(
            r'"(' + '|'.join(re.escape(p) for p in sorted(by_path, key=len, reverse=True)) + r')(?![\w-])',
            lambda m: f'"{ROUTE}/{by_path[m.group(1)]}', replaced)
        if replaced != text:
            path.write_text(replaced, encoding='utf-8')
            changed += 1
    return changed


def write_manifest(pages: list[dict]) -> Path:
    groups: dict[str, list[dict]] = {}
    for entry in pages:
        groups.setdefault(entry['group'], []).append(
            {'slug': entry['slug'], 'title': entry['title'], 'source': entry['url']})
    manifest = {
        'root': pages[0]['slug'] if pages else None,
        'campaign': groups.get('campaign', []),
        'archives': [
            {'year': group.removeprefix('archive-'), 'pages': entries}
            for group, entries in sorted(groups.items(), reverse=True) if group.startswith('archive-')
        ],
    }
    out = CONTENT / 'admissions' / 'manifest.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', default=str(DEFAULT_INPUT))
    parser.add_argument('--limit', type=int)
    parser.add_argument('--skip-existing', action='store_true',
                        help='не переносити сторінки, які вже є в контенті')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    pages = json.loads(Path(args.input).read_text(encoding='utf-8'))
    if args.limit:
        pages = pages[:args.limit]

    done = failed = skipped = 0
    for index, entry in enumerate(pages, 1):
        target = CONTENT / 'pages' / f'{entry["slug"]}.uk.json'
        if args.skip_existing and target.exists():
            skipped += 1
            continue
        print(f'[{index}/{len(pages)}] {entry["slug"]}', file=sys.stderr)
        if emit_one(entry, args.dry_run):
            done += 1
        else:
            failed += 1

    if args.dry_run:
        print(f'\ndry run: {done} ok, {failed} помилок', file=sys.stderr)
        return 0

    changed = relink(pages)
    manifest = write_manifest(pages)
    print(f'\nперенесено={done} пропущено={skipped} помилок={failed}; '
          f'перелінковано файлів: {changed}\n→ {manifest}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
