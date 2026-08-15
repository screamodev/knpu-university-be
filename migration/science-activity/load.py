#!/usr/bin/env python3
"""
Документи Наукової ради та наукових заходів → колекція `documents`.

Пункт 13 списку зауважень від 17.08.2026. Джерела — дві сторінки старого сайту:

  • https://hnpu.edu.ua/uk/division/naukova-rada — положення, склад і плани засідань 2018–2025;
  • https://hnpu.edu.ua/uk/division/naukova-ta-naukovo-tehnichna-diyalnist-hnpu-imeni-gs-skovorody
    — плани наукових заходів.

Самі файли лежать двома способами: PDF на старому сайті (беремо через архів, бо оригінал уже не
віддається) і Google Drive (беремо `uc?export=download`). Кожен файл вантажимо з явним UUID —
і карта `files.map.json` тримає відповідність, щоб на будь-якому середовищі /assets/<uuid> був той
самий.

    DIRECTUS_URL=http://localhost:8055 DIRECTUS_TOKEN=... python3 load.py --dry-run
    DIRECTUS_URL=http://localhost:8055 DIRECTUS_TOKEN=... python3 load.py
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as uuid_mod
from pathlib import Path

HERE = Path(__file__).parent
MAP_PATH = HERE / 'files.map.json'

# Тека «Документи / Наука» — фіксований id зі snapshots/bootstrap-editor-experience.sh.
FOLDER_ID = '631b3f95-f859-44ca-a0bb-c6471a42e758'

ARCHIVE = 'https://web.archive.org/web/2024id_/'

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': '*/*',
}

# (section, title, url, filename)
DOCUMENTS = [
    ('science-council', 'Положення про Наукову раду',
     'https://hnpu.edu.ua/sites/default/files/files/Normat_dokum/Piojenn/Naykova_Rada.pdf',
     'polozhennia-pro-naukovu-radu.pdf'),
    ('science-council', 'Склад Наукової ради',
     'https://drive.google.com/uc?export=download&id=1UJqGs07nVdS-hhg7zWiaiDgxhRCFXh7W',
     'sklad-naukovoi-rady.pdf'),
    ('science-council', 'План засідань Наукової ради 2024–2025 рр.',
     'https://drive.google.com/uc?export=download&id=1fKapV952G_RYcuCOz0_URveD96NLpk6Q',
     'plan-zasidan-2024-2025.pdf'),
    ('science-council', 'План засідань Наукової ради 2023–2024 рр.',
     'https://drive.google.com/uc?export=download&id=1NUNrbxZhroTILR9VOpECtnn9qgRl4Koc',
     'plan-zasidan-2023-2024.pdf'),
    ('science-council', 'План засідань Наукової ради 2022–2023 рр.',
     'https://drive.google.com/uc?export=download&id=1LxqiFX7QSf-qdm3nYptCuLnjcW9CVGEO',
     'plan-zasidan-2022-2023.pdf'),
    ('science-council', 'План засідань Наукової ради 2021–2022 рр.',
     'https://hnpu.edu.ua/sites/default/files/files/Naukova_rada/Plan%20zasidan21-22.pdf',
     'plan-zasidan-2021-2022.pdf'),
    ('science-council', 'План засідань Наукової ради 2020–2021 рр.',
     'https://hnpu.edu.ua/sites/default/files/files/Naukova_rada/plan-2020-2021.pdf',
     'plan-zasidan-2020-2021.pdf'),
    ('science-council', 'План засідань Наукової ради 2019–2020 рр.',
     'https://hnpu.edu.ua/sites/default/files/files/Naukova_rada/plan-2019-2020.pdf',
     'plan-zasidan-2019-2020.pdf'),
    ('science-council', 'План засідань Наукової ради 2018–2019 рр.',
     'https://hnpu.edu.ua/sites/default/files/files/Naukova_rada/plan-2018-2019.pdf',
     'plan-zasidan-2018-2019.pdf'),
    ('science-events', 'Порядок реалізації права на академічну мобільність',
     'https://hnpu.edu.ua/sites/default/files/files/Nauka/Por_mobilnocti.pdf',
     'poriadok-akademichnoi-mobilnosti.pdf'),
    ('science-events', 'План заходів, присвячених Дню науки в Україні у 2024 році',
     'https://docs.google.com/document/d/1_ERmcLqugqKObWQAlB_KziW28C3WejEB/export?format=pdf',
     'plan-den-nauky-2024.pdf'),
    ('science-events', 'План проведення наукових заходів, присвячених 220-річчю ХНПУ імені Г. С. Сковороди',
     'https://drive.google.com/uc?export=download&id=1bueSJzmyY-X2yeXrk210I0BqgcKheWev',
     'plan-220-richchia.pdf'),
]


class Directus:
    def __init__(self, base: str, token: str):
        self.base = base.rstrip('/')
        self.token = token

    def request(self, method: str, path: str, payload=None, raw: bytes | None = None,
                content_type: str | None = None):
        headers = dict(BROWSER_HEADERS, Authorization=f'Bearer {self.token}')
        data = raw
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        if content_type:
            headers['Content-Type'] = content_type
        request = urllib.request.Request(f'{self.base}{path}', data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=600) as response:
            body = response.read()
        return json.loads(body)['data'] if body else None

    def get(self, path: str):
        return self.request('GET', path)

    def upload(self, file_id: str, filename: str, title: str, blob: bytes) -> str:
        """Multipart upload з явним id — той самий файл матиме той самий uuid скрізь."""
        boundary = '----knpu' + uuid_mod.uuid4().hex
        mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        parts: list[bytes] = []
        for name, value in (('id', file_id), ('folder', FOLDER_ID), ('title', title)):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f'Content-Type: {mime}\r\n\r\n'.encode())
        parts.append(blob)
        parts.append(f'\r\n--{boundary}--\r\n'.encode())
        data = self.request('POST', '/files', raw=b''.join(parts),
                            content_type=f'multipart/form-data; boundary={boundary}')
        return data['id']


def login(base: str, email: str, password: str) -> str:
    request = urllib.request.Request(
        f'{base.rstrip("/")}/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode(),
        headers=dict(BROWSER_HEADERS, **{'Content-Type': 'application/json'}), method='POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())['data']['access_token']


def looks_like_document(blob: bytes) -> bool:
    """Старий хост і Drive віддають HTML-сторінку з кодом 200, коли файлу немає."""
    return len(blob) > 2048 and (blob[:4] == b'%PDF' or blob[:2] == b'PK')


def download(url: str) -> bytes:
    """PDF зі старого сайту вже не віддається напряму — для нього йдемо в архів."""
    candidates = [url]
    if 'hnpu.edu.ua' in url:
        candidates.append(ARCHIVE + url)
    # Для більших файлів Drive спершу віддає сторінку-попередження; прямий хост із confirm=t
    # обходить її.
    drive_id = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('id', [None])[0]
    if drive_id:
        candidates.append(
            f'https://drive.usercontent.google.com/download?id={drive_id}&export=download&confirm=t')

    last: Exception | None = None
    for candidate in candidates:
        try:
            request = urllib.request.Request(candidate, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(request, timeout=300) as response:
                blob = response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            last = error
            continue
        if looks_like_document(blob):
            return blob
        last = RuntimeError(f'{candidate}: {len(blob)} байтів, не схоже на документ')
    raise RuntimeError(str(last))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL', 'http://localhost:8055'))
    parser.add_argument('--token', default=os.environ.get('DIRECTUS_TOKEN'))
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL'))
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or (login(args.directus_url, args.email, args.password)
                           if args.email and args.password else None)
    if not token:
        parser.error('потрібен DIRECTUS_TOKEN або DIRECTUS_EMAIL + DIRECTUS_PASSWORD')

    client = Directus(args.directus_url, token)
    files_map: dict[str, str] = json.loads(MAP_PATH.read_text(encoding='utf-8')) if MAP_PATH.exists() else {}

    query = urllib.parse.urlencode({'fields': 'id,section,title', 'limit': -1,
                                    'filter': json.dumps({'section': {'_in': ['science-council', 'science-events']}})})
    existing = {(row['section'], row['title']) for row in (client.get(f'/items/documents?{query}') or [])}

    todo = [row for row in DOCUMENTS if (row[0], row[1]) not in existing]
    print(f'{len(DOCUMENTS)} документів, {len(existing)} уже в базі, {len(todo)} до створення')
    if args.dry_run or not todo:
        return 0

    present = set()
    for chunk_start in range(0, len(files_map), 50):
        ids = list(files_map.values())[chunk_start:chunk_start + 50]
        query = urllib.parse.urlencode({'fields': 'id', 'limit': -1,
                                        'filter': json.dumps({'id': {'_in': ids}})})
        present |= {row['id'] for row in (client.get(f'/files?{query}') or [])}

    created = failed = 0
    for order, (section, title, url, filename) in enumerate(todo, start=1):
        try:
            file_id = files_map.get(url) or str(uuid_mod.uuid4())
            if file_id not in present:
                blob = download(url)
                file_id = client.upload(file_id, filename, title, blob)
                files_map[url] = file_id
                MAP_PATH.write_text(json.dumps(files_map, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            client.request('POST', '/items/documents', {
                'status': 'published',
                'section': section,
                'title': title,
                'file': file_id,
                'order': order,
            })
            created += 1
            print(f'  + {section}: {title}')
        except Exception as error:  # noqa: BLE001 — один поганий файл не має валити решту
            failed += 1
            print(f'  ! {title}: {error}', file=sys.stderr)
        time.sleep(0.05)

    print(f'створено {created}, помилок {failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
