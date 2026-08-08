#!/usr/bin/env python3
"""
«Основні напрямки наукової і мистецької діяльності кафедр» (Google Drive PDF) → `science_directions`.

The document is a numbered list of кафедри; under each one, a bulleted напрям with the
supervising professor in brackets:

    1. Анатомії і фізіології людини імені професора Я.Р. Синельникова
       ➢ Фізіологічний стан організму тварин при використанні халатних форм мікроелементів
         (проф. І.А. Іонов)

Needs `pypdf`, so run it with the dependency available:

    docker run --rm --network host -v "$PWD":/work -w /work python:3.12-slim \
      sh -c "pip install --quiet pypdf && python extract_science_directions.py"
"""

from __future__ import annotations

import re
import sys
import urllib.request
from io import BytesIO

from common import BROWSER_HEADERS, DATA, write_json

FILE_ID = '1tpOF1Gfpp8xnx3znyVJt9wAQtMwkx1AM'
SOURCE = f'https://drive.google.com/file/d/{FILE_ID}/view'
DOWNLOAD = f'https://drive.google.com/uc?export=download&id={FILE_ID}'

# The list was typed in Word with a Wingdings bullet, which pypdf surfaces as U+F0D8.
BULLET_CLASS = '[•▪●∙➢]'
DEPARTMENT_RE = re.compile(r'^\s*(\d{1,3})\.\s+(.*)$')
BULLET_RE = re.compile(BULLET_CLASS)
SUPERVISOR_RE = re.compile(
    r'\((?:відповідальн\w*\s*)?([^()]*(?:проф|доц|канд|д-р|викл|аспірант)[^()]*)\)\s*$', re.I)


def pdf_text() -> str:
    from pypdf import PdfReader

    request = urllib.request.Request(DOWNLOAD, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=300) as response:
        raw = response.read()
    reader = PdfReader(BytesIO(raw))
    print(f'  {len(reader.pages)} pages, {len(raw)} bytes', file=sys.stderr)
    return '\n'.join(page.extract_text() or '' for page in reader.pages)


def main() -> int:
    text = pdf_text()

    rows: list[dict] = []
    department_parts: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        department = re.sub(r'\s+', ' ', ' '.join(department_parts)).strip(' .;')
        topic = re.sub(r'\s+', ' ', ' '.join(pending)).strip(' ;.')
        if not department or len(topic) < 8:
            return
        supervisor = SUPERVISOR_RE.search(topic)
        rows.append({
            'department': department,
            'topic': SUPERVISOR_RE.sub('', topic).strip(' ;.,') if supervisor else topic,
            'supervisor': supervisor.group(1).strip() if supervisor else None,
            'order': len(rows) + 1,
        })

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith(('основні напрямки', 'кафедр хнпу')):
            continue

        heading = DEPARTMENT_RE.match(line)
        if heading:
            flush()
            pending = []
            rest = heading.group(2)
            # A heading line often already carries the first напрям after the bullet.
            if BULLET_RE.search(rest):
                name, first = BULLET_RE.split(rest, 1)
                department_parts = [name]
                pending = [first]
            else:
                department_parts = [rest]
            continue

        if BULLET_RE.match(line):
            flush()
            pending = [BULLET_RE.split(line, 1)[1]]
            continue

        if pending:
            pending.append(line)
        elif department_parts:
            # The department name wraps onto the next lines until the first bullet.
            department_parts.append(line)

    flush()

    departments = {row['department'] for row in rows}
    print(f'  departments: {len(departments)}, directions: {len(rows)}, '
          f'{sum(1 for row in rows if row["supervisor"])} with a supervisor', file=sys.stderr)

    write_json(DATA / 'science_directions.json', {
        'source': SOURCE,
        'batches': [{
            'collection': 'science_directions',
            'identity': ['department', 'topic'],
            'rows': rows,
        }],
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
