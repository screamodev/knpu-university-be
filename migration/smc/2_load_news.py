#!/usr/bin/env python3
"""
Stage 2 — load the quality centre's news into `articles`.

The centre kept its news as accordion blocks of one Joomla page; stage 1 split them. Here each
block becomes an ordinary article of this site, tagged «Центр забезпечення якості освіти», so the
Новини tab of /education/quality is a live feed and the centre keeps publishing through Directus.

Photos inside an entry are uploaded and their URLs rewritten to `/assets/<uuid>`; the first photo
becomes the cover. Idempotent on `slug`.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 2_load_news.py --dry-run
    python3 2_load_news.py --limit 5
    python3 2_load_news.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'pass2'))
from common import Directus, download, filename_for, login, upload  # noqa: E402

HERE = Path(__file__).parent
CATEGORY_SLUG = 'tsentr-zabezpechennya-yakosti'
CATEGORY_NAME = 'Центр забезпечення якості освіти'
CATEGORY_NAME_EN = 'Centre for Quality Assurance in Education'

TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e', 'є': 'ie', 'ж': 'zh',
    'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ь': '', 'ю': 'iu', 'я': 'ia', '’': '', "'": '',
}


def slugify(text: str, limit: int = 70) -> str:
    lowered = unicodedata.normalize('NFC', text).lower()
    out = ''.join(TRANSLIT.get(char, char) for char in lowered)
    out = re.sub(r'[^a-z0-9]+', '-', out).strip('-')
    return out[:limit].strip('-') or 'novyna'


def ensure_category(directus: Directus) -> str:
    query = urllib.parse.urlencode({'fields': 'id,name', 'filter[slug][_eq]': CATEGORY_SLUG, 'limit': '1'})
    found = directus.get(f'/items/categories?{query}') or []
    if found:
        return found[0]['id']
    created = directus.request('POST', '/items/categories', payload={
        'name': CATEGORY_NAME, 'nameEn': CATEGORY_NAME_EN, 'slug': CATEGORY_SLUG,
    })
    print(f'created category «{CATEGORY_NAME}»', file=sys.stderr)
    return created['id']


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', default=str(HERE / 'data' / 'news.json'))
    parser.add_argument('--map', default=str(HERE / 'images.map.json'))
    parser.add_argument('--limit', type=int)
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    entries = json.loads(Path(args.input).read_text(encoding='utf-8'))
    for entry in entries:
        entry['slug'] = f'smc-{entry["date"] or "bez-daty"}-{slugify(entry["title"], 50)}'

    if args.dry_run:
        for entry in entries:
            print(f'{entry["date"] or "—":<12} {len(entry["images"]):>2} img  {entry["slug"][:80]}')
        print(f'\n{len(entries)} entries, {sum(len(e["images"]) for e in entries)} photos', file=sys.stderr)
        return 0

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)
    category_id = ensure_category(directus)

    map_path = Path(args.map)
    uploaded: dict[str, str] = json.loads(map_path.read_text(encoding='utf-8')) if map_path.exists() else {}
    created = updated = failed = 0

    for index, entry in enumerate(entries, 1):
        slug = entry['slug']
        query = urllib.parse.urlencode({'fields': 'id', 'filter[slug][_eq]': slug, 'limit': '1'})
        existing = directus.get(f'/items/articles?{query}') or []

        html = entry['html']
        cover: str | None = None
        for source in entry['images']:
            file_id = uploaded.get(source)
            if not file_id:
                downloaded = download(source)
                if not downloaded:
                    continue
                content, content_type = downloaded
                try:
                    file_id = upload(directus, content, filename_for(source), content_type,
                                     entry['title'][:255], None)
                except urllib.error.HTTPError as exc:
                    print(f'    ! upload {exc.code}: {exc.read().decode("utf-8", "replace")[:160]}',
                          file=sys.stderr)
                    continue
                uploaded[source] = file_id
                map_path.write_text(json.dumps(uploaded, ensure_ascii=False, indent=2) + '\n',
                                    encoding='utf-8')
            html = html.replace(source, f'/assets/{file_id}')
            cover = cover or file_id

        payload = {
            'status': 'published',
            'title': entry['title'][:255],
            'slug': slug,
            'content': html,
            'date_published': entry['date'],
            'cover': cover,
            'categories': [{'categories_id': category_id}],
        }

        try:
            if existing:
                directus.request('PATCH', f'/items/articles/{existing[0]["id"]}', payload=payload)
                updated += 1
            else:
                directus.request('POST', '/items/articles', payload=payload)
                created += 1
        except urllib.error.HTTPError as exc:
            print(f'    ! {slug}: {exc.code} {exc.read().decode("utf-8", "replace")[:200]}', file=sys.stderr)
            failed += 1
            continue

        if index % 10 == 0:
            print(f'  [{index}/{len(entries)}] {slug[:70]}', file=sys.stderr)
        if args.limit and created + updated >= args.limit:
            break

    print(f'\ncreated={created} updated={updated} failed={failed}', file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
