#!/usr/bin/env python3
"""
Зібрати вкладку «Виставкова діяльність» кафедри образотворчого мистецтва (правки 08.10).

Читає `exhibitions.json` (виставки, підписи, джерела) і робить три речі:

* качає джерела в `.cache/` — публічні файли Google Drive (галереї «Незламні» і «Прогулянка
  Харковом» зі старого Google Sites кафедри) та оригінали картин «Мистецтво без кордонів» зі старого
  сайту;
* стискає фото до JPEG ≤1600 px у `files/` (в git); анімації (mp4) туди не потрапляють — вони в
  карті з `drive_id`, а `push_assets.py` качає їх сам;
* пише `files.map.json` і `data/exhibitions.uk.json` — тіло вкладки для
  `knpu-university-fe/app/content/structure/kafedra-obrazotvorchogo-mystectva/exhibitions.uk.json`.

Каталог «Байки Харківські» лежить у `files/` як є; RENAISSANCE (181 МБ) у git не йде — в карті
він з `drive_id`, його качає `push_assets.py`.

Pillow тут немає, тож через контейнер:

    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONPATH=/tmp/pil \\
      -v "$PWD/..:/m" -w /m/fixes-2026-10-08-exhibitions python:3.12-slim \\
      sh -c 'pip install -q --target /tmp/pil Pillow && python3 build.py'

Ідемпотентний: готові файли пропускаються.
"""

from __future__ import annotations

import html
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

from bundle import CACHE, FILES, HERE, JPEG_QUALITY, MAX_SIDE, file_id, save_map, slugify

UA = 'Mozilla/5.0'
OLD_SITE = 'https://old.hnpu.edu.ua'
OUT = HERE / 'data' / 'exhibitions.uk.json'

# Назви лінків узяті з обкладинок PDF: у самих файлів текстового шару немає. Третє поле — `drive_id`
# для файла, якого немає в git: RENAISSANCE важить 181 МБ, а ліміт GitHub — 100 МБ.
CATALOGS = [
    ('renaissance-catalog-2022.pdf',
     'RENAISSANCE. Каталог виставки студентів кафедри образотворчого мистецтва ХНПУ імені '
     'Г. С. Сковороди (Харків, 2022)',
     '1RNSstrtfREFUOSxMoAsJewQ_v4vSDSqz'),
    ('bajky-kharkivski-2021.pdf', 'Григорій Сковорода. Байки Харківські (2021)', None),
]


def fetch(url: str, key: str) -> bytes:
    cached = CACHE / key
    if cached.exists() and cached.stat().st_size > 0:
        return cached.read_bytes()
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=300) as response:
        body = response.read()
    if body[:15].lstrip().lower().startswith((b'<!doctype', b'<html')):
        raise OSError(f'{url}: віддано HTML-сторінку замість файла')
    CACHE.mkdir(exist_ok=True)
    cached.write_bytes(body)
    return body


def drive(drive_id: str) -> bytes:
    return fetch(f'https://drive.usercontent.google.com/download?id={drive_id}&export=download', drive_id)


def old_site(path: str) -> bytes:
    return fetch(OLD_SITE + path, 'old-' + slugify(urllib.parse.unquote(path)))


def is_mp4(raw: bytes) -> bool:
    return raw[4:8] == b'ftyp'


def compress(raw: bytes, name: str) -> None:
    target = FILES / name
    if target.exists():
        return
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
        image = image.convert('RGBA')
        flat = Image.new('RGB', image.size, 'white')
        flat.paste(image, mask=image.split()[-1])
        image = flat
    else:
        image = image.convert('RGB')
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    FILES.mkdir(exist_ok=True)
    image.save(target, 'JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True)


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def link(fid: str, inner: str) -> str:
    return f'<a href="/assets/{fid}" target="_blank" rel="noopener noreferrer">{inner}</a>'


def figure(picture: str, caption_html: str) -> str:
    return f'<figure>{picture}<figcaption>{caption_html}</figcaption></figure>'


def img(fid: str, alt: str) -> str:
    return f'<img src="/assets/{fid}" loading="lazy" alt="{html.escape(alt)}" />'


def build_google_sites(key: str, group: dict, mapping: dict[str, dict]) -> str:
    figures = []
    for n, item in enumerate(group['items'], 1):
        caption = item['caption']
        stem = f'exh-{key}-{n:02d}-{slugify(caption.split(",")[0])}'
        target = drive(item['target'])
        if is_mp4(target):
            video, still = f'{stem}.mp4', f'{stem}-preview.jpg'
            compress(drive(item['preview']), still)
            mapping[file_id(video)] = {'name': video, 'drive_id': item['target']}
            mapping[file_id(still)] = {'name': still}
            tail = ' (анімація)'
            if caption.endswith(tail):
                label = esc(caption[:-len(tail)]) + ' ' + link(file_id(video), '(анімація)')
            else:
                label = esc(caption)
            figures.append(figure(link(file_id(video), img(file_id(still), caption)), label))
        else:
            name = f'{stem}.jpg'
            compress(target, name)
            mapping[file_id(name)] = {'name': name}
            figures.append(figure(link(file_id(name), img(file_id(name), caption)), esc(caption)))
    return details(group['summary'], [
        f'<p><strong>{esc(group["subtitle"])}</strong></p>',
        '<div class="photo-grid gallery">' + ''.join(figures) + '</div>',
    ])


def build_legacy(key: str, group: dict, mapping: dict[str, dict]) -> str:
    intro, *rest = group['intro']
    portrait = f'exh-{key}-00-portrait.jpg'
    compress(old_site(group['portrait']), portrait)
    mapping[file_id(portrait)] = {'name': portrait}
    figures = []
    for n, item in enumerate(group['items'], 1):
        title, *details_lines = item['caption_lines']
        name = f'exh-{key}-{n:02d}-{slugify(title)[:40].strip("-")}.jpg'
        compress(old_site(item['url']), name)
        mapping[file_id(name)] = {'name': name}
        caption = '<br />'.join(esc(line) for line in item['caption_lines'])
        figures.append(figure(link(file_id(name), img(file_id(name), title)), caption))
    return details(group['summary'], [
        f'<p>{esc(intro)}</p>',
        f'<p>{img(file_id(portrait), "Чжен Сяндун")}</p>',
        *[f'<p>{esc(paragraph)}</p>' for paragraph in rest],
        '<div class="photo-grid gallery">' + ''.join(figures) + '</div>',
    ])


def details(summary: str, blocks: list[str]) -> str:
    return f'<details><summary><strong>{esc(summary)}</strong></summary>\n\n' + '\n\n'.join(blocks) + '\n\n</details>'


def main() -> int:
    spec = json.loads((HERE / 'exhibitions.json').read_text(encoding='utf-8'))
    mapping: dict[str, dict] = {}

    items = []
    for name, label, catalog_drive_id in CATALOGS:
        if catalog_drive_id:
            mapping[file_id(name)] = {'name': name, 'drive_id': catalog_drive_id}
        elif (FILES / name).exists():
            mapping[file_id(name)] = {'name': name}
        else:
            print(f'  ! {name}: файла немає в files/', file=sys.stderr)
            return 1
        items.append(f'<li>{link(file_id(name), esc(label))}</li>')
    blocks = ['<ul>\n' + '\n'.join(items) + '\n</ul>']

    groups = spec['groups']
    blocks.append(build_google_sites('nezlamni', groups['nezlamni'], mapping))
    blocks.append(build_google_sites('promenade', groups['promenade'], mapping))
    blocks.append(build_legacy('mbk', groups['mbk'], mapping))

    save_map(mapping)
    OUT.parent.mkdir(exist_ok=True)
    body = {
        'sections': [{'html': '\n\n'.join(blocks)}],
        'sourceUrls': [group['source'] for group in groups.values()],
        'capturedAt': '2026-10-08',
    }
    OUT.write_text(json.dumps(body, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    kinds = {'.jpg': 0, '.mp4': 0, '.pdf': 0}
    for meta in mapping.values():
        kinds[Path(meta['name']).suffix] += 1
    print(f'карта: {len(mapping)} файлів {kinds}; тіло вкладки: {OUT.stat().st_size // 1024} КБ',
          file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
