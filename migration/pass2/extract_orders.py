#!/usr/bin/env python3
"""
`/uk/nakazy-z-osnovnoyi-diyalnosti-universytetu` → `university_orders`.

The page lists ~134 накази з основної діяльності grouped by year, each link titled
«Наказ № 89-од вiд 25 травня 2026 року "Про оголошення конкурсу…"». Number, date and subject all
live in that one string, so they are parsed out into separate fields; the subject in quotes
becomes `title`, and the whole label is kept when a link has no quoted subject.

Two quirks of the old site are handled: scanned orders were typed with Latin look-alike letters
(«вiд» with a Latin i), and a few entries are JPEGs rather than PDFs.

    python3 extract_orders.py
"""

from __future__ import annotations

import re
import sys

from common import DATA, absolute, fetch, is_file_url, links_of, write_json

PAGE = 'https://hnpu.edu.ua/uk/nakazy-z-osnovnoyi-diyalnosti-universytetu'

# Scanned orders were typed with Latin look-alikes in place of Cyrillic letters.
LATIN_LOOKALIKES = str.maketrans({'i': 'і', 'I': 'І', 'e': 'е', 'a': 'а', 'o': 'о',
                                  'c': 'с', 'p': 'р', 'y': 'у', 'x': 'х'})

MONTHS = {
    'січня': 1, 'лютого': 2, 'березня': 3, 'квітня': 4, 'травня': 5, 'червня': 6,
    'липня': 7, 'серпня': 8, 'вересня': 9, 'жовтня': 10, 'листопада': 11, 'грудня': 12,
}

CYRILLIC = re.compile(r'[а-яіїєґА-ЯІЇЄҐ]')
LOOKALIKE_IN_WORD_RE = re.compile(r'(?<=[а-яіїєґА-ЯІЇЄҐ])([iIeaocpyx])|([iIeaocpyx])(?=[а-яіїєґА-ЯІЇЄҐ])')

NUMBER_RE = re.compile(r'Наказ\s*№?\s*([\d]+(?:\s*[-–]?\s*од)?)', re.I)
DATE_WORDS_RE = re.compile(r'\b(\d{1,2})\s+([а-яіїєґ]+)\s+(\d{4})\b', re.I)
DATE_DOTTED_RE = re.compile(r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b')
YEAR_RE = re.compile(r'\b(20\d{2})\b')
SUBJECT_RE = re.compile(r'[«"]\s*(.+?)\s*[»"]\s*$')


def fix_lookalikes(text: str) -> str:
    """
    Repair Latin letters typed inside Cyrillic words («замiщення» with a Latin i).

    Only letters that sit next to a Cyrillic one are touched, so genuinely Latin words in a title
    (Erasmus+, AMUSE, MOODLE) survive. Repeated until stable, because a run of them («органiзацii»)
    exposes the next letter to a Cyrillic neighbour only after the previous one is repaired.
    """
    for _ in range(8):
        repaired = LOOKALIKE_IN_WORD_RE.sub(
            lambda match: (match.group(1) or match.group(2)).translate(LATIN_LOOKALIKES), text)
        if repaired == text:
            return text
        text = repaired
    return text


def parse_date(label: str) -> str | None:
    normalised = label.translate(LATIN_LOOKALIKES)

    match = DATE_WORDS_RE.search(normalised)
    if match:
        month = MONTHS.get(match.group(2).lower())
        if month:
            return f'{int(match.group(3)):04d}-{month:02d}-{int(match.group(1)):02d}'

    match = DATE_DOTTED_RE.search(label)
    if match:
        return f'{int(match.group(3)):04d}-{int(match.group(2)):02d}-{int(match.group(1)):02d}'
    return None


def parse_number(label: str) -> str | None:
    match = NUMBER_RE.search(label.translate(LATIN_LOOKALIKES))
    if not match:
        return None
    number = re.sub(r'\s+', '', match.group(1)).replace('–', '-')
    # «25од» and «25-од» are the same order number, written two ways on the legacy page.
    return re.sub(r'(?<=\d)(од)$', r'-\1', number)


def main() -> int:
    rows: list[dict] = []
    seen: set[str] = set()

    for label, url in links_of(fetch(PAGE), PAGE):
        if not label or not is_file_url(url) or url in seen:
            continue
        seen.add(url)

        date = parse_date(label)
        year = int(date[:4]) if date else None
        if year is None:
            found = YEAR_RE.search(label)
            year = int(found.group(1)) if found else None

        subject = SUBJECT_RE.search(label)
        rows.append({
            'orderNumber': parse_number(label),
            'orderDate': date,
            'year': year,
            # The quoted part is the order's subject; without it, keep the whole label.
            'title': fix_lookalikes(subject.group(1) if subject else label)[:255],
            'order': len(rows) + 1,
            '_file': absolute(url, PAGE),
            '_fileField': 'documentFile',
        })

    years = sorted({row['year'] for row in rows if row['year']})
    print(f'  orders: {len(rows)}, years {years[0]}–{years[-1]}', file=sys.stderr)
    print(f'  without a number: {sum(1 for row in rows if not row["orderNumber"])}, '
          f'without a date: {sum(1 for row in rows if not row["orderDate"])}', file=sys.stderr)

    write_json(DATA / 'orders.json', {
        'source': PAGE,
        'batches': [{
            'collection': 'university_orders',
            'identity': ['title', 'orderDate'],
            'rows': rows,
        }],
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
