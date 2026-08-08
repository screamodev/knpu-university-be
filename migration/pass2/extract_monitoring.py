#!/usr/bin/env python3
"""
`/uk/monitoryng` → `monitoring_surveys` + `monitoring_survey_results` (+ the page's intro documents).

The legacy page is a single Drupal body with one collapsible `<legend>` per напрям діяльності and,
inside it, a repeating shape:

    АНКЕТА №2 "Ідеальний викладач очима студентів"   → link to the Google form
    (дослідницька група: …)
    Програма                                         → PDF
    Результати: 2018; 2019; … 2025                   → one PDF (or Drive link) per year

Anchors whose label carries «(анкета № 22/1)» are per-programme variants and become surveys of
their own, keeping the parent's напрям.

    python3 extract_monitoring.py
"""

from __future__ import annotations

import re
import sys

from common import DATA, absolute, fetch, is_file_url, text_of, write_json

PAGE = 'https://hnpu.edu.ua/uk/monitoryng'

# The body regex in common.py stops at the first closing triple </div>; this page needs the whole
# content region, from the body field down to the end of the collapsible form.
REGION_START_RE = re.compile(r'<div class="field field-name-body')
REGION_END_RE = re.compile(r'<div class="region region-footer|<footer|</form>\s*</div>\s*</div>\s*$')

TOKEN_RE = re.compile(
    r'<span class="fieldset-legend">(?P<legend>.*?)</span>'
    r'|<a\s[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<label>.*?)</a>'
    r'|(?P<text>[^<]{3,})',
    re.S)

AREAS = (
    ('ОСВІТНЯ ДІЯЛЬНІСТЬ', 'educational-activity'),
    ('РЕАЛІЗАЦІЯ ОСВІТНІХ ПРОГРАМ', 'programme-implementation'),
    ('ОСВІТНЬО-НАУКОВИХ ПРОГРАМ', 'phd-programmes'),
    ('ОСВІТНЄ СЕРЕДОВИЩЕ', 'educational-environment'),
    ('НАУКОВ', 'research'),
)

SURVEY_RE = re.compile(r'АНКЕТА\s*№\s*([\d]+(?:\s*/\s*\d+)?)', re.I)
VARIANT_RE = re.compile(r'анкет[аи]\s*№\s*([\d]+\s*/\s*\d+)', re.I)
YEAR_RE = re.compile(r'^(20\d{2})(?:\s*[/-]\s*(20\d{2}))?\s*(?:р\.?|рік)?[.;]?$')
GROUP_RE = re.compile(r'дослідницька група\s*:?\s*(.*)', re.I)

# Links above the first legend: the page's own normative documents.
INTRO_DOCUMENTS_LIMIT = 6


def area_of(legend: str) -> str:
    upper = legend.upper()
    for needle, value in AREAS:
        if needle in upper:
            return value
    return 'other'


def region(page: str) -> str:
    start = REGION_START_RE.search(page)
    if not start:
        return page
    end = REGION_END_RE.search(page, start.end())
    return page[start.start():end.start() if end else len(page)]


def normalise_number(raw: str) -> str:
    return re.sub(r'\s+', '', raw)


def main() -> int:
    body = region(fetch(PAGE))

    surveys: list[dict] = []
    results: list[dict] = []
    intro: list[dict] = []
    area: str | None = None
    current: dict | None = None

    for match in TOKEN_RE.finditer(body):
        if match.group('legend') is not None:
            area = area_of(text_of(match.group('legend')))
            current = None
            continue

        if match.group('text') is not None:
            if not current:
                continue
            group = GROUP_RE.search(text_of(match.group('text')))
            if group and not current.get('researchGroup'):
                current['researchGroup'] = group.group(1).strip(' )').strip() or None
            continue

        label = text_of(match.group('label'))
        url = absolute(match.group('href'), PAGE)
        if not label:
            continue

        # 1. before the first legend — the page's normative documents
        if area is None:
            if is_file_url(url) and len(intro) < INTRO_DOCUMENTS_LIMIT:
                intro.append({
                    'section': 'monitoring',
                    'title': label,
                    'order': len(intro) + 1,
                    '_file': url,
                })
            continue

        # 2. a survey heading (main or per-programme variant)
        # The old markup often splits «АНКЕТА № 37» and its quoted name into two <a> tags
        # pointing at the same form; stitch them back into one title.
        if current and current.get('formUrl') == url and '"' not in current['title']:
            current['title'] = f'{current["title"]} {label}'.strip()
            continue

        number = SURVEY_RE.search(label) or VARIANT_RE.search(label)
        if number and ('анкет' in label.lower()):
            title = re.sub(r'\s+', ' ', label).strip()
            current = {
                '_ref': f's{len(surveys) + 1}',
                'number': normalise_number(number.group(1)),
                'area': area,
                'title': title,
                'researchGroup': None,
                'formUrl': url if not is_file_url(url) else None,
                'order': len(surveys) + 1,
            }
            if is_file_url(url):
                current['_file'] = url
                current['_fileField'] = 'programmeFile'
            surveys.append(current)
            continue

        if not current:
            continue

        # 3. the survey's programme PDF
        if label.lower().startswith('програма'):
            if is_file_url(url) and not current.get('_file'):
                current['_file'] = url
                current['_fileField'] = 'programmeFile'
            continue

        # 4. a per-year result, or a single undated «Результати» link
        year = YEAR_RE.match(label.strip())
        if year or label.lower().startswith('результат'):
            entry = {
                '_parent': current['_ref'],
                'year': (f'{year.group(1)}/{year.group(2)}' if year and year.group(2)
                         else year.group(1) if year else None),
                'order': len(results) + 1,
            }
            if is_file_url(url):
                entry['_file'] = url
            else:
                entry['externalUrl'] = url
            results.append(entry)

    print(f'  intro documents: {len(intro)}', file=sys.stderr)
    print(f'  surveys: {len(surveys)} ({len([s for s in surveys if s.get("_file")])} with a programme PDF)',
          file=sys.stderr)
    print(f'  results: {len(results)}', file=sys.stderr)

    write_json(DATA / 'monitoring.json', {
        'source': PAGE,
        'batches': [
            {'collection': 'documents', 'identity': ['section', 'title'], 'rows': intro},
            {'collection': 'monitoring_surveys', 'identity': ['number', 'title'], 'rows': surveys},
            {
                'collection': 'monitoring_survey_results',
                'identity': ['survey', 'year', 'order'],
                'parent': {'field': 'survey', 'from': '_parent'},
                'rows': results,
            },
        ],
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
