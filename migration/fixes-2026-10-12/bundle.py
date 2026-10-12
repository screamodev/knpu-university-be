"""
Спільне для бандла правок 12.10 (факультет історії і права, вкладка «Виховна діяльність»):
простір uuid і карта файлів.

Кожен файл отримує uuid5 від свого імені в просторі цього бандла, тож `/assets/<uuid>` у
статичному JSON фронту збігається на локалі й на проді. Фото стискаються до вебформату (довша
сторона 1600 px, JPEG) через Pillow — на цій машині немає macOS `sips`, тож `build.py` крутиться
в контейнері `python:3.12-slim`.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

HERE = Path(__file__).parent
FILES = HERE / 'files'
FILES_MAP = HERE / 'files.map.json'
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, 'https://hnpu.edu.ua/migration/fixes-2026-10-12')
MAX_SIDE = 1600
JPEG_QUALITY = 78

FE_STUDENTS = (HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'structure'
               / 'history-law' / 'students.uk.json')


def file_id(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name))


def save_map(mapping: dict[str, dict]) -> None:
    ordered = dict(sorted(mapping.items(), key=lambda item: item[1]['name']))
    FILES_MAP.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
