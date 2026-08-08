#!/usr/bin/env python3
"""
Read every defense page listed by `1_extract_list.py` and build the Directus payload.

Each page carries the council composition, the documents submitted for the defense and the
schedule. The body is cleaned with the same `structure-pages/2_transform.py` cleaner the other
migrations use, so the markup matches the rest of the site; the `<a href>` links still point at
hnpu.edu.ua at this stage — `3_rewrite_bodies.py` swaps them for `/assets/<uuid>` after the load.

    docker run --rm --network host -v "$(pwd)/..":/work -w /work/razovi-rady \
      python:3.12-slim python 2_extract_pages.py

→ data/councils.json (pass-2 envelope, load it with ../pass2/load.py)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

from shared import (
    DATA,
    body_of,
    fetch,
    legacy_file_url,
    legacy_path_of,
    parse_ukrainian_date,
    text_of,
    unescape,
    write_json,
)

HERE = Path(__file__).parent
STRUCTURE_PAGES = HERE.parent / 'structure-pages'

H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S)
LINK_RE = re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
STRONG_PARAGRAPH_RE = re.compile(r'<p\b[^>]*>\s*<strong>(.*?)</strong>\s*</p>', re.S)
COUNCIL_CODE_RE = re.compile(r'ДФ\s*([\d]{2,3}[\d.]*\d)')
CANDIDATE_FROM_TITLE_RE = re.compile(r'захист[ау]?\s+дисертації\s+(.+)$', re.I)
HEADING_RE = re.compile(
    r':\s*$|склад\s|голова\s+ради|рецензент|опонент|секретар|документи\s+до\s+захисту', re.I)
BRANCH_RE = re.compile(r'галуз[іи]\s+знань\s+([^,<.\n]{3,80}?)\s*(?:,|за\s+спеціальн|$)', re.I | re.M)
SPECIALTY_RE = re.compile(r'за\s+спеціальністю\s+([^<.\n]{3,90})', re.I)
DEFENSE_DATE_RE = re.compile(r'Дата\s+захисту\s*:?\s*([^<\n]{4,60})', re.I)
DEFENSE_TIME_RE = re.compile(r'Час\s+[Зз]ахисту\s*:?\s*(\d{1,2})[:.\s]*(\d{2})', re.I)
STREAM_RE = re.compile(r'https?://[^\s"\'<>]*(?:zoom\.us|meet\.google\.com)[^\s"\'<>]*', re.I)
DRIVE_RE = re.compile(r'^https?://(?:drive|docs)\.google\.com/', re.I)

# Link label → document kind. Checked before the filename, because the labels are explicit
# wherever the old site bothered to write them out.
LABEL_KINDS = [
    ('відеозапис', 'video'), ('аудіозапис', 'video'),
    ('рішення', 'decision'),
    ('наукового керівника', 'supervisor'),
    ('опонент', 'opponent'), ('відгук', 'opponent'),
    ('рецензі', 'review'),
    ('наукову новизну', 'conclusion'), ('висновок', 'conclusion'), ('фахов', 'conclusion'),
    ('автореферат', 'other'),
    ('дисертаці', 'dissertation'),
]
# Filename prefix → kind. Опоненти й рецензенти підписують посилання прізвищем, тому для них
# ім'я файлу — єдина ознака; за десять років накопичилося чимало варіантів транслітерації.
FILENAME_KINDS = [
    ('rishen', 'decision'),
    ('nauk_ker', 'supervisor'), ('nauker', 'supervisor'), ('naukker', 'supervisor'),
    ('anot', 'other'), ('avtoref', 'other'),
    ('retsenz', 'review'), ('resenz', 'review'), ('retsez', 'review'), ('rets', 'review'),
    ('retz', 'review'), ('recenz', 'review'), ('rec_', 'review'),
    ('oponent', 'opponent'), ('oponet', 'opponent'), ('opon', 'opponent'), ('op_', 'opponent'),
    ('vidhuk', 'opponent'), ('vidguk', 'opponent'), ('vidgyk', 'opponent'),
    ('vigguk', 'opponent'), ('vidgul', 'opponent'), ('vidg', 'opponent'),
    ('dyser', 'dissertation'), ('disert', 'dissertation'), ('dis', 'dissertation'),
    ('fakh', 'conclusion'), ('vysnov', 'conclusion'), ('vysn', 'conclusion'),
]


def block_text(clean_html: str) -> str:
    """
    Body text with block boundaries kept as line breaks.

    Flattening the whole body into one string lets `за спеціальністю …` run on into the next
    paragraph, because the legacy markup rarely ends a paragraph with a full stop.
    """
    blocks = re.split(r'</(?:p|li|h[2-6]|td|th|blockquote)>', clean_html)
    return '\n'.join(line for line in (text_of(block) for block in blocks) if line)


def load_transform():
    """Import `2_transform.py` by path — its name is not a valid module identifier."""
    spec = importlib.util.spec_from_file_location('legacy_transform', STRUCTURE_PAGES / '2_transform.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kind_of(label: str, legacy_path: str | None) -> str:
    lowered = label.lower()
    for needle, kind in LABEL_KINDS:
        if needle in lowered:
            return kind
    filename = (legacy_path or '').rsplit('/', 1)[-1].lower().lstrip('_ 0123456789')
    for prefix, kind in FILENAME_KINDS:
        if filename.startswith(prefix):
            return kind
    return 'other'


def council_fields(title: str, body_text: str) -> dict:
    code = COUNCIL_CODE_RE.search(title) or COUNCIL_CODE_RE.search(body_text)
    branch = BRANCH_RE.search(body_text)
    specialty = SPECIALTY_RE.search(body_text)
    return {
        'councilCode': f'ДФ {code.group(1)}' if code else None,
        'branch': branch.group(1).strip() if branch else None,
        'specialty': specialty.group(1).strip() if specialty else None,
    }


def candidate_from_title(title: str) -> str:
    match = CANDIDATE_FROM_TITLE_RE.search(title)
    value = match.group(1) if match else re.split(r'\s+[–—-]\s+', title)[-1]
    return re.sub(r'\s*\([^)]*\)\s*$', '', value).strip() or title


def candidate_and_topic(title: str, clean_html: str) -> tuple[str, str | None]:
    """The candidate and the dissertation topic — bold paragraphs first, page title as fallback."""
    bold = [text_of(match) for match in STRONG_PARAGRAPH_RE.findall(clean_html)]
    # Some pages bold their section headings too; those are never a name or a topic.
    bold = [value for value in bold if value and not HEADING_RE.search(value)]

    candidate = next((value for value in bold[:3] if 3 < len(value) <= 80), None)
    if not candidate:
        candidate = candidate_from_title(title)
    topic = next((value for value in bold[:4] if len(value) > 40 and value != candidate), None)
    return candidate[:255], topic


def year_of(defense_date: str | None, entry: dict, code: str | None) -> int | None:
    if defense_date:
        return int(defense_date[:4])
    if entry.get('year'):
        return entry['year']
    # «ДФ 011.143.25» — the last pair is the year the council was formed.
    match = re.search(r'\.(\d{2})$', code or '')
    return 2000 + int(match.group(1)) if match else None


def extract(entry: dict, transform) -> tuple[dict, list[dict]]:
    page = fetch(entry['url'])
    raw_body = body_of(page)
    clean_html, _images = transform.clean_body(raw_body)

    title_match = H1_RE.search(page)
    title = text_of(title_match.group(1)) if title_match else entry['label']
    body_text = block_text(clean_html)

    fields = council_fields(title, body_text)
    candidate, topic = candidate_and_topic(title, clean_html)

    date_match = DEFENSE_DATE_RE.search(body_text)
    defense_date = parse_ukrainian_date(date_match.group(1) if date_match else '') or entry.get('listDate')
    time_match = DEFENSE_TIME_RE.search(body_text)
    stream = STREAM_RE.search(raw_body)

    council = {
        '_ref': entry['slug'],
        'legacySlug': entry['slug'],
        'legacyUrl': entry['url'],
        'candidateName': candidate,
        'dissertationTitle': topic,
        'defenseDate': defense_date,
        'defenseTime': f'{int(time_match.group(1)):02d}:{time_match.group(2)}' if time_match else None,
        'year': year_of(defense_date, entry, fields['councilCode']),
        'contentHtml': clean_html,
        'streamUrl': stream.group(0) if stream else None,
        **fields,
    }

    files: list[dict] = []
    seen: set[str] = set()
    for href, label_markup in LINK_RE.findall(raw_body):
        url = unescape(href).strip()
        label = text_of(label_markup)
        legacy_path = legacy_path_of(url)

        if legacy_path:
            if legacy_path in seen:
                continue
            seen.add(legacy_path)
            files.append({
                '_parent': entry['slug'],
                # Normalised, so the same file linked from two pages uploads once.
                '_file': legacy_file_url(legacy_path),
                'legacyPath': legacy_path,
                'title': label or legacy_path.rsplit('/', 1)[-1],
                'kind': kind_of(label, legacy_path),
                'order': len(files) + 1,
            })
            continue

        # Google Drive holds the qualified-signature copies. «(КЕП)» next to a document we already
        # have is noise; a link with a real caption (the signed video recording) is not.
        if DRIVE_RE.match(url) and len(label) > 15 and url not in seen:
            seen.add(url)
            files.append({
                '_parent': entry['slug'],
                'externalUrl': url,
                'title': label,
                'kind': kind_of(label, None),
                'order': len(files) + 1,
            })

    return council, files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--limit', type=int, help='process only the first N pages')
    parser.add_argument('--index', default=str(DATA / 'index.json'))
    args = parser.parse_args()

    entries = json.loads(Path(args.index).read_text(encoding='utf-8'))
    if args.limit:
        entries = entries[:args.limit]

    transform = load_transform()
    transform.LEGACY_BASE = 'https://hnpu.edu.ua/'

    councils: list[dict] = []
    files: list[dict] = []
    for index, entry in enumerate(entries, 1):
        try:
            council, page_files = extract(entry, transform)
        except Exception as exc:  # noqa: BLE001 — one broken page must not stop 262 others
            print(f'  ! {entry["slug"]}: {exc}', file=sys.stderr)
            continue
        council['order'] = index
        councils.append(council)
        files.extend(page_files)
        if index % 25 == 0:
            print(f'  [{index}/{len(entries)}] {council["candidateName"][:50]}', file=sys.stderr)

    missing_date = [row['legacySlug'] for row in councils if not row['defenseDate']]
    no_files = [row['legacySlug'] for row in councils if not any(
        item['_parent'] == row['legacySlug'] for item in files)]
    print(f'\ncouncils={len(councils)} files={len(files)} '
          f'without_date={len(missing_date)} without_files={len(no_files)}', file=sys.stderr)
    if missing_date:
        print(f'  no defense date: {", ".join(missing_date[:5])}', file=sys.stderr)
    if no_files:
        print(f'  no documents:    {", ".join(no_files[:5])}', file=sys.stderr)

    write_json(DATA / 'councils.json', {
        'batches': [
            {
                'collection': 'dissertation_councils',
                'identity': ['legacySlug'],
                'rows': councils,
            },
            {
                'collection': 'dissertation_council_files',
                'identity': ['council', 'order'],
                'parent': {'field': 'council', 'from': '_parent'},
                'rows': files,
            },
        ],
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
