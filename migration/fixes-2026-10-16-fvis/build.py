#!/usr/bin/env python3
"""
Вкладки «Історія» і «Спортивні споруди» факультету фізичного виховання і спорту (правки 16.10, п. 3).

Бере з `SRC` (розпакований zip «Скачати все» з листа faculty-sport@) файли `Фото1.jpg` …
`Фото 17.jpg` (у назвах пробіли й одна зайва літера «І» — `ІФото 13.jpg`; номер береться з назви),
стискає до 1600 px по довшій стороні в JPEG (`files/fvis-photo-NN.jpg`), пише `files.map.json` і
збирає два JSON фронту з HTML-фрагментів у `data/`:

* `history.html` → `physical-education/history.uk.json` — текст «Оновлення стор. факультету.docx»
  (розділ 1 «ІСТОРІЯ») дослівно; Фото 1 на початку, Фото 2 після рядка «Декан»;
* `facilities.html` → `physical-education/facilities.uk.json` — розділ 2 «ОСВІТА» («Створити нову
  вкладку СПОРТИВНІ СПОРУДИ»); фото в сітках `photo-grid gallery` біля тих залів, де їх указано.

У фрагментах `{{img:N|alt}}` → `<img src="/assets/<uuid>" loading="lazy" alt="…" />`.

    BE=/home/hnpu1/knpu-university-be FE=/home/hnpu1/knpu-university-fe
    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONPATH=/tmp/pil \\
      -v "$BE:$BE" -v "$FE:$FE" -v "<SRC>:/src:ro" -w "$BE/migration/fixes-2026-10-16-fvis" \\
      python:3.12-slim sh -c 'pip install -q --target /tmp/pil Pillow && python3 build.py /src'

Ідемпотентний: готові фото пропускаються, JSON перезаписуються тим самим вмістом.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageOps

from bundle import CAPTURED_AT, DATA, FE_UNIT, FILES, JPEG_QUALITY, MAX_SIDE, file_id, save_map

PHOTO_COUNT = 17
PLACEHOLDER = re.compile(r'\{\{img:(\d+)\|([^}]*)\}\}')


def photo_name(number: int) -> str:
    return f'fvis-photo-{number:02d}.jpg'


def find_source(src: Path, number: int) -> Path:
    pattern = re.compile(rf'^\D*{number}\.jpe?g$', re.I)
    found = [path for path in src.iterdir() if pattern.match(path.name)]
    if len(found) != 1:
        raise SystemExit(f'Фото {number}: у {src} знайдено {len(found)} файлів, потрібен один')
    return found[0]


def convert(source: Path, target: Path) -> None:
    image = ImageOps.exif_transpose(Image.open(source)).convert('RGB')
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    image.save(target, 'JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True)


def render(fragment: str) -> str:
    def img(match: re.Match[str]) -> str:
        number, alt = int(match.group(1)), match.group(2)
        attrs = f' alt="{html.escape(alt)}"' if alt else ''
        return f'<img src="/assets/{file_id(photo_name(number))}" loading="lazy"{attrs} />'

    return PLACEHOLDER.sub(img, fragment.strip())


def write_tab(name: str, fragment: str, source_urls: list[str] | None = None) -> None:
    content: dict = {'sections': [{'html': render(fragment)}]}
    if source_urls:
        content['sourceUrls'] = source_urls
    content['capturedAt'] = CAPTURED_AT
    (FE_UNIT / f'{name}.uk.json').write_text(
        json.dumps(content, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> int:
    src = Path(sys.argv[1])
    FILES.mkdir(exist_ok=True)
    mapping = {}
    for number in range(1, PHOTO_COUNT + 1):
        name = photo_name(number)
        target = FILES / name
        if not target.exists():
            convert(find_source(src, number), target)
        mapping[file_id(name)] = {'name': name}
    save_map(mapping)

    history_urls = json.loads((FE_UNIT / 'history.uk.json').read_text(encoding='utf-8')).get('sourceUrls')
    write_tab('history', (DATA / 'history.html').read_text(encoding='utf-8'), history_urls)
    write_tab('facilities', (DATA / 'facilities.html').read_text(encoding='utf-8'))
    print(f'карта: {len(mapping)} файлів; history.uk.json, facilities.uk.json записано', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
