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

LEGEND_SOURCE_RE = re.compile(r'<span class="fieldset-legend">(.*?)</span>', re.S)

TOKEN_RE = re.compile(
    r'<legendtext>(?P<legend>.*?)</legendtext>'
    r'|<a\s[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<label>.*?)</a>'
    # Any other tag is skipped explicitly, so that its markup cannot leak into `text` below.
    r'|(?P<tag><[^>]*>)'
    r'|(?P<text>[^<]{3,})',
    re.S)

# Every напрям the page opens a top-level <legend> for. Longer needles first: «ОСВІТНЬО-НАУКОВИХ»
# must win over «ОСВІТНІХ ПРОГРАМ», and the rating results over plain «НАУКОВ».
AREAS = (
    ('РЕЙТИНГОВОГО ОЦІНЮВАННЯ', 'staff-rating'),
    ('ОСВІТНЯ ДІЯЛЬНІСТЬ', 'educational-activity'),
    ('ОСВІТНЬО-НАУКОВИХ ПРОГРАМ', 'phd-programmes'),
    ('РЕАЛІЗАЦІЯ ОСВІТНІХ ПРОГРАМ', 'programme-implementation'),
    ('ОСВІТНЄ СЕРЕДОВИЩЕ', 'educational-environment'),
    ('МІЖНАРОДНЕ СПІВРОБІТНИЦТВО', 'international'),
    ('МОЛОДІЖНА ПОЛІТИКА', 'youth-policy'),
    ('МЕНЕДЖМЕНТ І КАДРОВЕ', 'management'),
    ('СТЕЙКХОЛДЕР', 'stakeholders'),
    ('ЕКСПРЕС-ОПИТУВАННЯ', 'express'),
    ('НАУКОВ', 'research'),
)

SURVEY_RE = re.compile(r'АНКЕТА\s*№\s*([\d]+(?:\s*/\s*\d+)?)', re.I)
# «АНКЕТА № 9» with nothing after it: the name lives in the next link or text fragment.
BARE_HEADING_RE = re.compile(r'АНКЕТА\s*№\s*[\d]+(?:\s*/\s*\d+)?\s*', re.I)
VARIANT_RE = re.compile(r'анкет[аи]\s*№\s*([\d]+\s*/\s*\d+)', re.I)
YEAR_RE = re.compile(r'^(20\d{2})(?:\s*[/-]\s*(20\d{2}))?\s*(?:р\.?|рік)?[.;]?$')
GROUP_RE = re.compile(r'дослідницька група\s*:?\s*(.*)', re.I)

# Links above the first legend: the page's own normative documents.
INTRO_DOCUMENTS_LIMIT = 6


def is_aside(label: str) -> bool:
    """«Програма», «Результати», a year — the rows that belong to a survey, not its name."""
    text = label.strip().lower()
    return (not text
            or text.startswith(('програма', 'результат'))
            or YEAR_RE.match(label.strip()) is not None)


def area_of(legend: str) -> str | None:
    """
    The напрям a <legend> opens, or None for the nested ones («Анкета за ОНП», «Анкета по
    факультетам», «Анкета по кафедрам»): those sit inside a напрям and keep the one in force,
    which is why their surveys used to land in «Інше».
    """
    upper = legend.upper()
    for needle, value in AREAS:
        if needle in upper:
            return value
    return None


# Inline formatting only; the old editor wrapped every other character in <span>, which split
# «АНКЕТА № 27» into the text nodes «АНКЕТА № 2» and «7» — the number was then read as 2 and the
# survey merged into a different one. Structural tags (a, p, div, br, fieldset) stay: the parser
# needs them.
COSMETIC_TAGS_RE = re.compile(r'</?(?:span|strong|em|b|i|u|font|small|sub|sup)\b[^>]*>', re.I)


def region(page: str) -> str:
    start = REGION_START_RE.search(page)
    if not start:
        return page
    end = REGION_END_RE.search(page, start.end())
    return page[start.start():end.start() if end else len(page)]


def normalise_number(raw: str) -> str:
    return re.sub(r'\s+', '', raw)


def merge_duplicates(surveys: list[dict], results: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    A few анкети appear under two напрями (37 under both «Освітня діяльність» and «Реалізація
    освітніх програм»). Keep the first occurrence, fill in whatever it is missing from the later
    ones, and repoint their results at it.
    """
    canonical: dict[str, dict] = {}
    alias: dict[str, str] = {}
    kept: list[dict] = []

    for survey in surveys:
        survey.pop('_needsTitle', None)
        first = canonical.get(survey['number'])
        if first is None:
            canonical[survey['number']] = survey
            kept.append(survey)
            continue
        alias[survey['_ref']] = first['_ref']
        for key in ('researchGroup', 'formUrl', '_file', '_fileField'):
            if not first.get(key) and survey.get(key):
                first[key] = survey[key]
        # The longer heading is the one that kept the survey's full name.
        if len(survey['title']) > len(first['title']):
            first['title'] = survey['title']

    for index, survey in enumerate(kept, start=1):
        survey['order'] = index
    for result in results:
        result['_parent'] = alias.get(result['_parent'], result['_parent'])
    return kept, results


def main() -> int:
    body = LEGEND_SOURCE_RE.sub(r'<legendtext>\1</legendtext>', region(fetch(PAGE)))
    body = COSMETIC_TAGS_RE.sub('', body)

    surveys: list[dict] = []
    results: list[dict] = []
    intro: list[dict] = []
    area: str | None = None
    started = False
    current: dict | None = None

    def open_survey(number: str, title: str, url: str | None) -> dict:
        bare = BARE_HEADING_RE.fullmatch(re.sub(r'\s+', ' ', title).strip()) is not None
        entry: dict = {
            '_ref': f's{len(surveys) + 1}',
            '_needsTitle': bare,
            'number': normalise_number(number),
            'area': area,
            'title': re.sub(r'\s+', ' ', title).strip(),
            'researchGroup': None,
            'formUrl': url if url and not is_file_url(url) else None,
            'order': len(surveys) + 1,
        }
        if url and is_file_url(url):
            entry['_file'] = url
            entry['_fileField'] = 'programmeFile'
        surveys.append(entry)
        return entry

    for match in TOKEN_RE.finditer(body):
        if match.group('tag') is not None:
            continue

        if match.group('legend') is not None:
            opened = area_of(text_of(match.group('legend')))
            started = True
            if opened:
                area = opened
            current = None
            continue

        if match.group('text') is not None:
            text = text_of(match.group('text'))

            # Some headings are plain text rather than a link (анкети 22 and 39): the number sits
            # in a <strong>, and the quoted name follows as text or as the link to the form.
            number = SURVEY_RE.match(text.strip())
            if started and number:
                # With the cosmetic tags gone the whole heading — number, name and «(дослідницька
                # група: …)» — usually arrives as one text node, so split it here.
                head, _, tail = text.partition('(')
                current = open_survey(number.group(1), head, None)
                group = GROUP_RE.search(text)
                if group:
                    current['researchGroup'] = group.group(1).strip(' )').strip() or None
                elif tail:
                    current['researchGroup'] = None
                continue

            if not current:
                continue

            # Continuation of a heading that was cut off before its name. The same fragment
            # often carries the research group after it, so split on that marker first.
            if current.get('_needsTitle'):
                name = GROUP_RE.split(text)[0].strip(' (\u00a0')
                # «(дослідницька група: )» with nothing inside leaves an empty bracket behind.
                name = re.sub(r'\(\s*\)\s*$', '', name).strip(' (\u00a0')
                if name and not is_aside(name):
                    current['title'] = re.sub(r'\s+', ' ', f'{current["title"]} {name}').strip()
                    current['_needsTitle'] = False

            group = GROUP_RE.search(text)
            if group and not current.get('researchGroup'):
                current['researchGroup'] = group.group(1).strip(' )').strip() or None
            continue

        label = text_of(match.group('label'))
        # A few addresses carry a non-breaking space glued to the end, which breaks the link.
        url = absolute(match.group('href').replace('%C2%A0', '').replace('\u00a0', '').strip(), PAGE)
        if not label:
            continue

        # 1. before the first legend — the page's normative documents
        if not started:
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
            current = open_survey(number.group(1), label, url)
            continue

        if not current:
            continue

        # A heading opened from plain text (анкети 9, 20, 39) is completed by the link that carries
        # its name — that link is also the form the survey is filled in.
        if current.get('_needsTitle') and not is_aside(label):
            current['title'] = re.sub(r'\s+', ' ', f'{current["title"]} {label}').strip()
            current['_needsTitle'] = False
            if not current.get('formUrl') and not is_file_url(url):
                current['formUrl'] = url
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

    surveys, results = merge_duplicates(surveys, results)

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
