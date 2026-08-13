#!/usr/bin/env python3
"""
Stage 1 — build the body of `/education/digital-center` from the legacy markup.

The first migration flattened the page: the old site wrapped every topic in a `[collapse]`
shortcode, and the generic cleaner dropped those markers, leaving one wall of text. The client
asked for the drop-downs back, so this script keeps the shortcodes as structure instead:
each `[collapse title=…]` becomes a `collapsible` section (nested ones become `children`),
which `SharedStaticPageBody` renders through `SharedAccordion`.

Input is `source/body.uk.html` — the page body as the client sent it, with the shortcodes
intact. It is committed rather than fetched, because Cloudflare blocks scripted requests to the
old site and the client's copy is newer than the SQL dump.

Cleaning reuses `../structure-pages/2_transform.py`, so the markup that comes out is the same
subset the frontend's sanitizer accepts. Images are uploaded to Directus (same helper as
`../pages/migrate_page.py`) and rewritten to `/assets/<uuid>`; the ids are baked into the
committed JSON, so run `../pages/sync_images.py` before pointing the site at another Directus.

Usage:
    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin

    python3 1_build_body.py --dry-run
    python3 1_build_body.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / 'source' / 'body.uk.html'
IMAGES_MAP = HERE / 'images.map.json'
TARGET_DIR = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'pages'
SLUG = 'digital-center'
LEGACY_URL = 'https://hnpu.edu.ua/uk/division/centr-cyfrovizaciyi-osvity'
LEGACY_URL_EN = 'https://hnpu.edu.ua/en/division/education-digitalisation-center'

# Straight from the English version of the legacy page — the only English text it had.
INTRO_EN = (
    '<p>The purpose of the centre\'s activities is to establish a cohesive policy for the '
    'digitalization of the educational process, scientific research, and university management '
    'systems. It aims to drive the development, implementation, and support of innovative '
    'information and communication technologies within the university, ensuring alignment with '
    'broader advancements at the local and national levels.</p>'
)

# Headings only: the bodies stay Ukrainian, because every document and form behind them is.
HEADINGS_EN = {
    'Оголошення': 'Announcements',
    'Про реєстрацію на платформі Coursera': 'Registering on the Coursera platform',
    'Про можливості використання онлайн-платформи openHPI': 'Using the openHPI online platform',
    'Напрями діяльності': 'Areas of work',
    'Платформа MOODLE': 'The MOODLE platform',
    'Стажування на платформі Moodle': 'Moodle training for teaching staff',
    'Сертифікація електронного навчального курсу': 'Certification of an e-learning course',
    'Офіційний сайт університету': 'The university website',
    'Проведення заходів': 'Running events',
    'Корпоративна пошта': 'Corporate email',
    'Обліковий запис Zoom': 'Zoom account',
}

COLLAPSE_OPEN_RE = re.compile(r'\[collapse(?:\s+collapsed)?\s+title=([^\]]*)\]')
COLLAPSE_CLOSE = '[/collapse]'
HEADING_RE = re.compile(r'<h2\b[^>]*>(.*?)</h2>', re.S)


def load_transform():
    """Import 2_transform.py by path — its name is not a valid module identifier."""
    spec = importlib.util.spec_from_file_location(
        'legacy_transform', HERE.parent / 'structure-pages' / '2_transform.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_page_helpers():
    spec = importlib.util.spec_from_file_location(
        'legacy_migrate_page', HERE.parent / 'pages' / 'migrate_page.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Node:
    """One `[collapse]` block, or the loose markup between two of them."""

    def __init__(self, title: str | None) -> None:
        self.title = title
        self.chunks: list[str] = []
        self.children: list[Node] = []


def parse_collapses(markup: str) -> Node:
    """
    Turn the shortcodes into a tree.

    The old editor nested them one level deep («Стажування» inside «Платформа MOODLE»); the
    parser handles any depth, and an unbalanced `[/collapse]` is reported instead of silently
    swallowing the rest of the page.
    """
    root = Node(None)
    stack = [root]
    position = 0

    while position < len(markup):
        opening = COLLAPSE_OPEN_RE.search(markup, position)
        closing = markup.find(COLLAPSE_CLOSE, position)
        if opening and (closing == -1 or opening.start() < closing):
            stack[-1].chunks.append(markup[position:opening.start()])
            node = Node(unescape_title(opening.group(1)))
            stack[-1].children.append(node)
            stack.append(node)
            position = opening.end()
        elif closing != -1:
            stack[-1].chunks.append(markup[position:closing])
            if len(stack) == 1:
                raise SystemExit(f'unbalanced [/collapse] at offset {closing}')
            stack.pop()
            position = closing + len(COLLAPSE_CLOSE)
        else:
            stack[-1].chunks.append(markup[position:])
            break

    if len(stack) != 1:
        raise SystemExit(f'{len(stack) - 1} unclosed [collapse] block(s)')
    return root


def unescape_title(raw: str) -> str:
    return re.sub(r'\s+', ' ', raw.replace('&nbsp;', ' ')).strip()


def split_on_headings(html: str) -> list[dict]:
    """
    Cut loose markup into sections at every `<h2>`.

    The heading moves out of the prose into `section.heading`, which is what gives «Оголошення»
    and «Напрями діяльності» the same title styling as everywhere else on the site.
    """
    sections: list[dict] = []
    position = 0
    heading: str | None = None

    for match in HEADING_RE.finditer(html):
        body = html[position:match.start()].strip()
        if heading or body:
            sections.append({k: v for k, v in (('heading', heading), ('html', body)) if v is not None})
        heading = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        position = match.end()

    tail = html[position:].strip()
    if heading or tail:
        sections.append({k: v for k, v in (('heading', heading), ('html', tail)) if v is not None})
    return sections


def sections_from_tree(root: Node, transform) -> tuple[list[dict], list[str]]:
    """
    Flatten the tree into the `sections[]` the frontend renders.

    Loose markup between collapses is emitted as plain sections, and an `<h2>` in it becomes the
    section heading — that is how «Оголошення» and «Напрями діяльності» keep their titles without
    a heading tag inside the prose.
    """
    sections: list[dict] = []
    images: list[str] = []

    def clean(chunk: str) -> str:
        html, found = transform.clean_body(chunk)
        images.extend(found)
        # The cleaner resolves every relative URL against the old site, which would send the
        # `/assets/<uuid>` links we put in the source (files already mirrored into Directus)
        # back to hnpu.edu.ua. Undo that — the frontend resolves them against Directus itself.
        html = html.replace('https://hnpu.edu.ua/assets/', '/assets/')
        return html

    def collapsible_section(node: Node) -> dict:
        section: dict = {'heading': node.title, 'collapsible': True, 'html': ''}
        parts: list[str] = []
        children: list[dict] = []
        for chunk in node.chunks:
            html = clean(chunk)
            if html:
                parts.append(html)
        for child in node.children:
            children.append(collapsible_section(child))
        section['html'] = '\n'.join(parts)
        if children:
            section['children'] = children
        return section

    for index, chunk in enumerate(root.chunks):
        html = clean(chunk)
        if html:
            sections.extend(split_on_headings(html))
        # A collapse always follows the chunk with the same index.
        if index < len(root.children):
            sections.append(collapsible_section(root.children[index]))

    for node in root.children[len(root.chunks):]:
        sections.append(collapsible_section(node))

    return sections, images


def translate(sections: list[dict]) -> list[dict]:
    """English variant: translated headings, Ukrainian bodies (the documents are Ukrainian)."""
    out = []
    for section in sections:
        copy = dict(section)
        heading = section.get('heading')
        if heading:
            copy['heading'] = HEADINGS_EN.get(heading, heading)
            if heading not in HEADINGS_EN:
                print(f'  ! no English heading for {heading!r}', file=sys.stderr)
        if section.get('children'):
            copy['children'] = translate(section['children'])
        out.append(copy)
    return out


def replace_images(sections: list[dict], mapping: dict[str, str]) -> None:
    for section in sections:
        for legacy, asset in mapping.items():
            section['html'] = section['html'].replace(legacy, asset)
        if section.get('children'):
            replace_images(section['children'], mapping)


def count(sections: list[dict]) -> tuple[int, int]:
    total = len(sections)
    collapsible = sum(1 for section in sections if section.get('collapsible'))
    for section in sections:
        if section.get('children'):
            nested_total, nested_collapsible = count(section['children'])
            total += nested_total
            collapsible += nested_collapsible
    return total, collapsible


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--target', default=str(TARGET_DIR))
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--keep-images', action='store_true',
                        help='leave image URLs on the old host instead of uploading them')
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    transform = load_transform()

    markup = SOURCE.read_text(encoding='utf-8')
    tree = parse_collapses(markup)
    sections, images = sections_from_tree(tree, transform)

    images = list(dict.fromkeys(images))
    mapping = json.loads(IMAGES_MAP.read_text(encoding='utf-8')) if IMAGES_MAP.exists() else {}
    todo = [url for url in images if url not in mapping]

    if todo and not args.keep_images and not args.dry_run:
        helpers = load_page_helpers()
        token = args.token or helpers.directus_login(args.directus_url, args.email, args.password)
        for url in todo:
            file_id = helpers.upload_image(args.directus_url, token, url)
            if file_id:
                mapping[url] = f'/assets/{file_id}'
                print(f'  uploaded {url} → {mapping[url]}')
        IMAGES_MAP.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + '\n',
                              encoding='utf-8')

    replace_images(sections, mapping)

    total, collapsible = count(sections)
    print(f'{total} sections, {collapsible} collapsible, {len(images)} image(s)')
    for section in sections:
        marker = '▸' if section.get('collapsible') else '·'
        print(f'  {marker} {section.get("heading") or "(intro)"} — {len(section["html"])} chars')
        for child in section.get('children', []):
            print(f'      ▸ {child.get("heading")} — {len(child["html"])} chars')

    captured = date.today().isoformat()
    payloads = {
        'uk': {'title': 'Центр цифровізації освіти', 'sections': sections,
               'sourceUrls': [LEGACY_URL], 'capturedAt': captured},
        'en': {'title': 'Centre for Digitalisation of Education',
               'sections': [{'html': INTRO_EN}] + translate(sections)[1:],
               'sourceUrls': [LEGACY_URL_EN, LEGACY_URL], 'capturedAt': captured},
    }

    if args.dry_run:
        print('\n(dry run — nothing written)')
        return 0

    target = Path(args.target)
    for locale, payload in payloads.items():
        path = target / f'{SLUG}.{locale}.json'
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'wrote {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
