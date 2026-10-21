#!/usr/bin/env python3
"""
Правки 20.10, п. 2 (Наукова бібліотека): перенести на `/science/bibliographic-indexes` покажчики
2017, 2018 і 2019 років зі старої сторінки
https://old.hnpu.edu.ua/uk/bibliografichni-pokazhchyky-naukovoyi-biblioteky-hnpu-imeni-g-s-skovorody

Скрипт:
  1. качає стару сторінку (або бере `--html`) і розбирає блоки 2019 → 2017 на рядки;
  2. пише `files.map.json` (PDF зі старого сайту, `url` у карті — їх заливає `push_assets.py`);
  3. збирає розмітку в тому ж вигляді, що блок 2020 року на сторінці (кожен рядок УДК / ББК / шифр
     і кожен опис — у власному `<p>`, номер пункту в одному рядку з УДК, заголовки років —
     `<hr /><p><strong>…</strong></p>`), і перевіряє її;
  4. з `--apply` вписує блок у `science-bibliographic-indexes.uk.json` фронта.

Текст переноситься дослівно, схлопуються лише подвійні пробіли. Без `--apply` нічого не пише,
крім карти файлів.

    python3 build.py            # перевірка + карта файлів
    python3 build.py --apply    # те саме + запис у JSON фронта
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser

from bundle import FE_PAGE, FILES_MAP, file_id, save_map

OLD_PAGE = ('https://old.hnpu.edu.ua/uk/bibliografichni-pokazhchyky-naukovoyi-biblioteky-hnpu-'
            'imeni-g-s-skovorody')
OLD_FILES = 'https://old.hnpu.edu.ua/sites/default/files/files/biblioteka/'
UA = 'Mozilla/5.0'

# Перший рік блока й останній файл, на якому розбір зупиняється (далі на старій сторінці — меню).
FIRST_YEAR_MARK = re.compile(r'2019 році:')
LAST_LINK_PART = 'inkluzivna'

# Файл покажчика Лозової (2019) на старому сайті віддає 404. 21.10 клієнт надіслав його сам:
# лежить у `files/` (у git), у карті без `url`.
FROM_CLIENT = {'lozova_biobibliograf.pdf'}

YEARS = ('2019', '2018', '2017')


class Lines(HTMLParser):
    """Блочні елементи старої сторінки → рядки `(текст, href першого посилання)`."""

    BLOCKS = {'div', 'p', 'br', 'hr', 'li'}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[tuple[str, str | None]] = []
        self._text: list[str] = []
        self._href: str | None = None
        self.done = False

    def _flush(self) -> None:
        text = re.sub(r'\s+', ' ', ''.join(self._text).replace('\xa0', ' ')).strip()
        if text and not self.done:
            self.lines.append((text, self._href))
            if self._href and LAST_LINK_PART in self._href:
                self.done = True
        self._text, self._href = [], None

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKS:
            self._flush()
        elif tag == 'a' and self._href is None:
            self._href = dict(attrs).get('href')

    def handle_endtag(self, tag):
        if tag in self.BLOCKS:
            self._flush()

    def handle_data(self, data):
        self._text.append(data)


def fetch_old_page() -> str:
    request = urllib.request.Request(OLD_PAGE, headers={'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode('utf-8')


def old_lines(page: str) -> list[tuple[str, str | None]]:
    match = FIRST_YEAR_MARK.search(page)
    if not match:
        raise SystemExit('на старій сторінці не знайдено заголовок 2019 року')
    start = page.rfind('<div', 0, match.start())
    parser = Lines()
    parser.feed(page[start:])
    parser.close()
    if not parser.done:
        raise SystemExit('розбір не дійшов до останнього покажчика 2017 року')
    return parser.lines


def old_file_name(href: str) -> str:
    return href.rsplit('/', 1)[-1]


def map_name(old_name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', re.sub(r'\.pdf$', '', old_name, flags=re.I).lower())
    return f'sci-bibliographic-indexes-{slug.strip("-")}.pdf'


def build_block(lines) -> tuple[str, dict[str, dict]]:
    """Розмітка блоку 2019 → 2017 та карта файлів для `push_assets.py`."""
    mapping: dict[str, dict] = {}
    out: list[str] = []
    year_heading = re.compile(r'^Бібліографічні покажчики, складені .* у (\d{4}) році:$')
    subheading = re.compile(r'^[\w\- ]+ покажчики:$')
    seen_years: list[str] = []

    for text, href in lines:
        escaped = html.escape(text, quote=False)
        if match := year_heading.match(text):
            seen_years.append(match.group(1))
            out.append(f'<hr /><p><strong>{escaped}</strong></p>')
        elif href is None and subheading.match(text):
            out.append(f'<p><strong>{escaped}</strong></p>')
        elif href is None:
            out.append(f'<p>{escaped}</p>')
        else:
            old_name = old_file_name(href)
            name = map_name(old_name)
            mapping[file_id(name)] = ({'name': name} if old_name in FROM_CLIENT
                                      else {'name': name, 'url': OLD_FILES + old_name})
            out.append(f'<p><a href="/assets/{file_id(name)}">{escaped}</a></p>')

    if tuple(seen_years) != YEARS:
        raise SystemExit(f'очікував заголовки {YEARS}, а на сторінці {tuple(seen_years)}')
    return '\n'.join(out), mapping


class Checker(HTMLParser):
    """Перевірка розмітки: баланс <p>, текст поза <p>, «осиротілі» номери пунктів."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.assets: list[str] = []
        self._open: list[str] = []
        self._p_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == 'br':
            return
        if tag == 'hr':
            if self._open:
                self.problems.append(f'<hr> усередині <{self._open[-1]}>')
            return
        if tag == 'p' and 'p' in self._open:
            self.problems.append('вкладений <p>: попередній не закрито')
        if tag == 'a':
            href = dict(attrs).get('href') or ''
            if href.startswith('/assets/'):
                self.assets.append(href.removeprefix('/assets/'))
        self._open.append(tag)
        if tag == 'p':
            self._p_text = []

    def handle_endtag(self, tag):
        if tag in ('hr', 'br'):  # void-теги: `<hr />` парсер віддає як start + end
            return
        if tag not in self._open:
            self.problems.append(f'зайвий </{tag}>')
            return
        while self._open and self._open[-1] != tag:
            self.problems.append(f'<{self._open.pop()}> не закрито перед </{tag}>')
        self._open.pop()
        if tag == 'p':
            text = ''.join(self._p_text).strip()
            if re.fullmatch(r'\d+\)\.?', text):
                self.problems.append(f'номер пункту окремо від УДК: «{text}»')

    def handle_data(self, data):
        if 'p' in self._open:
            self._p_text.append(data)
        elif data.strip():
            self.problems.append(f'текст поза <p>: «{data.strip()[:50]}»')

    def finish(self) -> list[str]:
        self.close()
        problems = list(self.problems)
        problems += [f'<{tag}> не закрито' for tag in self._open]
        return problems


def check(markup: str) -> Checker:
    checker = Checker()
    checker.feed(markup)
    checker.problems = checker.finish()
    return checker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--html', help='збережена стара сторінка замість завантаження')
    parser.add_argument('--apply', action='store_true', help='записати блок у JSON фронта')
    args = parser.parse_args()

    page = open(args.html, encoding='utf-8').read() if args.html else fetch_old_page()
    block, mapping = build_block(old_lines(page))

    checker = check(block)
    unknown = [uuid for uuid in checker.assets if uuid not in mapping]
    print(f'блок: {len(block.splitlines())} рядків · {len(checker.assets)} посилань на файли · '
          f'{len(mapping)} файлів у карті', file=sys.stderr)
    if checker.problems or unknown:
        for problem in checker.problems:
            print(f'  ! {problem}', file=sys.stderr)
        for uuid in unknown:
            print(f'  ! посилання на файл поза картою: {uuid}', file=sys.stderr)
        return 1

    save_map(mapping)
    print(f'карту записано: {FILES_MAP}', file=sys.stderr)

    data = json.loads(FE_PAGE.read_text(encoding='utf-8'))
    body = data['sections'][0]['html']
    if re.search(r'2018 році:</strong></p>', body):
        # Блок уже на сторінці (правки 20.10): лише обгортаємо в посилання описи файлів від клієнта.
        patched = body
        for uuid, meta in mapping.items():
            if 'url' in meta:
                continue
            link = next(line for line in block.splitlines() if f'/assets/{uuid}' in line)
            plain = '<p>' + re.sub(r'^<p><a [^>]*>|</a></p>$', '', link) + '</p>'
            if f'/assets/{uuid}' in patched:
                continue
            if patched.count(plain) != 1:
                raise SystemExit(f'опис «{meta["name"]}» на сторінці не знайдено рівно один раз')
            patched = patched.replace(plain, link)
        page_check = check(patched)
        print('перевірка сторінки загалом:', file=sys.stderr)
        for problem in page_check.problems or ['без зауважень']:
            print(f'  · {problem}', file=sys.stderr)
        if args.apply and patched != body:
            data['sections'][0]['html'] = patched
            FE_PAGE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
            print(f'записано: {FE_PAGE}', file=sys.stderr)
        elif patched == body:
            print('сторінка вже містить блок і посилання — нічого не змінюю', file=sys.stderr)
        return 0

    # Хвіст сторінки до правки: «…Фрізман</a>\n<hr /><strong>…у 2019 році:</strong></p>» — <p>
    # Фрізмана не закрито, а заголовок 2019 року без власного <p>. Відрізаємо цей заголовок і
    # закриваємо <p>, далі йде повний блок із коректним заголовком.
    cut = body.rfind('<hr />')
    if cut < 0 or '2019 році:' not in body[cut:] or body[cut:].count('<a ') > 0:
        raise SystemExit('хвіст сторінки не схожий на очікуваний — перевір вручну')
    new_body = body[:cut].rstrip() + '</p>\n' + block
    page_check = check(new_body)

    print('перевірка сторінки загалом:', file=sys.stderr)
    for problem in page_check.problems or ['без зауважень']:
        print(f'  · {problem}', file=sys.stderr)

    if not args.apply:
        print('без --apply JSON фронта не змінено', file=sys.stderr)
        return 0
    data['sections'][0]['html'] = new_body
    FE_PAGE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'записано: {FE_PAGE}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
