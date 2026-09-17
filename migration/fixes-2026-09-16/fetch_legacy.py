#!/usr/bin/env python3
"""
Перенести сторінки зі старого сайту (old.hnpu.edu.ua), які правки 16.09 просять повернути.

Для кожної сторінки: тіло статті → той самий прибиральник, що й у structure-pages
(`clean_body`), таблиці-фотогалереї → сітка карток, зображення → стиснуті копії в `files/` з
детермінованим uuid. Результат — `data/legacy/<key>.html` з `/assets/<uuid>`, який далі
вставляється в статичний контент фронту.

    python3 fetch_legacy.py              # усі сторінки
    python3 fetch_legacy.py art-life …   # вибрані
"""

from __future__ import annotations

import html
import importlib.util
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bundle import HERE, add_file, add_image, load_map, save_map

MIGRATION = HERE.parent
sys.path.insert(0, str(MIGRATION / 'pass2'))

from gridify_photo_tables import convert as gridify  # noqa: E402

_spec = importlib.util.spec_from_file_location('transform', MIGRATION / 'structure-pages' / '2_transform.py')
_transform = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_transform)
clean_body = _transform.clean_body

OLD = 'https://old.hnpu.edu.ua'
CACHE = HERE / '.cache'
OUT = HERE / 'data' / 'legacy'
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh) knpu-migration'}

PAGES: dict[str, str] = {
    # Кафедра образотворчого мистецтва — блоки під відео на головній і випускники.
    'art-life': '/uk/nashe-zhyttya',
    'art-diplomas': '/uk/diplomni-roboty-vypusknykiv-kafedry-obrozotvorchogo-mystectva',
    'art-semester': '/uk/semestrovi-roboty-studentiv-kafedry-obrazotvorche-mystectvo',
    'art-graduates': '/uk/division/vypusknyky-kafedry-obrazotvorchogo-mystectva',
    # Центр ментального здоров'я — вкладка «Валеоклуб».
    'mental-valeoclub': '/uk/studentskyy-naukovyy-valeologichnyy-klub',
    # Меню «Наука» (правка 16.09, п. 2): жовті пункти — сторінки старого сайту, які переносимо.
    'sci-bibliographic-indexes': '/uk/bibliografichni-pokazhchyky-naukovoyi-biblioteky-hnpu-imeni-g-s-skovorody',
    'sci-notable-scientists': '/uk/naukovi-praci-profesoriv-hnpu-imeni-g-s-skovorody',
    'sci-inexhaustible-treasure': '/uk/nevycherpnyy-skarb',
    'sci-library-projects': '/uk/proyekty-naukovoyi-biblioteky-hnpu-imeni-gsskovorody',
    'sci-scientometric-databases': '/uk/division/dostup-do-mizhnarodnyh-naukometrychnyh-baz',
    'sci-rankings': '/uk/pokaznyky-reytynguvannya-universytetu',
    'sci-grants': '/uk/grantova-ta-proyektna-diyalnist',
    'sci-publication-activity': '/uk/publikaciyna-aktyvnist-naukovo-pedagogichnyh-pracivnykiv-universytetu',
    'sci-publishing-regulations': '/uk/division/normatyvna-dokumentaciya-redakciyno-vydavnychogo-viddilu',
    'sci-events': '/uk/division/naukovi-zahody',
}

BODY_RE = re.compile(
    r'<div class="field field-name-body.*?<div class="field-item even"[^>]*>(.*?)</div>\s*</div>\s*</div>',
    re.S,
)
DOC_EXT = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.rtf')


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def cached(url: str) -> Path:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / re.sub(r'[^A-Za-z0-9._-]+', '_', urllib.parse.unquote(url))[-150:]
    if not path.exists():
        path.write_bytes(fetch(url))
    return path


def to_old(url: str) -> str:
    """Посилання на hnpu.edu.ua/sites/… тепер живуть лише на old.hnpu.edu.ua."""
    parts = urllib.parse.urlsplit(url)
    if parts.netloc in ('hnpu.edu.ua', 'www.hnpu.edu.ua', 'old.hnpu.edu.ua'):
        path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe='/')
        return f'{OLD}{path}'
    return url


def local_name(key: str, url: str) -> str:
    stem = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).stem
    stem = re.sub(r'[^A-Za-z0-9]+', '-', stem).strip('-').lower()[:60] or 'file'
    return f'{key}-{stem}'


GALLERIES = {'art-life', 'art-diplomas', 'art-semester'}
TAG_RE = re.compile(r'<[^>]+>')


def as_gallery(body: str) -> str:
    """
    Сторінки-галереї старого сайту — таблиці, де під рядком фото йде рядок підписів, плюс
    розсипані `<img>` поза таблицями. Усе це стає однією сіткою карток у початковому порядку.
    """
    figures: list[str] = []
    for chunk in re.split(r'(<table\b.*?</table>)', body, flags=re.S):
        if not chunk.startswith('<table'):
            figures += [f'<figure>{img}</figure>' for img in re.findall(r'<img\b[^>]*>', chunk)]
            continue
        rows = [re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S)
                for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', chunk, re.S)]
        for index, row in enumerate(rows):
            if not any('<img' in cell for cell in row):
                continue
            below = rows[index + 1] if index + 1 < len(rows) else []
            captions_row = below if below and not any('<img' in cell for cell in below) else []
            for column, cell in enumerate(row):
                for img in re.findall(r'<img\b[^>]*>', cell):
                    text = TAG_RE.sub(' ', cell) or ''
                    if column < len(captions_row):
                        text += ' ' + TAG_RE.sub(' ', captions_row[column])
                    text = re.sub(r'\s+', ' ', text).strip()
                    caption = f'<figcaption>{text}</figcaption>' if text else ''
                    figures.append(f'<figure>{img}{caption}</figure>')
    return f'<div class="photo-grid gallery">{"".join(figures)}</div>'


def convert_page(key: str, path: str, mapping: dict[str, dict]) -> str:
    page = cached(OLD + path).read_text(encoding='utf-8', errors='replace')
    match = BODY_RE.search(page)
    if not match:
        raise SystemExit(f'{key}: тіла статті не знайдено')
    body, _images = clean_body(match.group(1))
    if key not in GALLERIES:
        body, _grids = gridify(body)

    def swap_img(m: re.Match[str]) -> str:
        src = html.unescape(m.group(1))
        if not re.search(r'hnpu\.edu\.ua/sites/', src):
            return m.group(0)
        try:
            source = cached(to_old(src))
        except urllib.error.HTTPError as exc:
            print(f'    ! {src}: {exc.code}, зображення пропущено', file=sys.stderr)
            return m.group(0).replace(m.group(1), '')
        asset = add_image(source, local_name(key, src) + '.jpg', mapping)
        return m.group(0).replace(m.group(1), asset)

    def swap_doc(m: re.Match[str]) -> str:
        href = html.unescape(m.group(1))
        if not re.search(r'hnpu\.edu\.ua/sites/', href) or not href.lower().endswith(DOC_EXT):
            return m.group(0)
        suffix = Path(urllib.parse.urlsplit(href).path).suffix.lower()
        try:
            source = cached(to_old(href))
        except urllib.error.HTTPError as exc:
            print(f'    ! {href}: {exc.code}, посилання лишається на старий сайт', file=sys.stderr)
            return m.group(0).replace(m.group(1), to_old(href))
        name = local_name(key, href) + suffix
        asset = add_file(source, name, mapping)
        # Документи старого сайту важать сотні мегабайт — у git їх немає, push_assets.py качає
        # їх зі старого сайту за цією адресою.
        mapping[asset.split('/')[-1]]['url'] = to_old(href)
        return m.group(0).replace(m.group(1), asset)

    body = re.sub(r'<img[^>]*\bsrc="([^"]+)"', swap_img, body)
    body = re.sub(r'<a[^>]*\bhref="([^"]+)"', swap_doc, body)
    body = re.sub(r'<img[^>]*\bsrc=""[^>]*>', '', body)
    # Внутрішні посилання старого сайту: hnpu.edu.ua тепер новий сайт, стара сторінка — на old.
    body = re.sub(r'https?://(?:www\.)?hnpu\.edu\.ua/(uk/|sites/|division/|node/)', r'https://old.hnpu.edu.ua/\1', body)
    return as_gallery(body) if key in GALLERIES else body


def main(argv: list[str]) -> int:
    keys = argv or list(PAGES)
    mapping = load_map()
    OUT.mkdir(parents=True, exist_ok=True)
    for key in keys:
        body = convert_page(key, PAGES[key], mapping)
        (OUT / f'{key}.html').write_text(body + '\n', encoding='utf-8')
        print(f'  {key}: {len(body)} симв., {body.count("/assets/")} файлів', file=sys.stderr)
    save_map(mapping)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
