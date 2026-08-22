#!/usr/bin/env python3
"""
Правки підрозділів зі списку зауважень від 17.08.2026 (пункти 9, 12, 13).

Сторінки структури емітує `structure-pages/4_emit.py` із дампа старого сайту, тож правити
згенерований JSON руками не можна — наступний прогін етапу 4 їх зітре. Цей скрипт грає ту саму
роль, що й `7_fix_overtagged.py` та `8_fix_unit_content.py`: він докладає до вже емітованого
контенту те, що надіслав клієнт, і його можна запустити повторно після кожного нового прогону.

Що робить:

* **Факультет історії і права** — нове фото декана й посилання на її персональний сайт;
* **Кафедра хореографії** — новий текст головної, наукової діяльності та вкладки «Вступнику»,
  оновлений склад кафедри, телефони та посада завідувачки;
* **Факультет математики, інформатики і природничої освіти** — нові тексти головної, «Вступнику»,
  «Освіта», «Історія» (з галереєю історичних світлин) і «Співпраця», деканат, контакти.

Тексти лежать поруч у `html/` — це конвертовані `docx`/`doc`, які надіслали підрозділи
(див. `../docx_to_html.py`); зображення заливає `../../drive-assets/push_assets.py`, тут вони
шукаються за іменем файла у `files.map.json`.

    python3 apply.py --dry-run
    python3 apply.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
HTML = HERE / 'html'
FILES_MAP = HERE.parents[1] / 'drive-assets' / 'files.map.json'
CONTENT = HERE.parents[3] / 'knpu-university-fe' / 'app' / 'content' / 'structure'

ZELENSKA_SITE = 'https://sites.google.com/hnpu.edu.ua/lyudmyla-zelenska'

#: Викладачі, яких кафедра хореографії просила прибрати зі складу.
CHOREOGRAPHY_REMOVED = ('Лиманська', 'Нікітенко', 'Яворівська', 'Нос ')

#: Деканат ФМІПО: фото у теці Drive підписані прізвищами.
FMIPO_DEANERY = [
    ('fmipo-ponomarova.jpg', 'Декан', 'Пономарьова Наталія Олександрівна',
     'доктор педагогічних наук, професор, професор кафедри інформатики',
     'https://sites.google.com/hnpu.edu.ua/ponomarova/'),
    ('fmipo-prostakova.jpg', 'Заступник декана з навчальної роботи', 'Простакова Юлія Сергіївна',
     'кандидат педагогічних наук, доцент кафедри математики',
     'https://sites.google.com/hnpu.edu.ua/prostakova'),
    ('fmipo-gaidus.jpg', 'Координатор з наукової роботи', 'Гайдусь Андрій Юрійович',
     'кандидат технічних наук, доцент, доцент кафедри інформатики',
     'https://sites.google.com/hnpu.edu.ua/gaidus/'),
    ('fmipo-gulich.jpg', 'Координатор з виховної роботи', 'Гуліч Олена Олександрівна',
     'кандидат педагогічних наук, доцент, доцент кафедри теорії і практики англійської мови '
     'та зарубіжної літератури імені професора Михайла Гетманця',
     'https://sites.google.com/hnpu.edu.ua/kaf-tpel/%D1%81%D0%BF%D1%96%D0%B2%D1%80%D0%BE%D0%B1%D1%96%D1%82%D0%BD%D0%B8%D0%BA%D0%B8-staff/%D0%B3%D1%83%D0%BB%D1%96%D1%87-%D0%BE-%D0%BE'),
    ('fmipo-dumchikova.jpg', 'Секретар деканату', 'Думчикова Ольга Федорівна', None,
     'https://sites.google.com/view/dumchikova/%D0%B3%D0%BE%D0%BB%D0%BE%D0%B2%D0%BD%D0%B0-%D1%81%D1%82%D0%BE%D1%80%D1%96%D0%BD%D0%BA%D0%B0'),
    ('fmipo-bartosh.jpg', 'Секретар деканату', 'Бартош Ольга Іванівна', None,
     'https://sites.google.com/view/bartosh-olha/%D0%B3%D0%BE%D0%BB%D0%BE%D0%B2%D0%BD%D0%B0-%D1%81%D1%82%D0%BE%D1%80%D1%96%D0%BD%D0%BA%D0%B0'),
]

#: Світлина біля пам'ятника Сковороді — єдина, яку клієнт лишив на вкладці «Вступнику».
FMIPO_MONUMENT_PHOTO = '/assets/a6bb147c-50c3-4bb5-b54d-2f5e64567d6f'


def assets() -> dict[str, str]:
    """Ім'я файла → id, під яким він лежить у Directus."""
    return {name: file_id for file_id, name in json.loads(FILES_MAP.read_text(encoding='utf-8')).items()}


def body(name: str) -> str:
    return HTML.joinpath(f'{name}.html').read_text(encoding='utf-8').strip()


class Editor:
    """Збирає зміни і показує, які файли реально змінилися."""

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.touched: list[str] = []

    def edit(self, relative: str, change) -> None:
        path = CONTENT / relative
        data = json.loads(path.read_text(encoding='utf-8'))
        before = json.dumps(data, ensure_ascii=False, sort_keys=True)
        change(data)
        after = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if before == after:
            return
        self.touched.append(relative)
        if self.dry_run:
            return
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def history_law(editor: Editor, files: dict[str, str]) -> None:
    photo = f'/assets/{files["zelenska.jpg"]}'

    def home(data):
        for section in data['sections']:
            for person in section.get('people') or []:
                if person['name'].endswith('Зеленська'):
                    person['photo'] = photo
                    person['profileUrl'] = ZELENSKA_SITE

    editor.edit('history-law/home.uk.json', home)


def choreography(editor: Editor, files: dict[str, str]) -> None:
    yefimova_photo = f'/assets/{files["yefimova.jpg"]}'

    def home(data):
        sections = data['sections']
        main = next(section for section in sections if section.get('heading') == 'Головна')
        # Аудіоопис кафедри лишається перед текстом — це єдиний матеріал сторінки для
        # незрячих відвідувачів.
        audio = re.match(r'\s*<p><a href="[^"]+"><strong>Людям з порушеннями зору[^<]*</strong></a></p>',
                         main['html'])
        main['html'] = ((audio.group(0).strip() + '\n') if audio else '') + body('horeografiyi-home')

        staff = next(section for section in sections if section.get('heading') == 'Співробітники')
        html = staff['html']
        for surname in CHOREOGRAPHY_REMOVED:
            html = re.sub(r'<figure>(?:(?!</figure>).)*?' + surname + r'(?:(?!</figure>).)*?</figure>',
                          '', html, flags=re.S)
        html = re.sub(r'<img src="/assets/[0-9a-f-]+"( loading="lazy")? />(?=<figcaption><a href="[^"]*yefimova)',
                      f'<img src="{yefimova_photo}" loading="lazy" />', html)
        staff['html'] = html

    editor.edit('kafedra-horeografiyi/home.uk.json', home)
    editor.edit('kafedra-horeografiyi/science.uk.json',
                lambda data: data.__setitem__('sections', [{'html': body('horeografiyi-science')}]))
    editor.edit('kafedra-horeografiyi/admission.uk.json',
                lambda data: data.__setitem__('sections', [{'html': body('horeografiyi-admission')}]))


def fmipo(editor: Editor, files: dict[str, str]) -> None:
    people = [
        {
            'photo': f'/assets/{files[photo]}',
            'position': position,
            'name': name,
            'degree': degree,
            'profileUrl': url,
        }
        for photo, position, name, degree, url in FMIPO_DEANERY
    ]

    def home(data):
        data['sections'] = [{
            'html': body('fmipo-home'),
            'peopleHeading': 'Деканат',
            'people': people,
        }]

    def admission(data):
        data['sections'] = [{
            'html': body('fmipo-admission')
            + f'\n<p><img src="{FMIPO_MONUMENT_PHOTO}" loading="lazy" alt="Здобувачі факультету '
              'біля пам’ятника Г.С. Сковороді" /></p>',
        }]

    def education(data):
        sections = data['sections']
        sections[0]['html'] = body('fmipo-education')
        safety = next(s for s in sections if s.get('heading') == 'Безпека освітнього середовища')
        html = safety['html']
        # [collapse]-блок з організаційними заходами клієнт просив прибрати…
        html = re.sub(r'<p[^>]*>\s*\[collapse.*?\[/collapse\]\s*</p>', '', html, flags=re.S)
        html = re.sub(r'\[/?collapse[^\]]*\]', '', html)
        # …як і «Корисні посилання» наприкінці розділу.
        html = re.sub(r'<p[^>]*>\s*(<strong>)?\s*Корисні посилання.*$', '', html, flags=re.S)
        safety['html'] = html.strip()
        data['sections'] = [sections[0], safety]

    editor.edit('mathematics-informatics/home.uk.json', home)
    editor.edit('mathematics-informatics/admission.uk.json', admission)
    editor.edit('mathematics-informatics/education.uk.json', education)
    editor.edit('mathematics-informatics/history.uk.json',
                lambda data: data.__setitem__('sections', [{'html': body('fmipo-history')}]))
    editor.edit('mathematics-informatics/cooperation.uk.json',
                lambda data: data.__setitem__('sections', [{'html': body('fmipo-cooperation')}]))


def manifest(editor: Editor) -> None:
    def change(data):
        data['history-law']['contacts']['deanUrl'] = ZELENSKA_SITE

        choreo = data['kafedra-horeografiyi']['contacts']
        choreo['dean'] = 'Єфімова Олена Володимирівна'
        choreo['position'] = 'кандидат педагогічних наук, доцент'
        # Старі номери кафедра просила прибрати повністю.
        choreo['phone'] = '+38 (093) 408-79-66, +38 (098) 624-50-31'

        maths = data['mathematics-informatics']['contacts']
        maths['address'] = '61002, м. Харків, вул. Алчевських, 29, ауд. 309'
        maths['phone'] = '+38 (050) 139-31-67'
        maths['position'] = 'доктор педагогічних наук, професор, професор кафедри інформатики'
        maths['deanUrl'] = 'https://sites.google.com/hnpu.edu.ua/ponomarova/'

    editor.edit('manifest.json', change)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    files = assets()
    editor = Editor(args.dry_run)

    manifest(editor)
    history_law(editor, files)
    choreography(editor, files)
    fmipo(editor, files)

    for name in editor.touched:
        print(f'~ {name}')
    if not editor.touched:
        print('нічого не змінилося — правки вже застосовані.')
    print('готово.' if not args.dry_run else 'сухий прогін — нічого не записано.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
