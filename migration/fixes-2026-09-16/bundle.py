"""
Спільне для бандла правок 16.09: простір uuid, карта файлів і підготовка зображень.

Кожен файл отримує uuid5 від свого імені в просторі цього бандла, тож `/assets/<uuid>` у
статичних JSON фронту збігається на локалі й на проді. Фото стискаються до вебформату (довша
сторона 1600 px, JPEG) і лежать у `files/` в git; великі оригінали з пошти/Drive не комітимо.
"""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from pathlib import Path

HERE = Path(__file__).parent
FILES = HERE / 'files'
FILES_MAP = HERE / 'files.map.json'
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, 'https://hnpu.edu.ua/migration/fixes-2026-09-16')
MAX_SIDE = 1600

FE_CONTENT = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content'


def file_id(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name))


def load_map() -> dict[str, dict]:
    return json.loads(FILES_MAP.read_text(encoding='utf-8')) if FILES_MAP.exists() else {}


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


def add_image(source: Path, name: str, mapping: dict[str, dict]) -> str:
    """Стиснути `source` у `files/<name>` (JPEG, ≤1600 px) і записати в карту. → `/assets/<uuid>`."""
    FILES.mkdir(exist_ok=True)
    target = FILES / name
    if not target.exists():
        probe = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', str(source)],
                               check=True, capture_output=True, text=True).stdout
        longest = max(int(n) for n in re.findall(r'pixel(?:Width|Height): (\d+)', probe))
        resize = ['-Z', str(MAX_SIDE)] if longest > MAX_SIDE else []
        subprocess.run(
            ['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '78', *resize,
             str(source), '--out', str(target)],
            check=True, capture_output=True,
        )
    fid = file_id(name)
    mapping[fid] = {'name': name}
    return f'/assets/{fid}'


def add_file(source: Path, name: str, mapping: dict[str, dict]) -> str:
    """Скопіювати документ як є. → `/assets/<uuid>`."""
    FILES.mkdir(exist_ok=True)
    target = FILES / name
    if not target.exists():
        target.write_bytes(source.read_bytes())
    fid = file_id(name)
    mapping[fid] = {'name': name}
    return f'/assets/{fid}'


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
