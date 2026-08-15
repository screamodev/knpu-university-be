#!/usr/bin/env python3
"""
Причесати вже перенесений статичний контент фронтенду.

Міграція лишила у текстах сліди старих движків: джумлівські маркери `{spoiler title=… opened=0}`
замість списків файлів, уламки атрибутів (`width="200" loading="lazy" />`) як звичайний текст,
порожні `<a></a>`, зелені банери-«кнопки» старого сайту й покликання на hnpu.edu.ua /
smc.hnpu.edu.ua, які вже нікуди не ведуть.

Скрипт править `app/content/pages/*.json` і `app/content/structure/**/*.json` на місці
(усі значення ключа `html`), ідемпотентно: повторний прогін нічого не змінює.

    python3 tidy_legacy_html.py                 # dry-run зі звітом
    python3 tidy_legacy_html.py --write
    python3 tidy_legacy_html.py --write --only 'quality-centre-*'

Покликання на файли (`…/sites/…/*.pdf`) не чіпаються — це робота mirror_page_files.py.
"""

from __future__ import annotations

import argparse
import fnmatch
import html as html_mod
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).parent
CONTENT = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content'
UNITS_MAP = HERE.parent / 'structure-pages' / 'units.map.json'

# Тільки самі старі сайти. Піддомени (`lms.`, `catalog.`, `library.`, `dspace.`) — це живі
# сервіси університету, їхні покликання лишаються як є.
LEGACY_HOSTS = ('hnpu.edu.ua', 'www.hnpu.edu.ua', 'smc.hnpu.edu.ua')

FILE_EXT_RE = re.compile(r'\.(pdf|docx?|xlsx?|pptx?|rtf|odt|zip|rar|jpe?g|png|gif)$', re.I)

SPOILER_RE = re.compile(r'\{spoiler\s*(?P<attrs>[^}]*)\}(?P<inner>.*?)\{\s*/\s*spoiler\s*\}',
                        re.S | re.I)
STRAY_SPOILER_RE = re.compile(r'\{\s*/?\s*spoiler[^}]*\}', re.I)
TITLE_RE = re.compile(r'title\s*=\s*(?P<title>.*?)\s*(?:\bopened\s*=\s*\S*\s*)?$', re.S | re.I)
LINK_RE = re.compile(r'<a\s[^>]*href="(?P<href>[^"]*)"[^>]*>(?P<text>.*?)</a>', re.S)
BANNER_ANCHOR_RE = re.compile(
    r'<a\s[^>]*href="(?P<href>[^"]*)"[^>]*>\s*<img\b[^>]*alt="(?P<alt>Knopka[^"]*)"[^>]*>\s*</a>',
    re.I)
BANNER_IMG_RE = re.compile(r'<img\b[^>]*alt="(?P<alt>Knopka[^"]*)"[^>]*>', re.I)
EMPTY_ANCHOR_RE = re.compile(r'<a\b[^>]*>\s*</a>')
JS_ANCHOR_RE = re.compile(r'<a\s[^>]*href="javascript:[^"]*"[^>]*>(?P<text>.*?)</a>', re.S | re.I)
# Уламок відкритого тега, що лишився у тексті: `… width="200" loading="lazy" />`.
ATTR_JUNK_RE = re.compile(r'\s*(?:\b[a-zA-Z-]+="[^"<>]*"\s*)+/?>')
# Службові слова всередині спойлера — самі по собі не є змістом.
FILLER_WORDS = ('завантаження', 'завантажити', 'переглянути', 'детальніше', 'докладніше')

MARK_OPEN, MARK_CLOSE = '\x01LI\x01', '\x02LI\x02'


def _load_tidy():
    """`tidy()` з structure-pages/2_transform.py — той самий прибиральник порожніх абзаців."""
    spec = importlib.util.spec_from_file_location(
        'legacy_transform', HERE.parent / 'structure-pages' / '2_transform.py')
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module.tidy


tidy = _load_tidy()


# ── таблиці ──────────────────────────────────────────────────────────────────────────────────

def load_buttons() -> dict[str, dict[str, str]]:
    return json.loads((HERE / 'data' / 'legacy_buttons.json').read_text(encoding='utf-8'))['buttons']


def load_link_map(content: Path) -> dict[str, str]:
    """
    Ручна таблиця + підрозділи з units.map.json (`division/<alias>` → сторінка підрозділу).

    Плюс збіг «у лоб»: на старому сайті багато кафедр мали адресу `division/<той самий slug>`,
    що й сторінка в нас, — беремо назви тек `app/content/structure/<slug>`, бо саме вони
    гарантовано мають сторінку.
    """
    links = dict(json.loads((HERE / 'data' / 'legacy_links.json').read_text(encoding='utf-8'))['links'])
    units = json.loads(UNITS_MAP.read_text(encoding='utf-8'))['units']
    for slug, unit in units.items():
        for alias in unit.get('legacy') or []:
            links.setdefault(alias.strip('/'), f'/university/structure/{slug}')
    for unit_dir in sorted((content / 'structure').glob('*/')):
        links.setdefault(f'division/{unit_dir.name}', f'/university/structure/{unit_dir.name}')
    return links


# ── дрібні прибирання ────────────────────────────────────────────────────────────────────────

def strip_tags(markup: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', markup)).strip()


def map_text_nodes(markup: str, fn) -> str:
    """Застосувати `fn` лише до текстових вузлів, не чіпаючи самих тегів."""
    parts = re.split(r'(<[^>]*>)', markup)
    return ''.join(part if part.startswith('<') else fn(part) for part in parts)


def drop_attr_junk(markup: str) -> tuple[str, int]:
    hits = 0

    def clean(text: str) -> str:
        nonlocal hits
        new, count = ATTR_JUNK_RE.subn('', text)
        hits += count
        return new

    return map_text_nodes(markup, clean), hits


EMPTY_TAG_RE = re.compile(
    r'<(?P<tag>strong|em|b|i|u|span|p|h[2-6])\b[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</(?P=tag)>')


def drop_empty_blocks(markup: str) -> str:
    """Після прибирання банерів лишаються порожні `<p><strong></strong></p>` — теж сміття."""
    previous = None
    while previous != markup:
        previous = markup
        markup = EMPTY_TAG_RE.sub('', markup)
    return markup


def drop_orphan_tags(markup: str, tag: str) -> str:
    """
    Прибрати теги без пари. Джумла лишала маркер `{/spoiler}` усередині покликання, а самі
    спойлери перетинали межі абзаців, тож після згортання в списки лишаються самі `</a>` і `</p>`.
    """
    pattern = re.compile(rf'<{tag}\b[^>]*>|</{tag}>', re.I)
    open_stack: list[tuple[int, int]] = []
    orphans: list[tuple[int, int]] = []
    for tag_match in pattern.finditer(markup):
        if tag_match.group(0).startswith('</'):
            if open_stack:
                open_stack.pop()
            else:
                orphans.append(tag_match.span())
        else:
            open_stack.append(tag_match.span())
    for start, end in sorted(orphans + open_stack, reverse=True):
        markup = markup[:start] + markup[end:]
    return markup


def drop_empty_anchors(markup: str) -> tuple[str, int]:
    markup, unwrapped = JS_ANCHOR_RE.subn(lambda m: m.group('text'), markup)
    markup, dropped = EMPTY_ANCHOR_RE.subn('', markup)
    return markup, unwrapped + dropped


# ── вбудовані документи ──────────────────────────────────────────────────────────────────────

# Опубліковані Google-презентації та документи: на старому сайті вони стояли в <iframe>, але при
# перенесенні лишилися голим покликанням, і сторінка показувала довгий URL замість слайдів.
EMBED_LINK_RE = re.compile(
    r'<a\s[^>]*href="(?P<href>https://(?:docs|drive)\.google\.com/[^"]*?(?:pubembed|/preview)[^"]*)"[^>]*>'
    r'(?P<label>.*?)</a>', re.S)


def restore_embeds(markup: str) -> tuple[str, int]:
    def replace(match: re.Match[str]) -> str:
        href = html_mod.unescape(match.group('href'))
        label = strip_tags(match.group('label'))
        # Покликання з осмисленою назвою лишаємо покликанням — вбудовуємо лише «голі» адреси.
        if label and not label.startswith('http'):
            return match.group(0)
        return (f'<iframe src="{html_mod.escape(href, quote=True)}" '
                f'frameborder="0" allowfullscreen></iframe>')

    return EMBED_LINK_RE.subn(replace, markup)


# ── спойлери → списки файлів ─────────────────────────────────────────────────────────────────

def spoiler_item(match: re.Match[str]) -> str:
    title_match = TITLE_RE.search(match.group('attrs') or '')
    title = strip_tags(title_match.group('title') if title_match else '') or 'Файл'
    title = html_mod.escape(html_mod.unescape(title), quote=False)

    inner = re.sub(r'</?p[^>]*>|<br\s*/?>', ' ', match.group('inner') or '')
    links: list[str] = []
    for link in LINK_RE.finditer(inner):
        href = link.group('href')
        if href and href not in links:
            links.append(href)

    rest = strip_tags(LINK_RE.sub(' ', inner)).replace('\xa0', ' ').strip(' .,;:—-')
    meaningful = rest and rest.lower() not in FILLER_WORDS

    if links and not meaningful:
        parts = [f'<a href="{links[0]}">{title}</a>']
        parts += [f'<a href="{href}">файл {index}</a>' for index, href in enumerate(links[1:], 2)]
        return f'{MARK_OPEN}<li>{" ".join(parts)}</li>{MARK_CLOSE}'

    body = re.sub(r'\s{2,}', ' ', inner).strip()
    if body:
        return f'{MARK_OPEN}<li><strong>{title}</strong> {body}</li>{MARK_CLOSE}'
    return f'{MARK_OPEN}<li>{title}</li>{MARK_CLOSE}'


# Порожня «склейка» між сусідніми спойлерами: залишки абзаців і форматування.
BETWEEN_RE = re.compile(
    rf'{re.escape(MARK_CLOSE)}'
    r'(?:\s|&nbsp;|</?p[^>]*>|<br\s*/?>|</a>|<a\b[^>]*>|'
    r'<(?:em|strong|b|i|span)>\s*</(?:em|strong|b|i|span)>)*'
    rf'{re.escape(MARK_OPEN)}')


def convert_spoilers(markup: str) -> tuple[str, int]:
    if '{spoiler' not in markup.lower():
        return STRAY_SPOILER_RE.subn('', markup)

    markup, count = SPOILER_RE.subn(spoiler_item, markup)
    markup = drop_orphan_tags(markup, 'a')
    previous = None
    while previous != markup:
        previous = markup
        markup = BETWEEN_RE.sub('', markup)
    markup = markup.replace(MARK_OPEN, '<ul class="legacy-files">').replace(MARK_CLOSE, '</ul>')
    # Список не має жити всередині абзацу — знімаємо обгортку, що лишилася від Джумли.
    wrapped = re.compile(r'<p[^>]*>((?:(?!</?p\b).)*?<ul class="legacy-files">(?:(?!</?p\b).)*?)</p>',
                         re.S)
    previous = None
    while previous != markup:
        previous = markup
        markup = wrapped.sub(r'\1', markup)
    markup, stray = STRAY_SPOILER_RE.subn('', markup)
    return drop_orphan_tags(markup, 'p'), count + stray


# ── банери ───────────────────────────────────────────────────────────────────────────────────

def convert_banners(markup: str, buttons: dict[str, dict[str, str]]) -> tuple[str, int, int]:
    kept = dropped = 0

    def render(alt: str) -> str:
        nonlocal kept, dropped
        button = buttons.get(alt.strip())
        if button:
            kept += 1
            label = html_mod.escape(button['label'], quote=False)
            return f'<a class="legacy-btn" href="{button["href"]}">{label}</a>'
        dropped += 1
        return ''

    markup = BANNER_ANCHOR_RE.sub(lambda m: render(m.group('alt')), markup)
    markup = BANNER_IMG_RE.sub(lambda m: render(m.group('alt')), markup)
    return markup, kept, dropped


# ── покликання на старі сайти ────────────────────────────────────────────────────────────────

def legacy_key(href: str) -> str | None:
    """`http://hnpu.edu.ua/uk/division/x` → `division/x`; smc-адреси з префіксом `smc/`."""
    parts = urlsplit(html_mod.unescape(href))
    host = parts.netloc.lower()
    if host not in LEGACY_HOSTS:
        return None
    path = unquote(parts.path).strip('/')
    # Частина покликань на старому сайті двічі закодована: `/uk/http%3A//hnpu.edu.ua/uk/…`.
    inner = re.search(r'https?://([^/]+)/(.*)$', path)
    if inner:
        if inner.group(1).lower() not in LEGACY_HOSTS:
            return None
        host, path = inner.group(1).lower(), inner.group(2).strip('/')
    if host == 'smc.hnpu.edu.ua':
        return f'smc/{path}' if path else 'smc'
    segments = path.split('/')
    if segments and segments[0] in ('uk', 'en'):
        segments = segments[1:]
    return '/'.join(segments)


def lookup(key: str, link_map: dict[str, str]) -> str | None:
    """Точний збіг, далі — найдовший префікс (розділи smc мали десятки підсторінок)."""
    if key in link_map:
        return link_map[key]
    segments = key.split('/')
    for cut in range(len(segments) - 1, 0, -1):
        prefix = '/'.join(segments[:cut])
        if prefix in link_map:
            return link_map[prefix]
    return None


BARE_URL_RE = re.compile(r'https?://[^\s"<>]*hnpu\.edu\.ua[^\s"<>]*')
DOUBLE_SCHEME_RE = re.compile(r'https?://(?=https?://)')


def rewrite_bare_urls(markup: str, link_map: dict[str, str]) -> tuple[str, int]:
    """
    Адреса старого сайту, набрана просто текстом («…можна за посиланням: http://smc…/node/41»).
    Є відповідник — робимо покликання, немає — прибираємо адресу разом із «порожнім» хвостом.
    """
    changed = 0

    def clean(text: str) -> str:
        nonlocal changed

        def replace(match: re.Match[str]) -> str:
            nonlocal changed
            url = match.group(0)
            key = legacy_key(url)
            if key is None or FILE_EXT_RE.search(urlsplit(url).path):
                return url
            changed += 1
            target = lookup(key, link_map)
            return f'<a href="{target}">перейти до розділу</a>' if target else ''

        return BARE_URL_RE.sub(replace, text)

    return map_text_nodes(markup, clean), changed


def rewrite_legacy_links(markup: str, link_map: dict[str, str]) -> tuple[str, int, int, Counter]:
    remapped = unwrapped = 0
    unmatched: Counter = Counter()

    def handle(match: re.Match[str]) -> str:
        nonlocal remapped, unwrapped
        href = match.group('href')
        key = legacy_key(href)
        if key is None:
            return match.group(0)
        if FILE_EXT_RE.search(urlsplit(href).path):
            return match.group(0)          # файли лишає mirror_page_files.py
        target = lookup(key, link_map)
        if target:
            remapped += 1
            return match.group(0).replace(f'href="{href}"', f'href="{target}"')
        unwrapped += 1
        unmatched[key] += 1
        text = match.group('text')
        # Підпис-адреса без покликання — просто сміття у тексті.
        return '' if strip_tags(text).rstrip('/') == href.rstrip('/') else text

    markup = LINK_RE.sub(handle, markup)
    return markup, remapped, unwrapped, unmatched


# ── прогін ───────────────────────────────────────────────────────────────────────────────────

def tidy_html(markup: str, buttons, link_map, stats: Counter, unmatched: Counter) -> str:
    markup, junk = drop_attr_junk(markup)
    stats['уламки тегів'] += junk

    markup, spoilers = convert_spoilers(markup)
    stats['спойлери'] += spoilers

    markup, embeds = restore_embeds(markup)
    stats['вбудовані документи'] += embeds

    markup, kept, dropped = convert_banners(markup, buttons)
    stats['банери → кнопки'] += kept
    stats['банери прибрано'] += dropped

    markup, schemes = DOUBLE_SCHEME_RE.subn('', markup)   # `href="http://http://lms…"`
    stats['подвійна схема'] += schemes

    markup, bare = rewrite_bare_urls(markup, link_map)
    stats['адреси в тексті'] += bare

    markup, remapped, unlinked, misses = rewrite_legacy_links(markup, link_map)
    stats['покликання перенаправлено'] += remapped
    stats['покликання знято'] += unlinked
    unmatched.update(misses)

    markup, anchors = drop_empty_anchors(markup)
    stats['порожні покликання'] += anchors

    markup = tidy(drop_empty_blocks(markup))
    # Прибирання одного шару оголює наступний (порожнє покликання всередині порожнього абзацу).
    previous = None
    while previous != markup:
        previous = markup
        markup, anchors = drop_empty_anchors(markup)
        stats['порожні покликання'] += anchors
        markup = tidy(drop_empty_blocks(markup))
    return markup


def walk(node, fn) -> bool:
    """Пройти JSON і застосувати `fn` до кожного рядкового значення ключа `html`."""
    changed = False
    if isinstance(node, dict):
        for key, value in node.items():
            if key == 'html' and isinstance(value, str):
                new = fn(value)
                if new != value:
                    node[key] = new
                    changed = True
            elif walk(value, fn):
                changed = True
    elif isinstance(node, list):
        for item in node:
            if walk(item, fn):
                changed = True
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--content', default=str(CONTENT))
    parser.add_argument('--only', help='glob по імені файлу, напр. "quality-centre-*"')
    parser.add_argument('--write', action='store_true', help='зберегти зміни (без цього — dry-run)')
    parser.add_argument('--show-unmatched', type=int, default=15,
                        help='скільки найчастіших неперенаправлених адрес показати')
    args = parser.parse_args()

    root = Path(args.content)
    files = [path for path in sorted(root.rglob('*.json')) if path.name != 'manifest.json']
    if args.only:
        files = [path for path in files if fnmatch.fnmatch(path.name, args.only)]
    if not files:
        print('немає файлів для обробки', file=sys.stderr)
        return 1

    buttons, link_map = load_buttons(), load_link_map(root)
    total: Counter = Counter()
    unmatched: Counter = Counter()
    touched = 0

    for path in files:
        payload = json.loads(path.read_text(encoding='utf-8'))
        stats: Counter = Counter()
        changed = walk(payload, lambda markup: tidy_html(markup, buttons, link_map, stats, unmatched))
        if not changed:
            continue
        touched += 1
        total.update(stats)
        summary = ', '.join(f'{name}: {count}' for name, count in stats.items() if count)
        print(f'{path.relative_to(root)} — {summary}')
        if args.write:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                            encoding='utf-8')

    print(f'\nфайлів змінено: {touched}', file=sys.stderr)
    for name, count in total.items():
        if count:
            print(f'  {name}: {count}', file=sys.stderr)
    if unmatched and args.show_unmatched:
        print('\nнайчастіші адреси без відповідника (покликання знято):', file=sys.stderr)
        for key, count in unmatched.most_common(args.show_unmatched):
            print(f'  {count:>4}  {key}', file=sys.stderr)
    if not args.write:
        print('\n(dry-run — нічого не збережено; повторіть із --write)', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
