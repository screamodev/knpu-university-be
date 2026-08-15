#!/usr/bin/env python3
"""
Move already-uploaded files into the folder tree seeded by
`snapshots/bootstrap-editor-experience.sh`.

The client asked for a tree instead of one flat library, and asked whether files that are
already uploaded can be re-foldered. They can: a folder is metadata on the `directus_files`
row, the asset keeps its uuid, so every `/assets/<uuid>` link on the site — including the ones
baked into migrated HTML — keeps working. Nothing here touches storage.

Which folder a file lands in is derived from what points at it: a file attached to a
`documents` row goes to the folder of that row's section, a partner logo goes to Партнери, an
article cover goes to Новини. Files nothing points at are left where they are and listed in
the summary, so an orphan is visible rather than silently swept somewhere.

Usage (local):
    DIRECTUS_URL=http://localhost:8055 DIRECTUS_TOKEN=... python3 organize_files.py --dry-run
    DIRECTUS_URL=http://localhost:8055 DIRECTUS_TOKEN=... python3 organize_files.py

Production runs inside the container network, like every other migration script:
    docker run --rm --network webnet -e DIRECTUS_URL=http://knpu-university-directus:8055 \
      -e DIRECTUS_TOKEN=... -v "$PWD":/w -w /w python:3.12-slim python organize_files.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent.parent

# Ids are fixed in `snapshots/bootstrap-editor-experience.sh` — same folders in every environment.
NEWS = '9f1d4e2a-6c3b-4a51-9e77-1c0b5d2f8a10'
PAPER = '7c2a5b93-4d18-4f60-8a2e-3b6d90f14c55'
DOCS = '3e5f21c7-8b04-4d92-a6f1-27c48ab5d301'
DOCS_ORDERS = 'f725708c-d643-4788-8f7c-cee3e227d89c'
DOCS_UNIVERSITY = '76c96419-c26f-4b55-b408-bcd97e3f4048'
DOCS_EDUCATION = 'aecfd48b-f628-466f-a333-72129edc2646'
DOCS_SCIENCE = '631b3f95-f859-44ca-a0bb-c6471a42e758'
DOCS_ADMISSIONS = 'ebf0ea72-8334-4ed5-a077-2e750e3d5f70'
DOCS_STUDENT = '364fdc41-3819-4c58-b96e-54ad96040bf9'
ARCHIVE = 'edb12c69-89b8-424a-8cdc-7bf1ebebef33'
MEDIA = '0b5192f4-98a7-4431-9cdb-0db67df26c38'
MEDIA_STRUCTURE = '03cbd78e-3aa5-4f2e-8273-f3fecc9a87df'
MEDIA_PARTNERS = '10976a4c-12ce-45de-a53d-064b5c017346'
MEDIA_GALLERY = '6d88cb3a-2123-45c9-a06b-d49d0015b33e'

FOLDER_NAMES = {
    NEWS: 'Новини',
    PAPER: 'Газета «Учитель»',
    DOCS: 'Документи',
    DOCS_ORDERS: 'Документи / Накази з основної діяльності',
    DOCS_UNIVERSITY: 'Документи / Університет',
    DOCS_EDUCATION: 'Документи / Навчання',
    DOCS_SCIENCE: 'Документи / Наука',
    DOCS_ADMISSIONS: 'Документи / Вступ',
    DOCS_STUDENT: 'Документи / Студентство',
    ARCHIVE: 'Архів старого сайту',
    MEDIA: 'Медіа сторінок',
    MEDIA_STRUCTURE: 'Медіа сторінок / Структура підрозділів',
    MEDIA_PARTNERS: 'Медіа сторінок / Партнери',
    MEDIA_GALLERY: 'Медіа сторінок / Галерея',
}

# `documents.section` → folder. Sections are declared in `migration/schema/apply_schema.py` and
# mirrored in the frontend's `app/utils/documentSections.ts`; a section missing here falls back
# to Документи itself, which is where they all sit today.
SECTION_FOLDERS = {
    'rector-report': DOCS_UNIVERSITY,
    'regulations': DOCS_UNIVERSITY,
    'regulation-drafts': DOCS_UNIVERSITY,
    'facilities': DOCS_UNIVERSITY,
    'vacancies': DOCS_UNIVERSITY,
    'attestation': DOCS_UNIVERSITY,
    'procurement-info': DOCS_UNIVERSITY,
    'financial-activity': DOCS_UNIVERSITY,
    'licenses': DOCS_UNIVERSITY,
    'awards': DOCS_UNIVERSITY,
    'contacts': DOCS_UNIVERSITY,
    'inclusive-support': DOCS_UNIVERSITY,
    'academic-office': DOCS_EDUCATION,
    'education-schedule': DOCS_EDUCATION,
    'quality-centre': DOCS_EDUCATION,
    'quality-centre-programmes': DOCS_EDUCATION,
    'digital-center': DOCS_EDUCATION,
    'monitoring': DOCS_EDUCATION,
    'scientific-secretary': DOCS_SCIENCE,
    'specialized-councils': DOCS_SCIENCE,
    'science-schools': DOCS_SCIENCE,
    'postgraduate-regulations': DOCS_SCIENCE,
    'admissions-committee': DOCS_ADMISSIONS,
    'student-council': DOCS_STUDENT,
}

# (collection, field, folder). Order matters: the first rule that claims a file wins, so the
# specific collections come before the catch-all imagery.
SIMPLE_RULES = [
    ('university_orders', 'documentFile', DOCS_ORDERS),
    ('contingent_reports', 'file', DOCS_EDUCATION),
    ('student_schedule_documents', 'file', DOCS_EDUCATION),
    ('monitoring_surveys', 'programmeFile', DOCS_EDUCATION),
    ('monitoring_survey_results', 'file', DOCS_EDUCATION),
    ('accreditation_certificates', 'file', DOCS_EDUCATION),
    ('accreditation_dossier_files', 'file', DOCS_EDUCATION),
    ('dissertation_council_files', 'file', DOCS_SCIENCE),
    ('science_schools', 'file', DOCS_SCIENCE),
    ('admission_exam_programs', 'programmeFile', DOCS_ADMISSIONS),
    ('newspaper_issues', 'pdfFile', PAPER),
    ('newspaper_issues', 'cover', PAPER),
    ('partners', 'logo', MEDIA_PARTNERS),
    ('gallery_items', 'image', MEDIA_GALLERY),
    ('articles', 'cover', NEWS),
    ('articles_files', 'directus_files_id', NEWS),
    ('events', 'cover', MEDIA),
    ('programmes', 'cover', MEDIA),
    ('memorial_entries', 'photo', MEDIA),
    ('student_council_members', 'photo', MEDIA),
    # A legacy redirect usually points at a file another collection already claimed. What is left
    # keeps an old hnpu.edu.ua address alive without belonging to a page, so it goes to the archive
    # rather than into the folders editors work in.
    ('legacy_redirects', 'file', ARCHIVE),
]

# Images of the migrated faculty/кафедра pages live inside static JSON in the frontend, so no
# collection points at them — the migration's own map is the only reference.
IMAGE_MAPS = [
    (REPO / 'migration' / 'structure-pages' / 'images.map.json', MEDIA_STRUCTURE),
    (REPO / 'migration' / 'pages' / 'images.map.json', MEDIA),
]

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': 'application/json',
}


class Directus:
    """Minimal REST client — stdlib only, browser headers so Cloudflare does not answer 1010."""

    def __init__(self, base: str, token: str):
        self.base = base.rstrip('/')
        self.token = token

    def request(self, method: str, path: str, payload=None):
        headers = dict(BROWSER_HEADERS, Authorization=f'Bearer {self.token}')
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(f'{self.base}{path}', data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=300) as response:
            body = response.read()
        return json.loads(body)['data'] if body else None

    def get(self, path: str):
        return self.request('GET', path)


def login(base: str, email: str, password: str) -> str:
    request = urllib.request.Request(
        f'{base.rstrip("/")}/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode(),
        headers=dict(BROWSER_HEADERS, **{'Content-Type': 'application/json'}), method='POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())['data']['access_token']


def rows(client: Directus, collection: str, field: str) -> list[dict]:
    """Every row of `collection` that has a file in `field`, id only."""
    query = urllib.parse.urlencode({
        'fields': f'{field},section' if collection == 'documents' else field,
        'filter': json.dumps({field: {'_nnull': True}}),
        'limit': -1,
    })
    try:
        return client.get(f'/items/{collection}?{query}') or []
    except urllib.error.HTTPError as error:
        # A collection that does not exist in this environment is not a reason to stop.
        if error.code in (403, 404):
            print(f'  ! {collection}.{field}: {error.code}, skipped', file=sys.stderr)
            return []
        raise


def file_id(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get('id')
    return None


def plan(client: Directus) -> tuple[dict[str, str], dict[str, int]]:
    """file id → target folder id, plus a per-folder count for the summary."""
    target: dict[str, str] = {}

    def claim(fid: str | None, folder: str) -> None:
        if fid and fid not in target:
            target[fid] = folder

    for row in rows(client, 'documents', 'file'):
        claim(file_id(row.get('file')), SECTION_FOLDERS.get(row.get('section'), DOCS))

    for collection, field, folder in SIMPLE_RULES:
        for row in rows(client, collection, field):
            claim(file_id(row.get(field)), folder)

    for path, folder in IMAGE_MAPS:
        if not path.exists():
            continue
        mapping = json.loads(path.read_text(encoding='utf-8'))
        for value in mapping.values():
            claim(file_id(value) if not isinstance(value, str) else value, folder)

    counts: dict[str, int] = {}
    for folder in target.values():
        counts[folder] = counts.get(folder, 0) + 1
    return target, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL', 'http://localhost:8055'))
    parser.add_argument('--token', default=os.environ.get('DIRECTUS_TOKEN'))
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL'))
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD'))
    parser.add_argument('--dry-run', action='store_true', help='print the plan, change nothing')
    parser.add_argument('--limit', type=int, default=0, help='move at most N files (trial run)')
    parser.add_argument('--batch', type=int, default=100, help='files per PATCH request')
    args = parser.parse_args()

    token = args.token or (login(args.directus_url, args.email, args.password)
                           if args.email and args.password else None)
    if not token:
        parser.error('DIRECTUS_TOKEN, or DIRECTUS_EMAIL + DIRECTUS_PASSWORD, is required')

    client = Directus(args.directus_url, token)

    total = client.get('/files?aggregate[count]=id')
    total_files = int(total[0]['count']['id']) if total else 0

    target, counts = plan(client)

    print(f'files in library: {total_files}')
    for folder, count in sorted(counts.items(), key=lambda item: -item[1]):
        print(f'  {count:>5}  {FOLDER_NAMES.get(folder, folder)}')
    print(f'  {total_files - len(target):>5}  (unmatched — left where they are)')

    # Only files that are not already in the right folder need a write.
    current = {}
    for row in client.get('/files?fields=id,folder&limit=-1') or []:
        current[row['id']] = row.get('folder')
    moves = [(fid, folder) for fid, folder in target.items()
             if fid in current and current[fid] != folder]
    if args.limit:
        moves = moves[:args.limit]

    print(f'to move: {len(moves)}')
    if args.dry_run or not moves:
        return 0

    by_folder: dict[str, list[str]] = {}
    for fid, folder in moves:
        by_folder.setdefault(folder, []).append(fid)

    moved = 0
    failed = 0
    for folder, ids in by_folder.items():
        for start in range(0, len(ids), args.batch):
            chunk = ids[start:start + args.batch]
            try:
                client.request('PATCH', '/files', {'keys': chunk, 'data': {'folder': folder}})
                moved += len(chunk)
            except urllib.error.HTTPError as error:
                failed += len(chunk)
                print(f'  ! {FOLDER_NAMES.get(folder, folder)}: {error.code} {error.read()[:200]!r}',
                      file=sys.stderr)
        print(f'  moved {len(ids):>5} → {FOLDER_NAMES.get(folder, folder)}')

    print(f'done: {moved} moved, {failed} failed')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
