#!/usr/bin/env python3
"""
Витягнути реєстр договорів про співпрацю з п’яти Google-документів старого сайту.

Сторінка https://hnpu.edu.ua/uk/ugody-pro-spivpracyu-hnpu-imeni-gs-skovorody — це п’ять покликань
на Google-документи, у кожному таблиця: № · дата укладання · сторони і предмет · термін дії
(у міжнародних ще й країна). Документи відкриті, тож беремо їх експортом у .docx і читаємо
`word/document.xml` — стандартною бібліотекою, без залежностей.

Назва кожного договору в реєстрі — гіперпокликання на його файл (переважно PDF на старому сайті,
подекуди Google Drive). Адресу кладемо в `sourceUrl`; `3_mirror.py` переносить такі файли до нас і
підмінює адресу на `/assets/<uuid>`, щоб покликання пережило вимкнення старого сайту.

Результат — `data/agreements.json`, який вантажить `2_load.py`.

    python3 1_extract.py            # звантажити й розібрати
    python3 1_extract.py --keep     # лишити .docx у .cache/ для перевірки
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).parent
CACHE = HERE / '.cache'
DATA = HERE / 'data'

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PKG_REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept': '*/*',
}

# category → Google Doc id, у порядку покликань на старій сторінці.
SOURCES = [
    ('napn', '13Ps8wUT2t0MDeLnQcZWJQUlFaVDv6ajI'),
    ('universities', '11VpdrTpERg3TNPVVSrQ6cFIpv9GmA4UK'),
    ('schools', '1AVAb6XDZ5yJP8F7WvDryefA1R1EnxDnT'),
    ('organizations', '1nYhspdepkJND77tt9aWF_nKESIbeO17N'),
    ('international', '1Cq1Dk_NUbpmL24siq8eDi0LU0c-RZNay'),
]

HEADER_WORDS = ('№', 'дата укладання', 'сторони', 'термін дії', 'країна')

# Підпис гіперпокликання на файл договору. Сам підпис у тексті предмета зайвий — адресу
# зберігаємо окремим полем, а назва договору стає покликанням на неї.
DROP_LINES = {'інформація про заклад'}


def download(doc_id: str) -> Path:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f'{doc_id}.docx'
    if path.exists():
        return path
    url = f'https://docs.google.com/document/d/{doc_id}/export?format=docx'
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read()
    if len(body) < 2048 or not body.startswith(b'PK'):
        raise SystemExit(f'{doc_id}: не схоже на .docx ({len(body)} байтів) — документ закрили?')
    path.write_bytes(body)
    return path


def cell_lines(cell) -> list[str]:
    """Абзаци клітинки окремими рядками — предмет договору там списком."""
    lines = []
    for paragraph in cell.iter(W + 'p'):
        text = ''.join(node.text or '' for node in paragraph.iter(W + 't'))
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            lines.append(text)
    return lines


def external_targets(path: Path) -> dict[str, str]:
    """`rId…` → адреса, для гіперпокликань документа."""
    root = ET.fromstring(zipfile.ZipFile(path).read('word/_rels/document.xml.rels'))
    return {rel.get('Id'): rel.get('Target')
            for rel in root.iter(PKG_REL + 'Relationship')
            if rel.get('TargetMode') == 'External' and rel.get('Target')}


def cell_link(cell, targets: dict[str, str]) -> str:
    """Перше гіперпокликання клітинки — у реєстрі це файл самого договору."""
    for link in cell.iter(W + 'hyperlink'):
        target = targets.get(link.get(R + 'id'))
        if target:
            return target
    return ''


def is_header(cells: list[list[str]]) -> bool:
    joined = ' '.join(' '.join(cell) for cell in cells).lower()
    return sum(word in joined for word in HEADER_WORDS) >= 2


def year_of(value: str) -> int | None:
    match = re.search(r'(19|20)\d{2}', value)
    return int(match.group(0)) if match else None


def rows_of(path: Path, category: str) -> list[dict]:
    root = ET.fromstring(zipfile.ZipFile(path).read('word/document.xml'))
    targets = external_targets(path)
    international = category == 'international'
    result: list[dict] = []
    order = 0

    for table in root.iter(W + 'tbl'):
        for row in table.findall(W + 'tr'):
            columns = row.findall(W + 'tc')
            cells = [cell_lines(cell) for cell in columns]
            if len(cells) < 4 or is_header(cells):
                continue

            number = ' '.join(cells[0]).strip().rstrip('.')
            date = ' '.join(cells[1]).strip()
            party = cells[2]
            if not party or not (number or date):
                continue

            # Перший абзац — сторона, решта — вид документа й предмет.
            partner = party[0]
            subject = '\n'.join(line for line in party[1:]
                                if line.lower().strip(' .') not in DROP_LINES).strip()

            # Покликання може стояти й на номері, і на назві сторони — беремо перше, що є.
            source_url = cell_link(columns[2], targets) or cell_link(columns[0], targets)

            country = ' '.join(cells[3]).strip() if international else ''
            term = ' '.join(cells[4 if international else 3]).strip() if len(cells) > (4 if international else 3) else ''

            order += 1
            result.append({
                'category': category,
                'number': number[:16],
                'agreementDate': date[:64],
                'year': year_of(date),
                'partner': partner[:500],
                'subject': subject,
                'country': country[:255],
                'term': term[:255],
                'sourceUrl': source_url,
                'order': order,
                'status': 'published',
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--keep', action='store_true', help='не прибирати .docx з .cache/')
    args = parser.parse_args()

    everything: list[dict] = []
    for category, doc_id in SOURCES:
        path = download(doc_id)
        rows = rows_of(path, category)
        print(f'{category:<14} {len(rows):>4} рядків', file=sys.stderr)
        everything.extend(rows)
        if not args.keep:
            path.unlink(missing_ok=True)

    DATA.mkdir(exist_ok=True)
    target = DATA / 'agreements.json'
    target.write_text(json.dumps(everything, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'→ {target.name}: {len(everything)} рядків', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
