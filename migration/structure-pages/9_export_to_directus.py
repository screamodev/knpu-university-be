#!/usr/bin/env python3
"""
Перекласти вкладки підрозділу зі статичного контенту фронту в колекцію `structure_pages`.

Тіла вкладок лежать у `knpu-university-fe/app/content/structure/<unit>/<tab>.<locale>.json` і
потрапляють у бандл — виправити там кому може лише розробник зі складанням образу. Скрипт
переносить їх у Directus, звідки те саме читає редактор.

Переносимо **підрозділами**, а не все одразу: статичний JSON лишається на місці й працює
запасним варіантом, поки для вкладки немає рядка в базі. Тому міграція оборотна — досить
видалити рядки, і сайт повернеться до мігрованого тексту.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 9_export_to_directus.py kafedra-horeografiyi          # → data/structure-pages.json
    python3 ../pass2/load.py data/structure-pages.json --dry-run
    python3 ../pass2/load.py data/structure-pages.json

`load.py` пропускає рядки, які вже є на цілі (звірка за `unit_slug` + `tab`), тож повторний
прогін не затре те, що редактор устиг написати.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_OUT = HERE / 'data' / 'structure-pages.json'


def default_content_dir() -> Path:
    """
    Тека зі статичним контентом фронту — сусідній репозиторій.

    Кроку потрібні обидва репозиторії поруч, тож це команда для машини розробника. У
    контейнері на сервері змонтована сама `migration/`, і шлях просто не збереться — тому
    результат експорту закомічено (`data/structure-pages.json`), а на проді запускають
    одразу `pass2/load.py`.
    """
    root = HERE.parent.parent.parent
    return root / 'knpu-university-fe' / 'app' / 'content' / 'structure'

# Вкладки, тіло яких — проза: те саме, що в `STRUCTURE_TABS` у migration/schema/apply_schema.py.
# «Структура», «Новини», «Оголошення» й «Нормативні документи» малюються з інших джерел, і рядок
# для них ніде б не показався.
PROSE_TABS = {'home', 'admission', 'history', 'education', 'science', 'students',
              'cooperation', 'doctoral'}


def section_html(section: dict) -> str:
    """
    Одна секція мігрованого JSON у вигляді HTML, який редактор побачить у WYSIWYG.

    Заголовок секції переїжджає в тіло як `<h2>`: у базі одне поле тексту на вкладку, а не
    список секцій, — редактор пише сторінку так само, як пише новину. Секцію, що на старому
    сайті була `[collapse]`, загортаємо у `<details>`: у контенті підрозділів таких немає, але
    в `app/content/pages` їх сотні, і конвертер знадобиться тим самим.
    """
    body = (section.get('html') or '').strip()
    heading = (section.get('heading') or '').strip()

    if section.get('collapsible'):
        inner = '\n'.join(
            [body] + [section_html(child) for child in section.get('children') or []]
        ).strip()
        return f'<details>\n<summary>{html.escape(heading)}</summary>\n{inner}\n</details>'

    parts = []
    if heading:
        parts.append(f'<h2>{html.escape(heading)}</h2>')
    if body:
        parts.append(body)
    for child in section.get('children') or []:
        parts.append(section_html(child))
    return '\n'.join(parts)


def tab_body(content: dict) -> str:
    return '\n'.join(filter(None, (section_html(section) for section in content.get('sections') or []))).strip()


def unit_rows(content: Path, slug: str) -> list[dict]:
    """
    Рядки для одного підрозділу: по одному на вкладку, з тілом уk і, якщо є, en.

    Файл із блоком `people` зупиняє експорт: картки керівництва живуть окремим полем у JSON і
    тут ще не мають куди переїхати. Мовчки втратити деканат гірше, ніж не мігрувати підрозділ.
    """
    directory = content / slug
    if not directory.is_dir():
        raise SystemExit(f'{slug}: немає теки {directory}')

    bodies: dict[str, dict[str, str]] = {}
    for path in sorted(directory.glob('*.json')):
        tab, _, locale = path.stem.partition('.')
        if tab not in PROSE_TABS:
            print(f'  · {path.name}: вкладка не текстова, пропускаю', file=sys.stderr)
            continue
        content = json.loads(path.read_text(encoding='utf-8'))

        for index, section in enumerate(content.get('sections') or []):
            if section.get('people'):
                raise SystemExit(
                    f'{slug}/{path.name}: секція {index} має блок people ({len(section["people"])} '
                    'осіб). Картки керівництва ще не переносяться — мігруйте інший підрозділ або '
                    'спершу зробіть для них колекцію.')

        body = tab_body(content)
        if not body:
            print(f'  · {path.name}: порожнє тіло, пропускаю', file=sys.stderr)
            continue
        bodies.setdefault(tab, {})[locale or 'uk'] = body

        if content.get('links'):
            print(f'  · {path.name}: {len(content["links"])} посилань лишаються у статиці',
                  file=sys.stderr)

    rows = []
    for tab in sorted(bodies):
        row = {'unit_slug': slug, 'tab': tab, 'status': 'published', 'body': bodies[tab].get('uk', '')}
        if bodies[tab].get('en'):
            row['bodyEn'] = bodies[tab]['en']
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('units', nargs='+', help='слаги підрозділів, напр. kafedra-horeografiyi')
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    parser.add_argument('--content', default=os.environ.get('STRUCTURE_CONTENT_DIR'),
                        help='тека app/content/structure фронту (типово — сусідній репозиторій)')
    args = parser.parse_args()

    content = Path(args.content) if args.content else default_content_dir()
    if not content.is_dir():
        raise SystemExit(
            f'немає теки зі статичним контентом: {content}\n'
            'Крок потребує репозиторію knpu-university-fe поруч — це команда для машини '
            'розробника. На сервері запускайте одразу pass2/load.py: результат експорту вже '
            'закомічено в data/structure-pages.json.')

    rows: list[dict] = []
    for slug in args.units:
        print(f'{slug}:', file=sys.stderr)
        unit = unit_rows(content, slug)
        for row in unit:
            print(f'  + {row["tab"]}: {len(row["body"])} символів'
                  + (f' (+en {len(row["bodyEn"])})' if 'bodyEn' in row else ''), file=sys.stderr)
        rows.extend(unit)

    if not rows:
        raise SystemExit('нічого експортувати')

    payload = {'batches': [{
        'collection': 'structure_pages',
        'identity': ['unit_slug', 'tab'],
        'rows': rows,
    }]}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{out}: {len(rows)} рядків', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
