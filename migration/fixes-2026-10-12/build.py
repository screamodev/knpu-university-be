#!/usr/bin/env python3
"""
Вкладка «Виховна діяльність» факультету історії і права (правки 12.10): урок «Козацька слава».

Бере з `SRC` (розпакований zip «Скачати все» з листа В. Вороніна) 5 фото, стискає їх у JPEG ≤1600 px
(`files/`), пише `files.map.json` і вставляє новий блок у
`knpu-university-fe/app/content/structure/history-law/students.uk.json` — одразу після першого
`<hr />`, над «Посвятою у першокурсники» (новіші події йдуть зверху).

Текст дослівно з `News_10_01.docx`. Заголовка в документі немає — його дала людина (12.10):
«Урок "Козацька слава" (он-лайн)», як `<p><strong>…</strong></p>` перед текстом, так само, як
заголовок «Посвята у першокурсники».

Pillow тут немає, тож через контейнер. Репо монтуються за тими самими шляхами, що на хості (бандл
сам знаходить фронт поруч), а SRC — теку з розпакованим zip — передати аргументом:

    BE=/home/hnpu1/knpu-university-be FE=/home/hnpu1/knpu-university-fe
    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONPATH=/tmp/pil \\
      -v "$BE:$BE" -v "$FE:$FE" -v "<SRC>:/src:ro" -w "$BE/migration/fixes-2026-10-12" \\
      python:3.12-slim sh -c 'pip install -q --target /tmp/pil Pillow && python3 build.py /src'

Ідемпотентний: готові файли пропускаються, блок вдруге не вставляється.
"""

from __future__ import annotations

import html
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

from bundle import FE_STUDENTS, FILES, JPEG_QUALITY, MAX_SIDE, file_id, save_map

MARKER = '<strong>01 жовтня 2026 р.</strong>'
MARKER_PARAGRAPH = '<p>' + MARKER
HEADING = '<p><strong>Урок "Козацька слава" (он-лайн)</strong></p>'
ALT = 'Урок «Козацька слава» (онлайн), 01.10.2026'
PHOTOS = [f'news_01_10_{n}.jpg' for n in range(1, 6)]

PARAGRAPHS = [
    '<p><strong>01 жовтня 2026 р.</strong> до Дня українського козацтва, Дня захисників та захисниць '
    'України на факультеті історії і права відбулися уроки "Козацька слава" (он-лайн) для учнів 7-х '
    'класів Харківської гімназії 35 та Харківської початкової школи 176.</p>',
    '<p>Здобувачі 2 курсу факультету історії і права Морозова Єлизавета та Давидов Денис підготували '
    'сучасний інтерактивний урок.</p>',
    '<p>Під час уроку учні дізналися про традиції, культуру, побут козаків на Січі та славну історію '
    'українського народу.</p>',
    '<p>Дякуємо всім учасникам та модераторам за проведений урок!</p>',
]


def compress(source: Path, target: Path) -> None:
    if target.exists():
        return
    image = ImageOps.exif_transpose(Image.open(source)).convert('RGB')
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    FILES.mkdir(exist_ok=True)
    image.save(target, 'JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True)


def main() -> int:
    src = Path(sys.argv[1])
    mapping: dict[str, dict] = {}
    figures = []
    for n, photo in enumerate(PHOTOS, 1):
        name = f'history-law-vykhovna-kozatska-slava-{n}.jpg'
        compress(src / photo, FILES / name)
        mapping[file_id(name)] = {'name': name}
        figures.append(f'<figure><img src="/assets/{file_id(name)}" loading="lazy" '
                       f'alt="{html.escape(ALT)}" /></figure>')
    save_map(mapping)

    block = '\n\n'.join([HEADING] + PARAGRAPHS + ['<div class="photo-grid gallery">' + ''.join(figures) + '</div>'])
    data = json.loads(FE_STUDENTS.read_text(encoding='utf-8'))
    body = data['sections'][0]['html']
    if MARKER in body:
        if HEADING in body:
            print('блок уже вставлено, фронт не чіпаю', file=sys.stderr)
            return 0
        # Блок вставлено раніше без заголовка (правки 12.10, перша версія) — дописати заголовок.
        data['sections'][0]['html'] = body.replace(MARKER_PARAGRAPH, HEADING + '\n\n' + MARKER_PARAGRAPH, 1)
        FE_STUDENTS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('заголовок дописано до вже вставленого блока', file=sys.stderr)
        return 0
    divider = '<hr />'
    at = body.index(divider) + len(divider)
    data['sections'][0]['html'] = body[:at] + '\n' + block + '\n\n<hr />' + body[at:]
    FE_STUDENTS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'карта: {len(mapping)} файлів; блок вставлено у {FE_STUDENTS.name}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
