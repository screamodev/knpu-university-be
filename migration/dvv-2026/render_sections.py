#!/usr/bin/env python3
"""
Зібрати блок «2026/2028 навчальний рік» у тексті сторінки «Здобувачу».

Сторінка `/education/free-choice/master` показує зріз мігрованої сторінки
`quality-centre-students` — від заголовка «Перелік дисциплін вільного вибору здобувачів
другого (магістерського)» і до розкладу. Клієнт просив покласти над наявним
«2025/2026 навчальний рік» такий самий блок за 2026/2028 з двох списків, що
розкриваються. Скрипт переписує саме ці чотири секції, лишаючи решту сторінки як є.

    python3 render_sections.py            # оновити app/content/pages/quality-centre-students.uk.json
    python3 render_sections.py --stdout   # тільки показати, що вийде
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

HERE = Path(__file__).parent
CONTENT = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'pages' / 'quality-centre-students.uk.json'

ANCHOR = 'Перелік дисциплін вільного вибору здобувачів  другого (магістерського)'
YEAR = '2026/2028 навчальний рік'
CYCLES = [('general', 'Цикл загальної підготовки'), ('prof', 'Цикл професійної підготовки')]


def cycle_html(disciplines: list[dict], by_name: dict[str, str]) -> str:
    """
    Та сама розмітка, що й у списках попередніх років: назва дисципліни веде на її опис,
    кафедра в дужках — на презентацію.
    """
    lines = []
    for item in disciplines:
        lines.append('<p><a href="/assets/%s"><strong>%s</strong></a></p>'
                     % (by_name[item['text']], html.escape(item['name'])))
        lines.append('<p><a href="/assets/%s"><em>%s</em></a></p>'
                     % (by_name[item['presentation']], html.escape(item['department'])))
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--stdout', action='store_true')
    args = parser.parse_args()

    files = json.loads((HERE / 'files.map.json').read_text(encoding='utf-8'))
    by_name = {meta['name']: file_id for file_id, meta in files.items()}
    disciplines = json.loads((HERE / 'disciplines.json').read_text(encoding='utf-8'))

    page = json.loads(CONTENT.read_text(encoding='utf-8'))
    sections = page['sections']
    start = next(i for i, s in enumerate(sections) if (s.get('heading') or '').startswith(ANCHOR))

    # Другий прогін має переписати те, що зробив перший, а не вкласти блок ще раз: після
    # першого в секції-якорі стоїть заголовок 2026/2028, а h3 попереднього року — четвертою.
    rewriting = YEAR in (sections[start].get('html') or '')
    width = 4 if rewriting else 1
    previous_year_html = sections[start + 3]['html'] if rewriting else sections[start]['html']

    rebuilt = [{
        'heading': sections[start]['heading'],
        'html': f'<h3 style="text-align: center">{YEAR}</h3>',
    }]
    for cycle, title in CYCLES:
        rebuilt.append({
            'heading': title,
            'collapsible': True,
            'html': cycle_html([d for d in disciplines if d['cycle'] == cycle], by_name),
        })
    rebuilt.append({'heading': None, 'html': previous_year_html})

    if args.stdout:
        for section in rebuilt:
            print('---', repr(section.get('heading')), section.get('collapsible'))
            print(section['html'][:400])
        return 0

    sections[start:start + width] = rebuilt
    CONTENT.write_text(json.dumps(page, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{CONTENT}: секції {start}–{start + len(rebuilt) - 1} оновлено')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
