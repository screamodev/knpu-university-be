#!/usr/bin/env python3
"""
Re-host the files still linked from migrated prose, and rewrite the links to `/assets/<uuid>`.

`migrate_page.py` moves images into Directus but leaves `<a href>` alone, so pages that carry an
archive inside their text — the спеціалізовані вчені ради list every dissertation, автореферат and
відгук — would keep pointing at hnpu.edu.ua. This walks the static content files, uploads what
they link to and rewrites the hrefs; the frontend resolves `/assets/<uuid>` against the Directus
public URL when it renders the body.

Idempotent: already-mirrored links (`/assets/…`) are left alone and uploads are cached in
`files.map.json`, so an interrupted run resumes. Files the old site no longer serves are reported
and their links are kept as they are.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 mirror_page_files.py --dry-run
    python3 mirror_page_files.py council-d-64-053-01 --limit 20
    python3 mirror_page_files.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
from pathlib import Path

from common import Directus, download, filename_for, login, present_file_ids, upload

HERE = Path(__file__).parent
# Лише типове значення для `--content`: у контейнері репозиторій часто змонтований неглибоко,
# і `parents[2]` там просто немає — тоді шлях доведеться передати вручну.
CONTENT = ((HERE.parents[2] if len(HERE.parents) > 2 else HERE)
           / 'knpu-university-fe' / 'app' / 'content' / 'pages')
# «Документи», created by snapshots/bootstrap-editor-experience.sh.
DEFAULT_FOLDER = '3e5f21c7-8b04-4d92-a6f1-27c48ab5d301'

# `src` as well as `href`: the quality centre's pages use images from its own host as buttons.
LEGACY_FILE_HREF_RE = re.compile(
    r'(?:href|src)="(?P<url>https?://[^"]*hnpu\.edu\.ua[^"]*\.'
    r'(?:pdf|docx?|xlsx?|pptx?|rtf|odt|zip|jpe?g|png|gif))"', re.I)


def links_of(payload: dict) -> list[str]:
    """Legacy file URLs linked from a static page's sections, in document order, deduplicated."""
    html = ' '.join(section.get('html') or '' for section in payload.get('sections', []))
    return list(dict.fromkeys(LEGACY_FILE_HREF_RE.findall(html)))


def unlink_pages(payload: dict, host: str) -> int:
    """
    Unwrap links to *pages* of a host we are replacing, keeping their text. File links stay —
    those are handled by the mirroring above. Returns how many links were unwrapped.
    """
    pattern = re.compile(
        rf'<a\s[^>]*href="(?P<href>[^"]*{re.escape(host)}[^"]*)"[^>]*>(?P<text>.*?)</a>', re.S)
    count = 0

    def unwrap(match: re.Match[str]) -> str:
        nonlocal count
        if LEGACY_FILE_HREF_RE.search(f'href="{match.group("href")}"') or \
                re.search(r'\.(pdf|docx?|xlsx?|pptx?|rtf|odt|zip|jpe?g|png)(\?|$)',
                          match.group('href').split('#')[0], re.I):
            return match.group(0)
        count += 1
        return match.group('text')

    for section in payload.get('sections', []):
        section['html'] = pattern.sub(unwrap, section.get('html') or '')
    return count


def upload_with_retry(directus: Directus, content: bytes, filename: str, content_type: str,
                      folder: str | None, attempts: int = 6, file_id: str | None = None) -> str:
    """
    Upload, surviving a Directus restart.

    A run of a few thousand files reliably makes the local Directus container restart (PM2 brings
    it back within seconds); without this the whole run died on «Connection refused» and had to be
    resumed by hand. HTTP errors are not retried — those are the server rejecting the file.
    """
    for attempt in range(1, attempts + 1):
        try:
            return upload(directus, content, filename, content_type, filename[:255], folder,
                          file_id=file_id)
        except urllib.error.HTTPError:
            raise
        except OSError as exc:
            if attempt == attempts:
                raise
            pause = min(30, 3 * attempt)
            print(f'    … {exc}; retrying in {pause}s ({attempt}/{attempts - 1})', file=sys.stderr)
            time.sleep(pause)
    raise OSError('unreachable')


def load_map(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def save_map(path: Path, data: dict[str, str]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('slugs', nargs='*', help='content files to process (default: all)')
    parser.add_argument('--content', default=str(CONTENT))
    parser.add_argument('--map', default=str(HERE / 'files.map.json'))
    parser.add_argument('--folder', default=DEFAULT_FOLDER)
    parser.add_argument('--limit', type=int, help='stop after this many uploads')
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--unlink-host', metavar='HOST',
                        help='unwrap links to pages (not files) on this host, keeping their text — '
                             'those pages are replaced by this site')
    parser.add_argument('--unlink-missing', action='store_true',
                        help='for files the old site no longer serves (404), unwrap the link and '
                             'keep its text — a dead link to a dead host helps nobody')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    content = Path(args.content)
    # `rglob` so the same script works on `app/content/structure/<unit>/<tab>.json` too.
    files = [path for path in sorted(content.rglob('*.json')) if path.name != 'manifest.json']
    if args.slugs:
        wanted = set(args.slugs)
        files = [path for path in files if path.name.split('.')[0] in wanted]

    if args.dry_run:
        total = 0
        for path in files:
            urls = links_of(json.loads(path.read_text(encoding='utf-8')))
            if urls:
                print(f'{path.name:<40} {len(urls)} files')
                total += len(urls)
        print(f'\n{total} files would be mirrored')
        return 0

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)
    map_path = Path(args.map)
    uploaded = load_map(map_path)
    # `files.map.json` is committed so a file keeps its uuid everywhere; on a fresh environment
    # those ids do not exist yet, so re-upload them under the same uuid.
    present = present_file_ids(directus, uploaded.values())
    mirrored = failed = 0

    unlinked_pages = 0

    for path in files:
        payload = json.loads(path.read_text(encoding='utf-8'))
        urls = links_of(payload)

        if args.unlink_host:
            count = unlink_pages(payload, args.unlink_host)
            if count:
                unlinked_pages += count
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')
                print(f'  unwrapped {count} page link(s) in {path.name}', file=sys.stderr)

        if not urls:
            continue
        print(f'\n== {path.name}: {len(urls)} files', file=sys.stderr)

        replacements: dict[str, str] = {}
        missing: list[str] = []
        for index, url in enumerate(urls, 1):
            file_id = uploaded.get(url)
            known_id = None
            if file_id and file_id not in present:
                known_id, file_id = file_id, None
            if not file_id:
                if args.limit and mirrored >= args.limit:
                    break
                downloaded = download(url)
                if not downloaded:
                    failed += 1
                    missing.append(url)
                    continue
                content_bytes, content_type = downloaded
                filename = filename_for(url)
                try:
                    file_id = upload_with_retry(directus, content_bytes, filename, content_type,
                                                args.folder, file_id=known_id)
                except urllib.error.HTTPError as exc:
                    print(f'    ! upload {exc.code}: {exc.read().decode("utf-8", "replace")[:200]}',
                          file=sys.stderr)
                    failed += 1
                    continue
                except OSError as exc:
                    print(f'    ! upload gave up: {exc}', file=sys.stderr)
                    failed += 1
                    continue
                uploaded[url] = file_id
                present.add(file_id)
                save_map(map_path, uploaded)
                mirrored += 1
                if mirrored % 10 == 0:
                    print(f'  [{index}/{len(urls)}] {filename[:70]}', file=sys.stderr)
            replacements[url] = file_id

        if replacements or (missing and args.unlink_missing):
            for section in payload.get('sections', []):
                html = section.get('html') or ''
                for url, file_id in replacements.items():
                    html = (html.replace(f'href="{url}"', f'href="/assets/{file_id}"')
                                .replace(f'src="{url}"', f'src="/assets/{file_id}"'))
                if args.unlink_missing:
                    for url in missing:
                        html = re.sub(
                            rf'<a\s[^>]*href="{re.escape(url)}"[^>]*>(.*?)</a>', r'\1', html, flags=re.S)
                        # A picture the old host no longer serves would render as a broken image.
                        html = re.sub(rf'<img\b[^>]*src="{re.escape(url)}"[^>]*/?>', '', html)
                section['html'] = html
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            note = f', unwrapped {len(missing)} dead' if args.unlink_missing and missing else ''
            print(f'  rewrote {len(replacements)} links in {path.name}{note}', file=sys.stderr)

    if args.unlink_host:
        print(f'unwrapped {unlinked_pages} link(s) to {args.unlink_host} pages', file=sys.stderr)
    print(f'\nmirrored={mirrored} failed={failed}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
