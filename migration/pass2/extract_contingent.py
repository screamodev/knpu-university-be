#!/usr/bin/env python3
"""
`/uk/division/kontyngent` → `contingent_reports`.

The page is a flat list of monthly PDFs, one per form of study:
«Контингент здобувачів освіти денної форми навчання станом на 01.08.2026». Both the form of
study and the date live in the link text; the academic year comes from the file path
(`…/Vidd_navch/25_26/…`), falling back to the date when the path says nothing.

    python3 extract_contingent.py
"""

from __future__ import annotations

import re
import sys

from common import DATA, absolute, fetch, is_file_url, links_of, write_json

PAGE = 'https://hnpu.edu.ua/uk/division/kontyngent'

DATE_RE = re.compile(r'\b(\d{2})\.(\d{2})\.(\d{4})\b')
YEAR_DIR_RE = re.compile(r'/(\d{2})_(\d{2})/')

FORMS = (('денн', 'full-time'), ('заочн', 'part-time'))


def form_of(title: str) -> str | None:
    lowered = title.lower()
    for needle, value in FORMS:
        if needle in lowered:
            return value
    return None


def academic_year(url: str, date: str | None) -> str | None:
    match = YEAR_DIR_RE.search(url)
    if match:
        return f'20{match.group(1)}-20{match.group(2)}'
    if not date:
        return None
    year, month = int(date[:4]), int(date[5:7])
    # The academic year starts in September.
    start = year if month >= 9 else year - 1
    return f'{start}-{start + 1}'


def main() -> int:
    rows: list[dict] = []
    seen: set[str] = set()

    for title, url in links_of(fetch(PAGE), PAGE):
        if not title or not is_file_url(url) or url in seen:
            continue
        form = form_of(title)
        if not form:
            continue
        seen.add(url)

        match = DATE_RE.search(title)
        date = f'{match.group(3)}-{match.group(2)}-{match.group(1)}' if match else None
        rows.append({
            'academicYear': academic_year(url, date),
            'formOfStudy': form,
            'reportDate': date,
            'title': title,
            'order': len(rows) + 1,
            '_file': absolute(url, PAGE),
        })

    years = sorted({row['academicYear'] for row in rows if row['academicYear']})
    print(f'  academic years: {", ".join(years)}', file=sys.stderr)
    print(f'  undated: {sum(1 for row in rows if not row["reportDate"])}', file=sys.stderr)

    write_json(DATA / 'contingent.json', {
        'source': PAGE,
        'batches': [{
            'collection': 'contingent_reports',
            'identity': ['title'],
            'rows': rows,
        }],
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
