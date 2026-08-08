#!/usr/bin/env python3
"""
Migrate a single prose page from the old site into the frontend's static content.

The faculty pipeline (`../structure-pages`) exists for whole units with sidebars; this is the
one-off version: fetch a page, clean its HTML the same way, move its images into Directus, and
write `app/content/pages/<slug>.<locale>.json`.

Reuses `2_transform.py` from the structure-pages migration for the HTML cleaning, so both paths
produce exactly the same subset of markup that the frontend's sanitizer accepts.

Usage:
    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin

    python3 migrate_page.py --slug language-exam \\
      --url https://hnpu.edu.ua/uk/ispyt-na-vyznachennya-rivnya-volodinnya-derzhavnoyu-movoyu-20-dlya-vykonannya-sluzhbovyh-obovyazkiv

    python3 migrate_page.py --slug language-exam --url … --dry-run
"""

from __future__ import annotations

import argparse
import html as html_lib
import importlib.util
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
STRUCTURE_PAGES = HERE.parent / 'structure-pages'
DEFAULT_TARGET = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'pages'
FOLDER_NAME = 'structure-pages'

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,image/*,*/*;q=0.8',
    'Accept-Language': 'uk,en;q=0.8',
}

BODY_RE = re.compile(r'<div class="field field-name-body.*?</div>\s*</div>\s*</div>', re.S)
# The quality centre runs Joomla instead of Drupal; its article body is marked up differently.
JOOMLA_BODY_RE = re.compile(r'<div[^>]*itemprop="articleBody"[^>]*>(.*?)</div>\s*</div>', re.S)
# Some Joomla pages render their text through a module instead of an article; those need the
# region named explicitly with --body-start / --body-end.
JOOMLA_FOOTER_MARKER = r'<footer|id="sp-footer"|© Центр забезпечення якості освіти'
H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S)
IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.I)


def load_transform():
    """Import 2_transform.py by path — its name is not a valid module identifier."""
    spec = importlib.util.spec_from_file_location('legacy_transform', STRUCTURE_PAGES / '2_transform.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode('utf-8', 'replace')


def directus_login(base: str, email: str, password: str) -> str:
    request = urllib.request.Request(
        f'{base.rstrip("/")}/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode(),
        headers={**BROWSER_HEADERS, 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())['data']['access_token']


def upload_image(base: str, token: str, url: str) -> str | None:
    """Download a legacy image and put it in Directus; returns the new file id."""
    import mimetypes
    import uuid as uuid_mod
    # Some legacy pages carry spacer images with an empty or relative-only src.
    if not url.startswith(('http://', 'https://')):
        print(f'  ! image skipped, not an absolute URL: {url!r}', file=sys.stderr)
        return None
    try:
        request = urllib.request.Request(url, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
            content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip()
    except (urllib.error.URLError, OSError) as exc:
        print(f'  ! image {url}: {exc}', file=sys.stderr)
        return None

    filename = url.rsplit('/', 1)[-1][:200] or 'image.jpg'
    if not content_type or content_type == 'application/octet-stream':
        content_type = mimetypes.guess_type(filename)[0] or 'image/jpeg'

    boundary = f'----knpu{uuid_mod.uuid4().hex}'
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\n{filename}\r\n'.encode(),
             f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
             f'Content-Type: {content_type}\r\n\r\n'.encode(),
             content,
             f'\r\n--{boundary}--\r\n'.encode()]
    request = urllib.request.Request(
        f'{base.rstrip("/")}/files', data=b''.join(parts),
        headers={'Authorization': f'Bearer {token}',
                 'Content-Type': f'multipart/form-data; boundary={boundary}'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read())['data']['id']
    except urllib.error.HTTPError as exc:
        print(f'  ! upload {url}: HTTP {exc.code} {exc.read().decode("utf-8", "replace")[:200]}', file=sys.stderr)
        return None


DOCUMENTS_JSON = HERE.parent / 'documents' / 'documents.json'
PASS2_DOCUMENTS_JSON = HERE.parent / 'pass2' / 'data' / 'documents.json'


def migrated_urls(section: str) -> set[str]:
    """
    Source URLs already loaded into `documents` for this section.

    Two payload shapes exist: the first pass wrote a flat list of rows with `sourceUrl`, the
    second wraps batches and names the URL `_file` / `externalUrl`. Both are consulted, so a page
    migrated after either pass has its links stripped.
    """
    urls: set[str] = set()

    if DOCUMENTS_JSON.exists():
        for row in json.loads(DOCUMENTS_JSON.read_text(encoding='utf-8')):
            if row.get('section') == section and row.get('sourceUrl'):
                urls.add(row['sourceUrl'])

    if PASS2_DOCUMENTS_JSON.exists():
        payload = json.loads(PASS2_DOCUMENTS_JSON.read_text(encoding='utf-8'))
        for batch in payload.get('batches', []):
            for row in batch['rows']:
                if row.get('section') != section:
                    continue
                url = row.get('_file') or row.get('externalUrl')
                if url:
                    urls.add(url)

    return urls
LIST_ITEM_RE = re.compile(r'<li\b[^>]*>(.*?)</li>', re.S)
EMPTY_LIST_RE = re.compile(r'<(ul|ol)\b[^>]*>\s*</\1>', re.S)
PARAGRAPH_RE = re.compile(r'<p\b[^>]*>(.*?)</p>', re.S)


def strip_document_links(html: str, section: str) -> str:
    """
    Drop list items and paragraphs that are nothing but a link already loaded into `documents`.

    Matching is by exact URL against the loaders' payloads rather than by file extension:
    these pages mix PDFs, scanned JPEGs and Google Drive links, and only the loader knows which
    of them became rows. Whatever it did not take stays in the prose.
    """
    known = migrated_urls(section)
    if not known:
        print(f'  ! no documents rows for section {section!r} — nothing stripped', file=sys.stderr)
        return html

    def drop_if_migrated(match: re.Match[str]) -> str:
        inner = match.group(1)
        links = [html_lib.unescape(href) for href in re.findall(r'<a\s[^>]*href="([^"]+)"', inner)]
        if not links or not all(absolute_href(href) in known for href in links):
            return match.group(0)
        # Keep anything that also carries its own sentence outside the link text.
        without_links = re.sub(r'<a\s.*?</a>', '', inner, flags=re.S)
        return '' if len(re.sub(r'<[^>]+>|\s', '', without_links)) < 15 else match.group(0)

    html = LIST_ITEM_RE.sub(drop_if_migrated, html)
    html = PARAGRAPH_RE.sub(drop_if_migrated, html)
    html = EMPTY_LIST_RE.sub('', html)
    return re.sub(r'\n{3,}', '\n\n', html).strip()


LEGACY_PAGE_LINK_RE = re.compile(
    r'<a\s[^>]*href="(?P<href>[^"]*hnpu\.edu\.ua[^"]*)"[^>]*>(?P<text>.*?)</a>', re.S)
FILE_HREF_RE = re.compile(r'\.(pdf|docx?|xlsx?|pptx?|rtf|odt|zip|jpe?g|png)(\?|$)', re.I)


def unlink_legacy_pages(html: str) -> str:
    """
    Unwrap links that point at pages of the old site, keeping their text.

    Migrated prose must not send visitors back to hnpu.edu.ua / smc.hnpu.edu.ua: those pages are
    being replaced by this site. Links to files are left alone — either they were already turned
    into `documents` rows and stripped, or they are the only copy there is.
    """
    def unwrap(match: re.Match[str]) -> str:
        if FILE_HREF_RE.search(match.group('href').split('#')[0]):
            return match.group(0)
        return match.group('text')

    return LEGACY_PAGE_LINK_RE.sub(unwrap, html)


def absolute_href(href: str) -> str:
    """Match the normalisation `../documents/1_extract.py` applied when it stored the URL."""
    return 'https:' + href if href.startswith('//') else href


def parse_args() -> argparse.Namespace:
    import os
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--slug', required=True, help='output file name, e.g. language-exam')
    parser.add_argument('--url', required=True)
    parser.add_argument('--locale', default='uk')
    parser.add_argument('--target', default=str(DEFAULT_TARGET))
    parser.add_argument('--directus-url', default=(os.environ.get('DIRECTUS_URL') or 'http://localhost:8055'))
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=(os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com'))
    parser.add_argument('--password', default=(os.environ.get('DIRECTUS_PASSWORD') or 'admin'))
    parser.add_argument('--strip-documents', metavar='SECTION',
                        help='drop list items that are only a link already loaded into the '
                             '`documents` collection under this section, so the page does not '
                             'show the same file in the prose and in the list')
    parser.add_argument('--body-start', metavar='REGEX',
                        help='for pages whose text is not in a Drupal/Joomla article body: start '
                             'the extracted region at the first match of this pattern')
    parser.add_argument('--body-end', metavar='REGEX', default=JOOMLA_FOOTER_MARKER,
                        help='end of the region opened by --body-start (default: the page footer)')
    parser.add_argument('--unlink-legacy', action='store_true',
                        help='unwrap links to pages of the old site (keeping their text) so the '
                             'migrated prose does not send visitors back to hnpu.edu.ua')
    parser.add_argument('--keep-images', action='store_true',
                        help='leave image URLs pointing at the old host instead of uploading')
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    transform = load_transform()
    # `2_transform` resolves relative hrefs against hnpu.edu.ua because that is the only host the
    # faculty pipeline ever sees. Pages of the quality centre live on smc.hnpu.edu.ua and their
    # `/files/…` images would 404 against the main host, so resolve against the page's own origin.
    parts = urllib.parse.urlsplit(args.url)
    transform.LEGACY_BASE = f'{parts.scheme}://{parts.netloc}/'

    page = fetch(args.url)
    if args.body_start:
        start = re.search(args.body_start, page, re.S)
        if not start:
            print('! --body-start did not match anything on that page', file=sys.stderr)
            return 1
        end = re.search(args.body_end, page[start.start():], re.S)
        markup = page[start.start():start.start() + end.start()] if end else page[start.start():]
    else:
        body = BODY_RE.search(page) or JOOMLA_BODY_RE.search(page)
        if not body:
            print('! no article body on that page — check the URL, or pass --body-start',
                  file=sys.stderr)
            return 1
        markup = body.group(0)

    title_match = H1_RE.search(page)
    title = ''
    if title_match:
        # The old theme upper-cases headings in CSS, so the markup is mixed — leave the text as
        # authored and only strip tags/entities.
        title = html_lib.unescape(re.sub(r'<[^>]+>', '', title_match.group(1)))
        title = re.sub(r'\s+', ' ', title).strip()

    html, images = transform.clean_body(markup)
    if args.strip_documents:
        html = strip_document_links(html, args.strip_documents)
    if args.unlink_legacy:
        html = unlink_legacy_pages(html)
    print(f'{title!r}: {len(html)} chars, {len(images)} image(s)', file=sys.stderr)

    if args.dry_run:
        print(html[:1500])
        return 0

    if images and not args.keep_images:
        token = args.token or directus_login(args.directus_url, args.email, args.password)
        mapping: dict[str, str] = {}
        for source in dict.fromkeys(images):
            file_id = upload_image(args.directus_url, token, source)
            if file_id:
                mapping[source] = file_id
        # Anything that failed to upload is dropped: an http:// image is blocked as mixed
        # content on the live site anyway.
        def replace(match: re.Match[str]) -> str:
            file_id = mapping.get(match.group(2))
            return f'{match.group(1)}/assets/{file_id}{match.group(3)}' if file_id else ''
        html = IMG_SRC_RE.sub(replace, html)
        print(f'  uploaded {len(mapping)}/{len(set(images))} image(s)', file=sys.stderr)

    payload = {
        'title': title,
        'sections': [{'html': html}],
        'sourceUrls': [args.url],
        'capturedAt': date.today().isoformat(),
    }
    out = Path(args.target) / f'{args.slug}.{args.locale}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'→ {out}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
