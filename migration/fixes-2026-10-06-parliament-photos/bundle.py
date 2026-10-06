"""
Спільне для бандла правок 06.10 (Студентський Парламент): простір uuid і
карта файлів.

Кожен файл отримує uuid5 від свого імені в просторі цього бандла, тож `/assets/<uuid>` у
статичному JSON фронту збігається на локалі й на проді. Логотип і PDF лежать як є
(через контейнер `python:3.12-slim` з Pillow — на цій машині немає macOS `sips`) і лежать у
`files/` в git.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

HERE = Path(__file__).parent
FILES = HERE / 'files'
FILES_MAP = HERE / 'files.map.json'
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, 'https://hnpu.edu.ua/migration/fixes-2026-10-06-parliament-photos')


def file_id(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name))


def build_map() -> dict[str, dict]:
    mapping = {file_id(p.name): {'name': p.name} for p in sorted(FILES.iterdir())}
    FILES_MAP.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return mapping


if __name__ == '__main__':
    for fid, meta in build_map().items():
        print(fid, meta['name'])
