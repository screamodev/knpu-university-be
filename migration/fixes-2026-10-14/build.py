#!/usr/bin/env python3
"""
Вкладка «Анонси подій» Центру розвитку компетентностей учителя (правки 14.10, п. 2).

Бере з `SRC` (розпакований zip «Скачати все» з листа Н. Пономарьової) постер
`Тренінги 2026 ХНПУ.png`, перекодовує його в JPEG (`files/`; 1024×1536 — вже менше за 1600 px),
пише `files.map.json` і збирає `knpu-university-fe/app/content/structure/teacher-competence-centre/
events.uk.json` з двох HTML-фрагментів у `data/`:

* `events-trainings.html` — текст `пРО ТРЕНІНГИ.docx` дослівно (рядок-вказівка «ВНИЗУ ДОДАЙТЕ ПОСТЕР
  ТРЕНІНГІВ» виконано, а не перенесено на сторінку); постер йде одразу за текстом;
* `events-naumov.html` — текст `пРО НАУМОВСЬКІ ЧИТАННЯ.docx` дослівно.

Блоки розділені `<hr />`, заголовків від себе немає: кожен починається першим рядком документа.

    BE=/home/hnpu1/knpu-university-be FE=/home/hnpu1/knpu-university-fe
    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONPATH=/tmp/pil \\
      -v "$BE:$BE" -v "$FE:$FE" -v "<SRC>:/src:ro" -w "$BE/migration/fixes-2026-10-14" \\
      python:3.12-slim sh -c 'pip install -q --target /tmp/pil Pillow && python3 build.py /src'

Ідемпотентний: готовий файл пропускається, `events.uk.json` перезаписується тим самим вмістом.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

from bundle import DATA, FE_EVENTS, FILES, JPEG_QUALITY, file_id, save_map

POSTER_SOURCE = 'Тренінги 2026 ХНПУ.png'
POSTER_NAME = 'teacher-competence-centre-trainings-2026.jpg'
POSTER_ALT = 'Онлайн-тренінги Центру розвитку компетентностей учителя, 22, 29 і 30 жовтня 2026 року'


def main() -> int:
    src = Path(sys.argv[1])
    target = FILES / POSTER_NAME
    if not target.exists():
        FILES.mkdir(exist_ok=True)
        image = ImageOps.exif_transpose(Image.open(src / POSTER_SOURCE)).convert('RGB')
        image.save(target, 'JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True)
    poster_id = file_id(POSTER_NAME)
    save_map({poster_id: {'name': POSTER_NAME}})

    trainings = (DATA / 'events-trainings.html').read_text(encoding='utf-8').strip()
    naumov = (DATA / 'events-naumov.html').read_text(encoding='utf-8').strip()
    poster = f'<p><img src="/assets/{poster_id}" loading="lazy" alt="{html.escape(POSTER_ALT)}" /></p>'
    body = '\n'.join([trainings, poster, '<hr />', naumov])
    FE_EVENTS.write_text(json.dumps(
        {'sections': [{'html': body}], 'capturedAt': '2026-10-14'}, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(f'карта: 1 файл; {FE_EVENTS.name} записано', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
