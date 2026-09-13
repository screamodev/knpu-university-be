#!/usr/bin/env python3
"""
Заповнити сінглтон `student_council_info` текстами з правок 13.09: «Про студентське
самоврядування», мета, основні завдання, нормативна база, емблема й загальне фото.

`pass2/load.py` вміє лише колекції з рядками, а це сінглтон, тож окремий скрипт. Поля, які
студенти вже заповнили в адмінці самі, не перетираються — лише порожні. `--force` перезаписує
все.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 set_council_info.py --dry-run
    python3 set_council_info.py

Файли емблеми й фото мають бути вже на цілі — спершу `push_assets.py`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login  # noqa: E402

EMBLEM_ID = 'ccad3d2b-c1a2-5ba4-a149-4a706886a583'
PHOTO_ID = '93d84723-7ce8-591d-b402-542c09cbfa81'
# «Положення про студентське самоврядування ХНПУ імені Г.С. Сковороди», уже в `documents`.
REGULATION_FILE_ID = '62d29ae7-72e2-40fa-9dec-7756c5f33111'

ABOUT = """<p>У ХНПУ імені Г.С. Сковороди та його структурних підрозділах діє студентське самоврядування, яке є невід’ємною частиною громадського самоврядування ХНПУ імені Г.С. Сковороди.</p>
<p>Студентський Парламент працює з 1996 року, коли офіційно було затверджено його Статут, і набуває все більшого значення у формуванні активної громадянської позиції серед студентів.</p>
<p>Студентський Парламент – це право і можливість здобувачів вищої освіти вирішувати питання навчання і побуту, захисту прав та інтересів здобувачів, а також брати участь в управлінні університету.</p>
<p>Студентський Парламент діє на принципах:</p>
<ul>
<li>добровільності, колегіальності, відкритості;</li>
<li>виборності та звітності органів студентського самоврядування;</li>
<li>рівності права студентів на участь у студентському самоврядуванні;</li>
<li>незалежності від впливу політичних партій та рухів, громадських і релігійних організацій.</li>
</ul>"""

MISSION = """<p>Метою діяльності Студентського Парламенту є захист прав та інтересів здобувачів; забезпечення виконання студентами своїх обов’язків; сприяння гармонійному розвитку особистості здобувача, формування у нього навичок організатора, керівника.</p>"""

OBJECTIVES = """<p>Основні завдання Студентського Парламенту:</p>
<ul>
<li>захист прав та інтересів здобувачів ХНПУ імені Г.С. Сковороди;</li>
<li>сприяння проведенню навчально-виховної роботи;</li>
<li>сприяння навчальній, науковій та творчій діяльності молоді;</li>
<li>сприяння формуванню у здобувачів вищої освіти ХНПУ імені Г.С. Сковороди моральних та етичних норм, виховання патріотизму;</li>
<li>пропаганда здорового способу життя, безпечної поведінки, запобігання вчиненню молоддю правопорушень;</li>
<li>сприяння виконанню студентами своїх обов’язків;</li>
<li>сприяння поліпшенню умов проживання й відпочинку здобувачів;</li>
<li>сприяння створенню різноманітних студентських гуртків, товариств, об'єднань, клубів за інтересами та координація їх діяльності;</li>
<li>співпраця з органами студентського самоврядування інших закладів вищої освіти, молодіжними громадськими організаціями;</li>
<li>сприяння працевлаштуванню випускників ХНПУ імені Г.С. Сковороди та залученню молоді до вторинної зайнятості у вільний від навчання час;</li>
<li>пропаганда в молодіжному середовищі патріотизму участь у організації та проведенні заходів спрямованих на патріотичне виховання студентства;</li>
<li>проведення роботи, спрямованої на підтримання високого іміджу ХНПУ імені Г.С. Сковороди, факультету, групи;</li>
<li>співробітництво з органами студентського самоврядування інших закладів вищої освіти;</li>
<li>забезпечення участі у вирішенні питань міжнародного обміну здобувачів; сприяння участі здобувачів ХНПУ імені Г.С. Сковороди у міжнародних, загальноукраїнських, міжрегіональних, регіональних та інших студентських конкурсах, конференціях, олімпіадах;</li>
<li>забезпечення участі здобувачів у реалізації державної молодіжної політики;</li>
<li>спільно з відповідними службами ХНПУ імені Г.С. Сковороди сприяння забезпеченню інформаційної, правової, психологічної, фінансової, юридичної та іншої допомоги студентській молоді;</li>
<li>представництво в колегіальних, представницьких, робочих, дорадчих органах ХНПУ імені Г.С. Сковороди та їхніх структурних підрозділах.</li>
</ul>"""

LEGAL_BASIS = f"""<p>У своїй діяльності органи студентського самоврядування керуються чинним законодавством України, у тому числі <a href="https://zakon.rada.gov.ua/laws/show/254%D0%BA/96-%D0%B2%D1%80#Text" target="_blank" rel="noopener noreferrer">Конституцією України</a>, <a href="https://zakon.rada.gov.ua/laws/show/1556-18#Text" target="_blank" rel="noopener noreferrer">Законом України «Про вищу освіту»</a> (стаття 40), наказами та розпорядженнями Міністерства освіти і науки України, Статутом Університету та <a href="/assets/{REGULATION_FILE_ID}" target="_blank" rel="noopener noreferrer">Положенням про ОСС</a>.</p>"""

VALUES = {
    'about': ABOUT,
    'mission': MISSION,
    'objectives': OBJECTIVES,
    'legalBasis': LEGAL_BASIS,
    'emblem': EMBLEM_ID,
    'photo': PHOTO_ID,
}


def is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, dict):
        return not value.get('id')
    return not str(value).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directus-url',
                        default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--force', action='store_true', help='перезаписати й заповнені поля')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    current = directus.get('/items/student_council_info') or {}
    patch = {
        field: value for field, value in VALUES.items()
        if args.force or is_empty(current.get(field))
    }
    kept = sorted(set(VALUES) - set(patch))
    if current.get('status') != 'published':
        patch['status'] = 'published'

    print(f'оновити: {sorted(patch) or "нічого"}', file=sys.stderr)
    if kept:
        print(f'лишити як є (вже заповнені): {kept}', file=sys.stderr)
    if args.dry_run or not patch:
        return 0

    directus.request('PATCH', '/items/student_council_info', payload=patch)
    print('done.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
