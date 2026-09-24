#!/usr/bin/env python3
"""
Додати посилання на рецензії під файлами освітньої програми (правка 24.09): ОП «Образотворче
мистецтво в закладах освіти», магістр (`programmes`, slug
`obrazotvorche-mystetstvo-v-zakladakh-osvity-master`). Рядок створено в адмінці прода, на локалі
його немає — тоді скрипт просто каже, що рядка не знайшов.

Під пунктом «Освітня програма 2026 року» з'являється «Рецензії на ОП 2026», під 2025 —
«Рецензії на ОП 2025» (папки Google Drive). Якорем є текст пункту, а не uuid файла, тож
перезалиті в адмінці PDF не заважають. Повторний запуск нічого не міняє.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 add_programme_reviews.py --dry-run
    python3 add_programme_reviews.py
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login  # noqa: E402

SLUG = 'obrazotvorche-mystetstvo-v-zakladakh-osvity-master'
REVIEWS = {
    'Освітня програма 2026 року': (
        'Рецензії на ОП 2026',
        'https://drive.google.com/drive/folders/1K4zlP0Atysx_TQfu0ASm6apg7oCnSHAF'),
    'Освітня програма 2025 року': (
        'Рецензії на ОП 2025',
        'https://drive.google.com/drive/folders/1K9VzEom5_gA-Xv2Dj_K4Sf0D9gx3Q2X-'),
}


def with_reviews(content: str) -> tuple[str, list[str]]:
    notes = []
    for anchor, (label, url) in REVIEWS.items():
        if url in content:
            notes.append(f'  = {label}: вже є')
            continue
        item = re.search(r'<li>(?:(?!</li>).)*?' + re.escape(anchor) + r'.*?</li>', content, re.S)
        if not item:
            notes.append(f'  ! {label}: пункту «{anchor}» не знайдено')
            continue
        link = f'\n<li><a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a></li>'
        content = content[:item.end()] + link + content[item.end():]
        notes.append(f'  + {label}')
    return content, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directus-url',
                        default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)
    rows = directus.get(f'/items/programmes?filter[slug][_eq]={quote(SLUG)}&fields=id,content&limit=1')
    if not rows:
        print(f'  ! programmes/{SLUG}: рядка немає на цілі', file=sys.stderr)
        return 1
    row = rows[0]
    content, notes = with_reviews(row['content'] or '')
    print('\n'.join(notes), file=sys.stderr)
    if content == row['content']:
        print('змін немає', file=sys.stderr)
        return 0
    if args.dry_run:
        print(content)
        return 0
    directus.request('PATCH', f'/items/programmes/{row["id"]}', {'content': content})
    print('оновлено', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
