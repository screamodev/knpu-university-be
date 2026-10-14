"""
Спільне для бандла правок 14.10 (Центр розвитку компетентностей учителя, вкладка «Анонси подій»):
простір uuid і карта файлів.

Кожен файл отримує uuid5 від свого імені в просторі цього бандла, тож `/assets/<uuid>` у
статичному JSON фронту збігається на локалі й на проді.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

HERE = Path(__file__).parent
FILES = HERE / 'files'
FILES_MAP = HERE / 'files.map.json'
DATA = HERE / 'data'
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, 'https://hnpu.edu.ua/migration/fixes-2026-10-14')
JPEG_QUALITY = 88

FE_EVENTS = (HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'structure'
             / 'teacher-competence-centre' / 'events.uk.json')


def file_id(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name))


def save_map(mapping: dict[str, dict]) -> None:
    ordered = dict(sorted(mapping.items(), key=lambda item: item[1]['name']))
    FILES_MAP.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
