#!/usr/bin/env python3
"""
Опис конференції — WYSIWYG замість простого текстового поля.

Редактори вставляли в `description` посилання на інформаційний лист, і на сайті воно лишалося
текстом. Скрипт робить дві речі:

1. Перемикає `science_conferences.description` і `.descriptionEn` на той самий редактор, що в
   новинах і на сторінках підрозділів (посилання, жирний, списки).
2. Переводить уже збережені описи з простого тексту в HTML: рядки стають `<br>`, голі адреси —
   посиланнями. Без цього TinyMCE при першому ж відкритті злив би рядки в один абзац. Описи, які
   вже є HTML, не чіпає, тож повторний запуск нічого не міняє.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 rich_conference_descriptions.py --dry-run
    python3 rich_conference_descriptions.py
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from pathlib import Path

MIGRATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MIGRATION / 'pass2'))
sys.path.insert(0, str(MIGRATION / 'schema'))

from apply_schema import MEDIA_STRUCTURE_FOLDER, rich_text  # noqa: E402
from common import Directus, login  # noqa: E402

COLLECTION = 'science_conferences'
FIELDS = {
    'description': 'Опис конференції. Посилання (напр. на інформаційний лист) ставте кнопкою '
                   '«посилання» — на сайті вони будуть клікабельні.',
    'descriptionEn': 'Опис англійською. Порожньо — сайт покаже українську версію.',
}

HTML_TAG = re.compile(r'<(p|br|a|ul|ol|li|strong|em|b|i|div|h[1-6])\b', re.I)
URL = re.compile(r'https?://[^\s<>"]+')


def plain_to_html(text: str) -> str:
    def paragraph(block: str) -> str:
        lines = []
        for line in block.split('\n'):
            escaped = html.escape(line.strip(), quote=False)
            lines.append(URL.sub(
                lambda m: f'<a href="{html.escape(html.unescape(m.group(0)))}" target="_blank" '
                          f'rel="noopener noreferrer">{m.group(0)}</a>',
                escaped,
            ))
        return '<p>' + '<br>'.join(line for line in lines if line) + '</p>'

    blocks = [b for b in re.split(r'\n\s*\n', text.replace('\r\n', '\n').strip()) if b.strip()]
    return '\n'.join(paragraph(block) for block in blocks)


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

    for name, note in FIELDS.items():
        current = directus.get(f'/fields/{COLLECTION}/{name}') or {}
        if (current.get('meta') or {}).get('interface') == 'input-rich-text-html':
            print(f'  = {COLLECTION}.{name}: уже WYSIWYG', file=sys.stderr)
            continue
        spec = rich_text(name, note, folder=MEDIA_STRUCTURE_FOLDER)
        meta = {key: spec['meta'][key] for key in ('interface', 'options', 'note')}
        print(f'  ~ {COLLECTION}.{name}: input-multiline → WYSIWYG', file=sys.stderr)
        if not args.dry_run:
            directus.request('PATCH', f'/fields/{COLLECTION}/{name}', payload={'meta': meta})

    rows = directus.get(f'/items/{COLLECTION}?fields=id,title,{",".join(FIELDS)}&limit=-1') or []
    for row in rows:
        patch = {}
        for name in FIELDS:
            value = row.get(name) or ''
            if value.strip() and not HTML_TAG.search(value):
                patch[name] = plain_to_html(value)
        if not patch:
            continue
        print(f'  ~ «{(row.get("title") or "")[:60]}»: {sorted(patch)} → HTML', file=sys.stderr)
        if not args.dry_run:
            directus.request('PATCH', f'/items/{COLLECTION}/{row["id"]}', payload=patch)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
