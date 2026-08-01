#!/usr/bin/env python3
"""
Stage 4 — write the migrated content into the frontend.

Reads `content.draft.json` (stage 2) and `images.map.json` (stage 3) and emits, under
`knpu-university-fe/app/content/structure/`:

  * `manifest.json`                    — contacts + which tabs exist, imported eagerly
  * `<unit>/<tab>.<locale>.json`       — the bodies, each its own lazy chunk

Image sources are rewritten from the legacy host to `/assets/<uuid>`; the frontend renderer
absolutises those against the Directus public URL. An image that was never uploaded is dropped
(they are 404s on the old host, and an `http://` src is blocked as mixed content on an HTTPS
site); `--keep-missing-images` leaves the tag in place instead.

Keys are written in a stable order so a re-run produces a clean diff.

Usage:
    python3 4_emit.py --dry-run
    python3 4_emit.py --only arts
    python3 4_emit.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_TARGET = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'structure'

TAB_ORDER = ['home', 'admission', 'structure', 'history', 'education', 'science', 'students',
             'news', 'cooperation']
CONTACT_ORDER = ['dean', 'deanEn', 'deanUrl', 'position', 'positionEn', 'address', 'addressEn',
                 'phone', 'email', 'facebook', 'instagram']

IMG_TAG_RE = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"[^>]*/?>', re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--content', default=str(HERE / 'content.draft.json'))
    parser.add_argument('--map', dest='map_path', default=str(HERE / 'images.map.json'))
    parser.add_argument('--target', default=str(DEFAULT_TARGET))
    parser.add_argument('--only', default=None)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--keep-missing-images', action='store_true',
                        help='keep legacy <img> tags that were never uploaded (they are 404s)')
    return parser.parse_args()


def rewrite_images(markup: str, mapping: dict[str, str], missing: set[str], keep_missing: bool) -> str:
    """
    Point every picture at Directus. An image with no upload is dropped by default: it is gone
    from the legacy host (all of them are 404s), and an `http://` src would be blocked as mixed
    content on the HTTPS site anyway.
    """
    def replace(match: re.Match[str]) -> str:
        src = match.group(1)
        file_id = mapping.get(src)
        if not file_id:
            missing.add(src)
            return match.group(0) if keep_missing else ''
        return re.sub(r'\bsrc="[^"]+"', f'src="/assets/{file_id}"', match.group(0), count=1)
    return IMG_TAG_RE.sub(replace, markup)


def ordered_contacts(contacts: dict) -> dict:
    return {key: contacts[key] for key in CONTACT_ORDER if contacts.get(key)}


def main() -> int:
    args = parse_args()
    content = json.loads(Path(args.content).read_text(encoding='utf-8'))
    map_path = Path(args.map_path)
    mapping = json.loads(map_path.read_text(encoding='utf-8')) if map_path.exists() else {}
    if not mapping:
        print('! images.map.json is empty — run 3_load_images.py first, or accept legacy URLs',
              file=sys.stderr)

    target = Path(args.target)
    captured = date.today().isoformat()
    manifest: dict[str, dict] = {}
    missing_images: set[str] = set()
    written = 0

    for slug in sorted(content):
        if args.only and slug != args.only:
            continue
        unit = content[slug]
        tabs_with_content: list[str] = []

        for tab in TAB_ORDER:
            data = unit['tabs'].get(tab)
            if not data:
                continue
            has_body = False
            for locale in ('uk', 'en'):
                payload = data.get(locale)
                if not payload:
                    continue
                sections = [
                    {
                        **({'heading': section['heading']} if section.get('heading') else {}),
                        'html': rewrite_images(section['html'], mapping, missing_images, args.keep_missing_images),
                    }
                    for section in payload['sections']
                ]
                if not sections:
                    continue
                file_payload = {
                    'sections': sections,
                    **({'links': data['links']} if data.get('links') and locale == 'uk' else {}),
                    'sourceUrls': payload.get('sourceUrls', []),
                    'capturedAt': captured,
                }
                path = target / slug / f'{tab}.{locale}.json'
                if not args.dry_run:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(file_payload, ensure_ascii=False, indent=2) + '\n',
                                    encoding='utf-8')
                written += 1
                has_body = True

            # A tab can also be nothing but outbound documents.
            if not has_body and data.get('links'):
                path = target / slug / f'{tab}.uk.json'
                if not args.dry_run:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(
                        {'sections': [], 'links': data['links'], 'sourceUrls': [], 'capturedAt': captured},
                        ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                written += 1
                has_body = True

            if has_body:
                tabs_with_content.append(tab)

        manifest[slug] = {
            'legacyUrl': unit.get('legacyUrl'),
            'capturedAt': captured,
            'tabs': tabs_with_content,
            'contacts': ordered_contacts(unit.get('contacts') or {}),
        }

    if not args.dry_run:
        # Merge rather than replace, so `--only` never drops the other units.
        manifest_path = target / 'manifest.json'
        existing = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
        existing.update(manifest)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps({k: existing[k] for k in sorted(existing)}, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')

    print(
        f'{"Would write" if args.dry_run else "Wrote"} {written} content files for '
        f'{len(manifest)} units → {target}',
        file=sys.stderr,
    )
    if missing_images:
        action = 'kept their legacy URL' if args.keep_missing_images else 'were dropped'
        print(f'! {len(missing_images)} images have no Directus file and {action}:', file=sys.stderr)
        for url in sorted(missing_images)[:10]:
            print(f'    {url}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
