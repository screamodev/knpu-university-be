#!/usr/bin/env python3
"""
`/uk/sertyfikaty-pro-akredytaciyu` → `accreditation_certificates`.

The legacy page is one long Drupal body: a collapsible `<legend>` per освітній рівень, a bold
«Галузь знань …» line per branch, and one `<a>` per certificate (JPG or PDF). Walking the markup
in document order is enough to attach each certificate to the level and branch above it.

    python3 extract_accreditation_certificates.py
"""

from __future__ import annotations

import re
import sys

from common import DATA, LINK_RE, absolute, body_of, fetch, is_file_url, text_of, write_json

PAGE = 'https://hnpu.edu.ua/uk/sertyfikaty-pro-akredytaciyu'

LEGEND_RE = re.compile(r'<span class="fieldset-legend">(.*?)</span>', re.S)
BRANCH_RE = re.compile(r'<strong>((?:(?!</strong>).)*?Галузь знань.*?)</strong>', re.S)
TOKEN_RE = re.compile(
    r'<span class="fieldset-legend">(?P<legend>.*?)</span>'
    r'|<strong>(?P<strong>(?:(?!</strong>).)*?)</strong>'
    r'|<a\s[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<label>.*?)</a>',
    re.S)

LEVELS = (
    ('бакалавр', 'bachelor'),
    ('магістер', 'master'),
    ('освітньо-науков', 'phd'),
    ('третій', 'phd'),
)

CODE_RE = re.compile(r'\b(\d{3})\b')


def level_of(legend: str) -> str | None:
    lowered = legend.lower()
    for needle, value in LEVELS:
        if needle in lowered:
            return value
    return None


def main() -> int:
    body = body_of(fetch(PAGE))

    level: str | None = None
    branch: str | None = None
    rows: list[dict] = []

    for match in TOKEN_RE.finditer(body):
        if match.group('legend') is not None:
            found = level_of(text_of(match.group('legend')))
            if found:
                level, branch = found, None
            continue

        if match.group('strong') is not None:
            label = text_of(match.group('strong'))
            if 'Галузь знань' in label:
                branch = label.replace('Галузь знань', '').strip(' :')
            continue

        title = text_of(match.group('label'))
        url = absolute(match.group('href'), PAGE)
        if not title or not level or not is_file_url(url):
            continue

        # The old markup splits one title across several <a> tags pointing at the same file.
        if rows and rows[-1]['_file'] == url:
            joiner = '' if title[:1].islower() or title[:1] in '"«' else ' '
            rows[-1]['title'] = (rows[-1]['title'] + joiner + title).strip()
            continue

        code = CODE_RE.search(title)
        rows.append({
            'level': level,
            'branch': branch,
            'specialtyCode': code.group(1) if code else None,
            'title': title,
            'order': len(rows) + 1,
            '_file': url,
        })

    for level_id in ('bachelor', 'master', 'phd'):
        print(f'  {level_id}: {sum(1 for row in rows if row["level"] == level_id)}', file=sys.stderr)

    write_json(DATA / 'accreditation_certificates.json', {
        'source': PAGE,
        'batches': [{
            'collection': 'accreditation_certificates',
            'identity': ['level', 'title'],
            'rows': rows,
        }],
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
