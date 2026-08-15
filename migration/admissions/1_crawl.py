#!/usr/bin/env python3
"""
Stage 1 — обійти розділ приймальної комісії старого сайту й скласти карту сторінок.

`/uk/division/pryymalna-komisiya` — це не одна сторінка, а розділ зі 100+ сторінок: поточна
кампанія (програми, розклади, результати, рейтинги, накази про зарахування, вартість),
документація комісії й архіви кампаній 2020–2025, кожен зі своїм переліком сторінок.

Скрипт іде від кореня розділу за внутрішніми покликаннями, лишаючись у межах вступної тематики,
і пише `data/pages.json`:

    [{"slug": "…", "url": "…", "title": "…", "group": "campaign|documents|archive-2024",
      "parents": ["/uk/…"], "bytes": 12345, "files": 17}]

Групу визначає те, з якої сторінки на неї вперше прийшли: корінь → поточна кампанія, «АРХІВ.
Вступна кампанія 2023 року» → archive-2023 і так далі. Далі `2_emit.py` за цією картою переносить
тексти, а `../pass2/mirror_page_files.py` — файли.

    python3 1_crawl.py --limit 5        # розвідка
    python3 1_crawl.py
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
BASE = 'https://hnpu.edu.ua'
ROOT = '/uk/division/pryymalna-komisiya'

HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'),
    'Accept-Language': 'uk,en;q=0.8',
}

BODY_RE = re.compile(r'<div class="field field-name-body.*?(?=<div class="region region-footer|<footer)', re.S)
TITLE_RE = re.compile(r'<title>(.*?)</title>', re.S)
FILE_RE = re.compile(r'\.(pdf|docx?|xlsx?|pptx?|jpe?g|png|zip)(\?|$)', re.I)
ARCHIVE_RE = re.compile(r'арх[іi]в.*?(20\d{2})', re.I)

# Сторінки розділу мають упізнавані адреси; за ці межі краулер не виходить, щоб не потягнути
# половину старого сайту через випадкове покликання в тексті.
IN_SECTION = re.compile(
    r'(20\d\d[-_])|(pryymal)|(vstup)|(arhiv-vstupna)|(zarahuvann)|(rekomendovan)|(reytyng)'
    r'|(programy-vstup)|(rozklad-vstup)|(rezultaty-vstup)|(rezultaty-tvorchyh)|(rezultaty-spivbesid)'
    r'|(dokumentaciya-pryymalnoyi)|(normatyvna-dokumentaciya-licenziya)|(ogolosh)|(o-g-o-l-o-sh)'
    r'|(osvit(niy)?-centr-donbask)|(bakalavr)|(magistr)|(inozem)|(tvorchi-konkursy)'
    r'|(perelik-dokumentiv-dlya-vstupu)|(pytannya-vidpovidi)|(zakonodavstvo-ukrayiny)'
    r'|(vaucher-na-navchannya)|(dodatkovyy-nabir)', re.I)

TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e', 'є': 'ie', 'ж': 'zh',
    'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ь': '', 'ю': 'iu', 'я': 'ia', '’': '', "'": '',
}


def fetch(path: str) -> str:
    request = urllib.request.Request(BASE + path, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode('utf-8', 'replace')


def clean(text: str) -> str:
    return re.sub(r'\s+', ' ', html_lib.unescape(re.sub(r'<[^>]+>', ' ', text))).strip()


def slugify(path: str) -> str:
    name = path.rsplit('/', 1)[-1]
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(TRANSLIT.get(char, char) for char in name.lower())
    name = re.sub(r'[^a-z0-9]+', '-', name).strip('-')
    return f'pk-{name}'[:80]


def normalise(href: str) -> str | None:
    href = href.split('#')[0].strip()
    for prefix in ('//hnpu.edu.ua', 'https://hnpu.edu.ua', 'http://hnpu.edu.ua'):
        if href.startswith(prefix):
            href = href[len(prefix):]
    if not href.startswith('/uk/') or FILE_RE.search(href):
        return None
    return href


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--limit', type=int, help='скільки сторінок обійти (для розвідки)')
    parser.add_argument('--out', default=str(HERE / 'data' / 'pages.json'))
    args = parser.parse_args()

    queue: list[tuple[str, str]] = [(ROOT, 'campaign')]
    seen: set[str] = set()
    pages: list[dict] = []

    while queue:
        path, group = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        try:
            page = fetch(path)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            print(f'  ! {path}: {exc}', file=sys.stderr)
            continue

        body_match = BODY_RE.search(page)
        body = body_match.group(0) if body_match else ''
        title_match = TITLE_RE.search(page)
        title = clean(title_match.group(1)).split('|')[0].strip() if title_match else path

        pages.append({
            'slug': slugify(path), 'url': BASE + path, 'path': path, 'title': title,
            'group': group,
            'bytes': len(body),
            'files': len({href for href in re.findall(r'href="([^"]+)"', body) if FILE_RE.search(href)}),
        })
        print(f'  {len(pages):>3}. {group:<14} {title[:56]:<56} {len(body):>7}b', file=sys.stderr)

        if args.limit and len(pages) >= args.limit:
            break

        for href, label in re.findall(r'href="([^"]+)"[^>]*>(.*?)</a>', body, re.S):
            target = normalise(href)
            if not target or target in seen or not IN_SECTION.search(target):
                continue
            archive = ARCHIVE_RE.search(clean(label))
            child_group = f'archive-{archive.group(1)}' if archive else group
            queue.append((target, child_group))
        time.sleep(0.25)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pages, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    groups: dict[str, int] = {}
    for entry in pages:
        groups[entry['group']] = groups.get(entry['group'], 0) + 1
    print(f'\n{len(pages)} сторінок, файлів у текстах: {sum(p["files"] for p in pages)}', file=sys.stderr)
    for group, count in sorted(groups.items()):
        print(f'  {group:<16} {count}', file=sys.stderr)
    print(f'→ {out}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
