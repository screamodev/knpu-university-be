#!/usr/bin/env python3
"""
`smc.hnpu.edu.ua/akredytatsiia` → `accreditation_dossiers` + `accreditation_dossier_files`.

The centre's Joomla page groups accreditation dossiers by навчальний рік (an accordion header),
then lists each освітня програма as a bold paragraph followed by a `<ul>` of its НАЗЯВО documents:
відомості про самооцінювання, програма виїзду, звіт експертної групи, експертний висновок ГЕР,
рішення Національного агентства. Entries with no link (plain `<li>` text) are skipped — the old
site never published those files.

    python3 extract_accreditation_dossiers.py
"""

from __future__ import annotations

import re
import sys

from common import DATA, absolute, fetch, is_file_url, text_of, write_json

PAGE = 'http://smc.hnpu.edu.ua/akredytatsiia'

TOKEN_RE = re.compile(
    r'(?P<year>Акредитація\s+\d{4}\s*[-–]\s*\d{4}\s+навчального\s+року)'
    r'|<strong>(?P<programme>(?:(?!</strong>).)*?)</strong>'
    r'|<a\s[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<label>.*?)</a>',
    re.S)

YEAR_RE = re.compile(r'(\d{4})\s*[-–]\s*(\d{4})')
HEADER_RE = re.compile(r'Акредитація\s+\d{4}\s*[-–]\s*\d{4}', re.I)

KINDS = (
    ('самооцінюв', 'self-assessment'),
    ('виїзду', 'visit-program'),
    ('звіт експертної', 'expert-report'),
    ('висновок', 'ger-conclusion'),
    ('рішення', 'naqa-decision'),
)

LEVELS = (
    ('перш', 'bachelor'),
    ('бакалавр', 'bachelor'),
    ('друг', 'master'),
    ('магістер', 'master'),
    ('трет', 'phd'),
    ('доктор філософії', 'phd'),
)


def kind_of(label: str) -> str:
    lowered = label.lower()
    for needle, value in KINDS:
        if needle in lowered:
            return value
    return 'other'


def level_of(title: str) -> str | None:
    lowered = title.lower()
    for needle, value in LEVELS:
        if needle in lowered:
            return value
    return None


def main() -> int:
    page = fetch(PAGE)

    dossiers: list[dict] = []
    files: list[dict] = []
    year: str | None = None
    current: dict | None = None

    for match in TOKEN_RE.finditer(page):
        if match.group('year'):
            found = YEAR_RE.search(match.group('year'))
            year = f'{found.group(1)}-{found.group(2)}' if found else None
            current = None
            continue

        if match.group('programme') is not None:
            title = text_of(match.group('programme'))
            if len(title) < 25 or 'програма' not in title.lower():
                continue
            current = {
                '_ref': f'd{len(dossiers) + 1}',
                'academicYear': year,
                'level': level_of(title),
                'programmeTitle': title,
                'order': len(dossiers) + 1,
            }
            dossiers.append(current)
            continue

        label = text_of(match.group('label'))
        # The year headers are themselves accordion links, so they arrive as anchors.
        if HEADER_RE.search(label):
            found = YEAR_RE.search(label)
            year = f'{found.group(1)}-{found.group(2)}' if found else None
            current = None
            continue

        if not current:
            continue
        url = absolute(match.group('href'), PAGE)
        if not label or not is_file_url(url):
            continue
        files.append({
            '_parent': current['_ref'],
            'kind': kind_of(label),
            'title': label,
            'order': len(files) + 1,
            '_file': url,
        })

    years = sorted({row['academicYear'] for row in dossiers if row['academicYear']})
    print(f'  years: {", ".join(years)}', file=sys.stderr)
    print(f'  dossiers: {len(dossiers)}, documents: {len(files)}', file=sys.stderr)

    write_json(DATA / 'accreditation_dossiers.json', {
        'source': PAGE,
        'batches': [
            {
                'collection': 'accreditation_dossiers',
                'identity': ['academicYear', 'programmeTitle'],
                'rows': dossiers,
            },
            {
                'collection': 'accreditation_dossier_files',
                'identity': ['dossier', 'kind', 'title'],
                'parent': {'field': 'dossier', 'from': '_parent'},
                'rows': files,
            },
        ],
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
