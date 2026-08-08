#!/usr/bin/env python3
"""
Append a legacy page to a unit's tab in `app/content/structure/<unit>/<tab>.<locale>.json`.

The faculty pipeline (`../structure-pages`) builds those files from the Drupal dump, but units
outside it — the відділ аспірантури і докторантури, whose tabs are hand-made — have no way to
gain content. This does the single-page version: fetch, clean the body with the same transformer
the pipeline uses, move the images into Directus, and append a `{heading, html}` section.

Idempotent through `sourceUrls`: a page already recorded there is skipped.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 append_structure_section.py --unit postgraduate --tab students \
        --url https://hnpu.edu.ua/uk/division/aspiranty-gromadyany-ukrayiny \
        --heading "Аспіранти — громадяни України" --dry-run
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from common import BROWSER_HEADERS, Directus, login, upload

HERE = Path(__file__).parent
STRUCTURE_PAGES = HERE.parent / 'structure-pages'
PAGES = HERE.parent / 'pages'
DEFAULT_CONTENT = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'structure'

BODY_RE = re.compile(r'<div class="field field-name-body.*?</div>\s*</div>\s*</div>', re.S)
IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.I)
LEGACY_PAGE_LINK_RE = re.compile(
    r'<a\s[^>]*href="(?P<href>[^"]*hnpu\.edu\.ua[^"]*)"[^>]*>(?P<text>.*?)</a>', re.S)
FILE_HREF_RE = re.compile(r'\.(pdf|docx?|xlsx?|pptx?|rtf|odt|zip|jpe?g|png)(\?|$)', re.I)


def load_transform():
    """Import 2_transform.py by path — its name is not a valid module identifier."""
    spec = importlib.util.spec_from_file_location('legacy_transform', STRUCTURE_PAGES / '2_transform.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode('utf-8', 'replace')


def unlink_legacy_pages(html: str) -> str:
    """Keep the text of links that point back at pages of the old site, drop the link itself."""
    def unwrap(match: re.Match[str]) -> str:
        if FILE_HREF_RE.search(match.group('href').split('#')[0]):
            return match.group(0)
        return match.group('text')

    return LEGACY_PAGE_LINK_RE.sub(unwrap, html)


def upload_images(directus: Directus, html: str, images: list[str]) -> str:
    mapping: dict[str, str] = {}
    for source in dict.fromkeys(images):
        if not source.startswith(('http://', 'https://')):
            continue
        try:
            request = urllib.request.Request(source, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(request, timeout=180) as response:
                content = response.read()
                content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip()
        except (urllib.error.URLError, OSError) as exc:
            print(f'  ! image {source}: {exc}', file=sys.stderr)
            continue
        filename = source.rsplit('/', 1)[-1][:200] or 'image.jpg'
        mapping[source] = upload(directus, content, filename, content_type, filename[:255], None)

    print(f'  uploaded {len(mapping)}/{len(set(images))} image(s)', file=sys.stderr)

    def replace(match: re.Match[str]) -> str:
        file_id = mapping.get(match.group(2))
        # An http:// image would be blocked as mixed content, so a failed upload drops the tag.
        return f'{match.group(1)}/assets/{file_id}{match.group(3)}' if file_id else ''

    return IMG_SRC_RE.sub(replace, html)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--unit', required=True)
    parser.add_argument('--tab', required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--heading', help='section heading; defaults to the page\'s <h1>')
    parser.add_argument('--locale', default='uk')
    parser.add_argument('--content', default=str(DEFAULT_CONTENT))
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    path = Path(args.content) / args.unit / f'{args.tab}.{args.locale}.json'
    if not path.exists():
        print(f'! no such tab file: {path}', file=sys.stderr)
        return 1

    payload = json.loads(path.read_text(encoding='utf-8'))
    if args.url in (payload.get('sourceUrls') or []):
        print(f'{path.name}: already has {args.url}')
        return 0

    page = fetch(args.url)
    body = BODY_RE.search(page)
    if not body:
        print('! no field-name-body on that page — check the URL', file=sys.stderr)
        return 1

    transform = load_transform()
    html, images = transform.clean_body(body.group(0))
    html = unlink_legacy_pages(html)

    heading = args.heading
    if not heading:
        title = re.search(r'<h1[^>]*>(.*?)</h1>', page, re.S)
        heading = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', title.group(1))).strip() if title else None

    print(f'{path.name} ← {heading!r}: {len(html)} chars, {len(images)} image(s)', file=sys.stderr)
    if args.dry_run:
        print(html[:800])
        return 0

    if images:
        token = args.token or login(args.directus_url, args.email, args.password)
        html = upload_images(Directus(args.directus_url, token), html, images)

    payload.setdefault('sections', []).append({'heading': heading, 'html': html})
    payload['sourceUrls'] = (payload.get('sourceUrls') or []) + [args.url]
    payload['capturedAt'] = date.today().isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'→ {path}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
