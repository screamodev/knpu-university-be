"""
Спільне для бандла правок 08.10 (кафедра образотворчого мистецтва, вкладка «Виставкова
діяльність»): простір uuid і карта файлів.

Кожен файл отримує uuid5 від свого імені в просторі цього бандла, тож `/assets/<uuid>` у
статичному JSON фронту збігається на локалі й на проді. Фото стискаються до вебформату (довша
сторона 1600 px, JPEG) через Pillow — на цій машині немає macOS `sips`, тож `build.py` крутиться
в контейнері `python:3.12-slim`.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

HERE = Path(__file__).parent
FILES = HERE / 'files'
CACHE = HERE / '.cache'
FILES_MAP = HERE / 'files.map.json'
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, 'https://hnpu.edu.ua/migration/fixes-2026-10-08-exhibitions')
MAX_SIDE = 1600
JPEG_QUALITY = 78


def file_id(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name))


def save_map(mapping: dict[str, dict]) -> None:
    ordered = dict(sorted(mapping.items(), key=lambda item: item[1]['name']))
    FILES_MAP.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def slugify(text: str) -> str:
    table = str.maketrans({
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e', 'є': 'ie', 'ж': 'zh',
        'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
        'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ь': '', 'ю': 'iu', 'я': 'ia', '’': '', "'": '',
    })
    text = text.lower().translate(table)
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')
