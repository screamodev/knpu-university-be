#!/usr/bin/env python3
"""
Create the collections added by migration pass 2 (Education / Science / Divisions).

The committed schema lives in `snapshots/schema.yaml`, but hand-writing 8 collections in that
format is ~4 000 lines of YAML. This script builds them through the API instead; afterwards
regenerate the snapshot so the repo stays the source of truth:

    docker compose -f docker-compose.dev.yml exec directus \
      npx directus schema snapshot --yes /directus/snapshots/schema.yaml

Idempotent: existing collections and fields are left alone, missing ones are added.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin
    python3 apply_schema.py --dry-run
    python3 apply_schema.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

STATUS_CHOICES = [
    {'text': '$t:published', 'value': 'published', 'color': '#2ECDA7'},
    {'text': '$t:draft', 'value': 'draft', 'color': '#D3DAE4'},
    {'text': '$t:archived', 'value': 'archived', 'color': '#A2B5CD'},
]


class Directus:
    def __init__(self, base: str, token: str):
        self.base = base.rstrip('/')
        self.token = token

    def request(self, method: str, path: str, payload=None):
        headers = {'Authorization': f'Bearer {self.token}'}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(f'{self.base}{path}', data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read()
        return json.loads(body)['data'] if body else None

    def get(self, path: str):
        return self.request('GET', path)


def login(base: str, email: str, password: str) -> str:
    request = urllib.request.Request(
        f'{base.rstrip("/")}/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())['data']['access_token']


# ── field builders ───────────────────────────────────────────────────────────

def field(name: str, data_type: str, *, interface: str, meta: dict | None = None,
          schema: dict | None = None, note: str | None = None, required: bool = False,
          width: str = 'full', options: dict | None = None, display: str | None = None,
          display_options: dict | None = None, special: list | None = None) -> dict:
    return {
        'field': name,
        'type': data_type,
        'meta': {
            'interface': interface,
            'options': options,
            'display': display,
            'display_options': display_options,
            'note': note,
            'required': required,
            'width': width,
            'special': special,
            **(meta or {}),
        },
        'schema': {
            'is_nullable': not required,
            **(schema or {}),
        },
    }


def id_field() -> dict:
    return {
        'field': 'id',
        'type': 'uuid',
        'meta': {'hidden': True, 'interface': 'input', 'readonly': True, 'special': ['uuid']},
        'schema': {'is_primary_key': True, 'has_auto_increment': False, 'is_nullable': False},
    }


def status_field() -> dict:
    return field('status', 'string', interface='select-dropdown', width='half',
                 options={'choices': STATUS_CHOICES}, display='labels',
                 display_options={'choices': STATUS_CHOICES, 'showAsDot': True},
                 schema={'default_value': 'draft', 'is_nullable': False, 'max_length': 255})


def order_field() -> dict:
    return field('order', 'integer', interface='input', width='half',
                 note='Порядок у списку на сайті.', schema={'default_value': 0})


def text_field(name: str, note: str | None = None, *, required: bool = False,
               width: str = 'full', length: int = 255) -> dict:
    return field(name, 'string', interface='input', note=note, required=required,
                 width=width, schema={'max_length': length})


def multiline(name: str, note: str | None = None, *, required: bool = False) -> dict:
    return field(name, 'text', interface='input-multiline', note=note, required=required)


def select(name: str, choices: list[dict], note: str | None = None, *,
           required: bool = False, width: str = 'half') -> dict:
    return field(name, 'string', interface='select-dropdown', options={'choices': choices},
                 display='labels', display_options={'choices': choices}, note=note,
                 required=required, width=width, schema={'max_length': 64})


def file_field(name: str = 'file', note: str | None = None, *, width: str = 'half') -> dict:
    return field(name, 'uuid', interface='file', special=['file'], note=note, width=width)


def m2o(name: str, note: str | None = None, *, template: str = '{{title}}') -> dict:
    return field(name, 'uuid', interface='select-dropdown-m2o', special=['m2o'],
                 options={'template': template}, note=note, width='half')


def o2m(name: str, note: str | None = None) -> dict:
    return {
        'field': name,
        'type': 'alias',
        'meta': {'interface': 'list-o2m', 'special': ['o2m'], 'note': note,
                 'options': {'enableCreate': True, 'enableSelect': False}},
    }


def collection(name: str, *, icon: str, note: str, template: str, fields: list[dict],
               sort: int, singleton: bool = False) -> dict:
    return {
        'collection': name,
        'meta': {
            'accountability': 'all',
            'archive_field': 'status',
            'archive_value': 'archived',
            'unarchive_value': 'draft',
            'archive_app_filter': True,
            'collapse': 'open',
            'display_template': template,
            'hidden': False,
            'icon': icon,
            'note': note,
            # A singleton is one editable record — Directus opens it directly, with no list and
            # therefore no manual ordering.
            'singleton': singleton,
            'sort': sort,
            'sort_field': None if singleton else 'order',
            'versioning': False,
        },
        'schema': {'name': name},
        'fields': fields,
    }


LEVEL_CHOICES = [
    {'text': 'Перший (бакалаврський)', 'value': 'bachelor'},
    {'text': 'Другий (магістерський)', 'value': 'master'},
    {'text': 'Третій (освітньо-науковий)', 'value': 'phd'},
]

# Напрями — як їх називає сама сторінка /uk/monitoryng старого сайту: спершу вона мала лише
# п’ять, решта анкет падала в «Інше», аж поки клієнт не попросив повернути повний розподіл.
MONITORING_AREAS = [
    {'text': 'Освітня діяльність', 'value': 'educational-activity'},
    {'text': 'Реалізація освітніх програм', 'value': 'programme-implementation'},
    {'text': 'Реалізація освітньо-наукових програм', 'value': 'phd-programmes'},
    {'text': 'Освітнє середовище', 'value': 'educational-environment'},
    {'text': 'Наукова й інноваційна діяльність', 'value': 'research'},
    {'text': 'Міжнародне співробітництво', 'value': 'international'},
    {'text': 'Молодіжна політика', 'value': 'youth-policy'},
    {'text': 'Менеджмент і кадрове забезпечення', 'value': 'management'},
    {'text': 'Взаємодія внутрішніх і зовнішніх стейкхолдерів', 'value': 'stakeholders'},
    {'text': 'Експрес-опитування', 'value': 'express'},
    {'text': 'Результати рейтингового оцінювання науково-педагогічних працівників',
     'value': 'staff-rating'},
    {'text': 'Інше', 'value': 'other'},
]

DOSSIER_KINDS = [
    {'text': 'Відомості про самооцінювання', 'value': 'self-assessment'},
    {'text': 'Програма виїзду експертної групи', 'value': 'visit-program'},
    {'text': 'Звіт експертної групи', 'value': 'expert-report'},
    {'text': 'Експертний висновок галузевої експертної ради', 'value': 'ger-conclusion'},
    {'text': 'Рішення Національного агентства', 'value': 'naqa-decision'},
    {'text': 'Інший документ', 'value': 'other'},
]

FORM_OF_STUDY = [
    {'text': 'Денна форма', 'value': 'full-time'},
    {'text': 'Заочна форма', 'value': 'part-time'},
]

COUNCIL_FILE_KINDS = [
    {'text': 'Дисертація', 'value': 'dissertation'},
    {'text': 'Висновок про наукову новизну', 'value': 'conclusion'},
    {'text': 'Висновок наукового керівника', 'value': 'supervisor'},
    {'text': 'Відгук офіційного опонента', 'value': 'opponent'},
    {'text': 'Рецензія', 'value': 'review'},
    {'text': 'Рішення про присудження ступеня', 'value': 'decision'},
    {'text': 'Аудіо-/відеозапис захисту', 'value': 'video'},
    {'text': 'Інший документ', 'value': 'other'},
]

REDIRECT_KINDS = [
    {'text': 'Сторінка', 'value': 'page'},
    {'text': 'Файл', 'value': 'file'},
]

AGREEMENT_CATEGORIES = [
    {'text': 'З Інститутами НАПН та НАН України', 'value': 'napn'},
    {'text': 'Із закладами вищої освіти України', 'value': 'universities'},
    {'text': 'Із закладами середньої, дошкільної освіти та відділами освіти', 'value': 'schools'},
    {'text': 'З організаціями й установами України', 'value': 'organizations'},
    {'text': 'Міжнародні договори, угоди, меморандуми', 'value': 'international'},
]

STUDENT_COUNCIL_GROUPS = [
    {'text': 'Голова', 'value': 'chair'},
    {'text': 'Заступник голови', 'value': 'deputy'},
    {'text': 'Голова студради факультету', 'value': 'faculty-chair'},
    {'text': 'Контрольно-ревізійна комісія', 'value': 'audit'},
]

COLLECTIONS = [
    collection(
        'monitoring_surveys', icon='poll', sort=30, template='{{number}} · {{title}}',
        note='Анкети моніторингових досліджень для сторінки «Моніторинг». Результати за роками — у пов’язаній колекції.',
        fields=[
            id_field(), status_field(),
            text_field('number', 'Номер анкети на кшталт «2» або «11/1».', width='half', length=32),
            select('area', MONITORING_AREAS, 'Напрям діяльності — заголовок групи на сторінці.',
                   required=True),
            text_field('title', required=True),
            text_field('titleEn'),
            multiline('researchGroup', 'Дослідницька група.'),
            file_field('programmeFile', 'PDF програми дослідження.'),
            text_field('formUrl', 'Покликання на Google-форму анкети.', width='half', length=500),
            order_field(),
            o2m('results', 'Результати за роками.'),
        ],
    ),
    collection(
        'monitoring_survey_results', icon='insert_chart', sort=31, template='{{year}}',
        note='Результати анкети моніторингу за конкретний рік.',
        fields=[
            id_field(), status_field(),
            m2o('survey', 'Анкета, до якої належить результат.', template='{{number}} · {{title}}'),
            text_field('year', 'Рік або навчальний рік: «2024», «2026/2027».', width='half', length=32),
            file_field('file'),
            text_field('externalUrl', 'Якщо файл лежить у Google Drive.', width='half', length=500),
            order_field(),
        ],
    ),
    collection(
        'accreditation_certificates', icon='verified', sort=32, template='{{title}}',
        note='Сертифікати про акредитацію освітніх програм і спеціальностей.',
        fields=[
            id_field(), status_field(),
            select('level', LEVEL_CHOICES, 'Рівень вищої освіти.', required=True),
            text_field('branch', 'Галузь знань, напр. «01 Освіта/Педагогіка».', width='half'),
            text_field('specialtyCode', 'Код спеціальності, напр. «014».', width='half', length=32),
            text_field('title', required=True),
            text_field('titleEn'),
            file_field('file'),
            text_field('externalUrl', width='half', length=500),
            order_field(),
        ],
    ),
    collection(
        'accreditation_dossiers', icon='fact_check', sort=33, template='{{programmeTitle}}',
        note='Акредитаційні справи освітніх програм (матеріали НАЗЯВО) — сторінка «Центр забезпечення якості освіти».',
        fields=[
            id_field(), status_field(),
            text_field('academicYear', 'Навчальний рік, напр. «2019-2020».', width='half', length=32),
            select('level', LEVEL_CHOICES, required=False),
            text_field('programmeTitle', required=True),
            order_field(),
            o2m('files', 'Документи акредитаційної справи.'),
        ],
    ),
    collection(
        'accreditation_dossier_files', icon='description', sort=34, template='{{title}}',
        note='Окремий документ акредитаційної справи.',
        fields=[
            id_field(), status_field(),
            m2o('dossier', template='{{programmeTitle}}'),
            select('kind', DOSSIER_KINDS, required=True),
            text_field('title'),
            file_field('file'),
            text_field('externalUrl', width='half', length=500),
            order_field(),
        ],
    ),
    collection(
        'contingent_reports', icon='groups', sort=35, template='{{title}}',
        note='Контингент здобувачів освіти — щомісячні звіти для сторінки «Контингент студентів».',
        fields=[
            id_field(), status_field(),
            text_field('academicYear', 'Навчальний рік, напр. «2025-2026».', width='half', length=32),
            select('formOfStudy', FORM_OF_STUDY, required=True),
            field('reportDate', 'date', interface='datetime', display='datetime', width='half',
                  note='Станом на цю дату.'),
            text_field('title', required=True),
            file_field('file'),
            order_field(),
        ],
    ),
    collection(
        'science_schools', icon='school', sort=36, template='{{name}}',
        note='Наукові школи університету — сторінка «Напрями наукової та мистецької діяльності».',
        fields=[
            id_field(), status_field(),
            text_field('name', required=True),
            text_field('nameEn'),
            text_field('leader', 'Керівник школи.'),
            text_field('founder', 'Фундатор школи.'),
            file_field('file', 'Довідка або положення.'),
            text_field('externalUrl', 'Сайт школи або керівника.', width='half', length=500),
            order_field(),
        ],
    ),
    collection(
        'science_directions', icon='science', sort=37, template='{{department}} · {{topic}}',
        note='Основні напрями наукової і мистецької діяльності кафедр.',
        fields=[
            id_field(), status_field(),
            text_field('department', 'Кафедра.', required=True),
            text_field('departmentEn'),
            multiline('topic', 'Тема напряму.', required=True),
            text_field('supervisor', 'Науковий керівник напряму.'),
            order_field(),
        ],
    ),
    collection(
        'dissertation_councils', icon='workspace_premium', sort=38,
        template='{{councilCode}} · {{candidateName}}',
        note='Разові спеціалізовані вчені ради — захисти дисертацій доктора філософії. '
             'Перенесені зі сторінки /uk/razovi-specializovani-vcheni-rady старого сайту; '
             'посилання на них зареєстровані в державній базі, тому `legacySlug` міняти не можна.',
        fields=[
            id_field(), status_field(),
            text_field('legacySlug', 'Адреса сторінки на старому сайті без /uk/. '
                                     'Вона ж — адреса на новому сайті. Не змінювати.', required=True),
            text_field('councilCode', 'Шифр ради, напр. «ДФ 011.143.25».', width='half', length=64),
            text_field('candidateName', 'Здобувач.', required=True, width='half'),
            text_field('candidateNameEn', width='half'),
            multiline('dissertationTitle', 'Тема дисертації.'),
            multiline('dissertationTitleEn'),
            text_field('specialty', 'Спеціальність, напр. «011 Освітні, педагогічні науки».',
                       width='half'),
            text_field('branch', 'Галузь знань, напр. «01 Освіта/Педагогіка».', width='half'),
            field('defenseDate', 'date', interface='datetime', display='datetime', width='half',
                  note='Дата захисту.'),
            text_field('defenseTime', 'Час захисту, напр. «08:30».', width='half', length=16),
            field('year', 'integer', interface='input', width='half',
                  note='Рік, під яким рада стоїть у переліку на сайті.'),
            field('contentHtml', 'text', interface='input-rich-text-html',
                  note='Текст сторінки: склад ради, документи до захисту, контакти.'),
            text_field('streamUrl', 'Покликання на трансляцію захисту.', width='half', length=500),
            text_field('legacyUrl', 'Повна адреса сторінки на старому сайті (походження).',
                       width='half', length=500),
            order_field(),
            o2m('files', 'Документи до захисту.'),
        ],
    ),
    collection(
        'dissertation_council_files', icon='description', sort=39, template='{{title}}',
        note='Документ до захисту разової спеціалізованої вченої ради.',
        fields=[
            id_field(), status_field(),
            m2o('council', template='{{councilCode}} · {{candidateName}}'),
            select('kind', COUNCIL_FILE_KINDS, required=False),
            multiline('title', 'Підпис посилання на старому сайті.'),
            file_field('file'),
            text_field('externalUrl', 'Якщо документ лежить у Google Drive (КЕП).',
                       width='half', length=500),
            text_field('legacyPath', 'Шлях файлу на старому сайті, напр. '
                                     '«/sites/default/files/files/Rada/Razova_rada/11_25/Dyser.pdf».',
                       length=500),
            order_field(),
        ],
    ),
    collection(
        'legacy_redirects', icon='alt_route', sort=40, template='{{legacyPath}}',
        note='Адреси старого сайту hnpu.edu.ua, які мають далі працювати після переїзду домену. '
             'Nuxt віддає на них 301 — або на `targetPath`, або на /assets/<файл>.',
        fields=[
            id_field(), status_field(),
            text_field('legacyPath', 'Шлях на старому сайті, напр. «/uk/…» або '
                                     '«/sites/default/files/…». Без домену й без параметрів.',
                       required=True, length=500),
            select('kind', REDIRECT_KINDS, required=False),
            text_field('targetPath', 'Куди вести — шлях на новому сайті. Для файлів лишити порожнім.',
                       length=500),
            file_field('file', 'Перенесений файл — 301 веде на /assets/<id>.'),
            text_field('note', 'Звідки взявся запис.'),
            order_field(),
        ],
    ),
    collection(
        'student_council_info', icon='groups_2', sort=41, singleton=True,
        template='Студентське самоврядування',
        note='Тексти й контакти сторінки «Студентське самоврядування». Один запис — редагують '
             'самі студенти; порожні поля сторінка показує як «розділ наповнюється».',
        fields=[
            id_field(), status_field(),
            field('about', 'text', interface='input-rich-text-html',
                  note='Про студентське самоврядування — вступний текст сторінки.'),
            field('mission', 'text', interface='input-rich-text-html', note='Місія.'),
            field('objectives', 'text', interface='input-rich-text-html', note='Завдання.'),
            text_field('address', 'Адреса: корпус, поверх, кімната.'),
            text_field('email', 'Загальна пошта самоврядування.', width='half'),
            text_field('trustBoxUrl', 'Скринька довіри — форма або пошта.', width='half', length=500),
            text_field('facebook', width='half', length=500),
            text_field('instagram', width='half', length=500),
            text_field('telegram', width='half', length=500),
        ],
    ),
    collection(
        'student_council_members', icon='badge', sort=42, template='{{name}}',
        note='Люди студентського самоврядування: голова, заступники, голови студрад факультетів '
             'і контрольно-ревізійна комісія. Блок на сторінці обирається полем «група».',
        fields=[
            id_field(), status_field(),
            select('group', STUDENT_COUNCIL_GROUPS, 'Блок сторінки, у якому з’явиться людина.',
                   required=True),
            text_field('name', 'Прізвище, ім’я та по батькові.', required=True),
            text_field('position', 'Посада, якщо відрізняється від назви блоку.'),
            text_field('faculty', 'Факультет — для голів студрад факультетів.', width='half'),
            text_field('email', width='half'),
            file_field('photo'),
            text_field('profileUrl', 'Сторінка або соцмережа людини.', width='half', length=500),
            order_field(),
        ],
    ),
    collection(
        'student_council_sectors', icon='hub', sort=43, template='{{name}}',
        note='Сектори студентського самоврядування: чим займаються і хто очолює.',
        fields=[
            id_field(), status_field(),
            text_field('name', required=True),
            multiline('description', 'Кілька речень про роботу сектору.'),
            text_field('leadName', 'Голова сектору.', width='half'),
            text_field('leadEmail', width='half'),
            text_field('externalUrl', 'Сторінка або спільнота сектору.', width='half', length=500),
            order_field(),
        ],
    ),
    collection(
        'cooperation_agreements', icon='handshake', sort=44, template='{{number}} · {{partner}}',
        note='Договори, угоди та меморандуми про співпрацю. П’ять розділів — по одній сторінці на '
             'кожен, як накази з основної діяльності.',
        fields=[
            id_field(), status_field(),
            select('category', AGREEMENT_CATEGORIES, 'Розділ — визначає, на якій сторінці рядок '
                                                    'з’явиться.', required=True),
            text_field('number', 'Номер у переліку розділу.', width='half', length=16),
            # Дати в реєстрі нерегулярні — «2017 р.», «25.12.2012 р.», тож рядок; рік окремим
            # полем, бо саме за ним фільтрує сторінка.
            text_field('agreementDate', 'Дата укладання так, як у реєстрі.', width='half', length=64),
            field('year', 'integer', interface='input', width='half',
                  note='Рік укладання — за ним працює фільтр на сторінці.'),
            text_field('partner', 'Друга сторона договору.', required=True, length=500),
            text_field('partnerEn', length=500),
            multiline('subject', 'Вид документа й предмет співпраці.'),
            multiline('subjectEn'),
            text_field('country', 'Країна — для міжнародних угод.', width='half'),
            text_field('countryEn', width='half'),
            text_field('term', 'Термін дії.', width='half'),
            text_field('termEn', width='half'),
            order_field(),
        ],
    ),
]

# field → collection it points at; used to create the relations Directus needs.
RELATIONS = [
    # (collection, field, related_collection, one_field)
    ('monitoring_surveys', 'programmeFile', 'directus_files', None),
    ('monitoring_survey_results', 'survey', 'monitoring_surveys', 'results'),
    ('monitoring_survey_results', 'file', 'directus_files', None),
    ('accreditation_certificates', 'file', 'directus_files', None),
    ('accreditation_dossier_files', 'dossier', 'accreditation_dossiers', 'files'),
    ('accreditation_dossier_files', 'file', 'directus_files', None),
    ('contingent_reports', 'file', 'directus_files', None),
    ('science_schools', 'file', 'directus_files', None),
    ('dissertation_council_files', 'council', 'dissertation_councils', 'files'),
    ('dissertation_council_files', 'file', 'directus_files', None),
    ('legacy_redirects', 'file', 'directus_files', None),
    ('student_council_members', 'photo', 'directus_files', None),
]

# Extra `documents.section` options this pass introduces.
NEW_DOCUMENT_SECTIONS = [
    {'text': 'Ліцензія університету', 'value': 'licenses'},
    {'text': 'Нагороди та відзнаки', 'value': 'awards'},
    {'text': 'Навчальний відділ', 'value': 'academic-office'},
    {'text': 'Графік освітнього процесу', 'value': 'education-schedule'},
    {'text': 'Служба вченого секретаря', 'value': 'scientific-secretary'},
    {'text': 'Спеціалізовані вчені ради', 'value': 'specialized-councils'},
    {'text': 'Центр забезпечення якості освіти', 'value': 'quality-centre'},
    {'text': 'Центр якості освіти — освітні програми', 'value': 'quality-centre-programmes'},
    {'text': 'Центр цифровізації освіти', 'value': 'digital-center'},
    {'text': 'Приймальна комісія', 'value': 'admissions-committee'},
    {'text': 'Моніторинг — нормативні документи', 'value': 'monitoring'},
    {'text': 'Наукові школи — нормативні документи', 'value': 'science-schools'},
    {'text': 'Контакти — довідники', 'value': 'contacts'},
    {'text': 'Наукова рада', 'value': 'science-council'},
    {'text': 'Наукові заходи', 'value': 'science-events'},
    {'text': 'Вчена рада — ухвали', 'value': 'academic-council-decisions'},
    {'text': 'На допомогу здобувачу', 'value': 'candidate-support'},
    {'text': 'На допомогу здобувачу вченого звання', 'value': 'academic-title-support'},
    {'text': 'Вартість навчання', 'value': 'tuition'},
    {'text': 'Вступ — перелік освітніх програм і ліцензовані обсяги',
     'value': 'admissions-programmes'},
    {'text': 'Вступ — рейтингові списки вступників', 'value': 'admissions-rating-lists'},
    {'text': 'Вступ — рекомендації до зарахування', 'value': 'admissions-recommendations'},
    {'text': 'Вступ — накази про зарахування', 'value': 'admissions-enrolment-orders'},
]


def ensure_collections(directus: Directus, dry_run: bool) -> None:
    existing = {row['collection'] for row in (directus.get('/collections?limit=-1') or [])}

    for spec in COLLECTIONS:
        name = spec['collection']
        if name in existing:
            ensure_fields(directus, spec, dry_run)
            continue
        print(f'+ collection {name}')
        if not dry_run:
            directus.request('POST', '/collections', payload=spec)


def ensure_fields(directus: Directus, spec: dict, dry_run: bool) -> None:
    name = spec['collection']
    have = {row['field'] for row in (directus.get(f'/fields/{name}') or [])}
    for item in spec['fields']:
        if item['field'] in have:
            continue
        print(f'+ field {name}.{item["field"]}')
        if not dry_run:
            directus.request('POST', f'/fields/{name}', payload=item)


def ensure_relations(directus: Directus, dry_run: bool) -> None:
    existing = {(row['collection'], row['field'])
                for row in (directus.get('/relations') or [])}
    for coll, fld, related, one_field in RELATIONS:
        if (coll, fld) in existing:
            continue
        print(f'+ relation {coll}.{fld} -> {related}')
        if dry_run:
            continue
        payload = {
            'collection': coll,
            'field': fld,
            'related_collection': related,
            'meta': {'sort_field': None, 'one_deselect_action': 'nullify'},
            'schema': {'on_delete': 'SET NULL'},
        }
        if one_field:
            payload['meta']['one_field'] = one_field
        directus.request('POST', '/relations', payload=payload)


def ensure_document_sections(directus: Directus, dry_run: bool) -> None:
    current = directus.get('/fields/documents/section')
    choices = list(current['meta']['options']['choices'])
    known = {choice['value'] for choice in choices}
    added = [choice for choice in NEW_DOCUMENT_SECTIONS if choice['value'] not in known]
    if not added:
        return
    choices.extend(added)
    print('+ documents.section: ' + ', '.join(choice['value'] for choice in added))
    if dry_run:
        return
    meta = {
        'options': {**(current['meta'].get('options') or {}), 'choices': choices},
        'display_options': {**(current['meta'].get('display_options') or {}), 'choices': choices},
    }
    directus.request('PATCH', '/fields/documents/section', payload={'meta': meta})


def ensure_monitoring_areas(directus: Directus, dry_run: bool) -> None:
    """
    Add напрями that appeared after the collection was created.

    `MONITORING_AREAS` only takes effect when `monitoring_surveys` is created; on an environment
    where it already exists the new напрями have to be appended to the field's choices, the same
    way `ensure_document_sections` does it for documents.
    """
    current = directus.get('/fields/monitoring_surveys/area')
    if not current:
        return
    choices = list((current['meta'].get('options') or {}).get('choices') or [])
    known = {choice['value'] for choice in choices}
    added = [choice for choice in MONITORING_AREAS if choice['value'] not in known]
    if not added:
        return
    choices.extend(added)
    print('+ monitoring_surveys.area: ' + ', '.join(choice['value'] for choice in added))
    if dry_run:
        return
    meta = {
        'options': {**(current['meta'].get('options') or {}), 'choices': choices},
        'display_options': {**(current['meta'].get('display_options') or {}), 'choices': choices},
    }
    directus.request('PATCH', '/fields/monitoring_surveys/area', payload={'meta': meta})


def ensure_category_parent(directus: Directus, dry_run: bool) -> None:
    """
    Give `categories` a parent, so a кафедра's category can sit under its faculty's.

    The site rolls the tree up: a кафедра page shows its own news and, while it has none, the
    faculty's; a faculty page shows its own plus everything its кафедри publish.
    """
    have = {row['field'] for row in (directus.get('/fields/categories') or [])}

    if 'parent' not in have:
        print('+ field categories.parent')
        if not dry_run:
            directus.request('POST', '/fields/categories', payload=m2o(
                'parent', 'Категорія вищого рівня — напр. факультет для кафедри.',
                template='{{name}}'))

    if 'children' not in have:
        print('+ field categories.children')
        if not dry_run:
            directus.request('POST', '/fields/categories', payload=o2m(
                'children', 'Категорії підрозділів, що входять до цієї.'))

    existing = {(row['collection'], row['field']) for row in (directus.get('/relations') or [])}
    if ('categories', 'parent') not in existing:
        print('+ relation categories.parent -> categories')
        if not dry_run:
            directus.request('POST', '/relations', payload={
                'collection': 'categories',
                'field': 'parent',
                'related_collection': 'categories',
                'meta': {'one_field': 'children', 'sort_field': None, 'one_deselect_action': 'nullify'},
                'schema': {'on_delete': 'SET NULL'},
            })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    try:
        ensure_collections(directus, args.dry_run)
        ensure_relations(directus, args.dry_run)
        ensure_document_sections(directus, args.dry_run)
        ensure_monitoring_areas(directus, args.dry_run)
        ensure_category_parent(directus, args.dry_run)
    except urllib.error.HTTPError as exc:
        print(f'! {exc.code}: {exc.read().decode("utf-8", "replace")[:800]}', file=sys.stderr)
        return 1

    print('done.' if not args.dry_run else 'dry run — nothing written.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
