#!/usr/bin/env python3
"""
Stage 2 — bucket the legacy pages into canonical tabs and clean their HTML.

Two jobs:

1. **Bucketing.** Each faculty's sidebar has its own vocabulary ("Виховна робота",
   "Студентське життя", "Студентська рада" are all student life). Keyword rules map every menu
   entry onto one of the canonical tabs, and the result is written to `tabs.map.draft.json`.
   Copy that to `tabs.map.json` and edit it — the committed file always wins, so a hand fix is
   never overwritten by a re-run.

2. **Cleaning.** Drupal bodies are full of `<font>`, `font-family:georgia`, layout tables and
   nested spans. Everything outside the frontend's DOMPurify allow-list
   (`app/utils/renderStoredArticleMarkdown.ts`) is dropped here rather than silently at render
   time, and the only inline style kept is `text-align`.

Outputs `content.draft.json` (per unit → tab → sections) and `images.list.json`.

Usage:
    python3 2_transform.py
    python3 2_transform.py --report
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

HERE = Path(__file__).parent
LEGACY_BASE = 'https://hnpu.edu.ua/'

# Canonical tabs, matching STRUCTURE_TAB_IDS in the frontend.
TAB_IDS = ['home', 'admission', 'structure', 'history', 'education', 'science', 'students',
           'news', 'cooperation']

# Menu label → tab. First match wins, so order matters: more specific phrases go first.
BUCKET_RULES: list[tuple[str, str]] = [
    ('головна', 'home'),
    ('про факультет', 'home'),
    ('вступник', 'admission'),
    ('абітурієнт', 'admission'),
    ('спеціальност', 'admission'),
    ('історія', 'history'),
    ('відомі випускники', 'history'),
    ('структура', 'structure'),
    ('освітня діяльність', 'education'),
    ('практичн', 'education'),
    ('практика', 'education'),
    ('дистанційне навчання', 'education'),
    ('розклад', 'education'),
    ('графік навчального', 'education'),
    ('звіт з освітньої', 'education'),
    ('матеріально-техничне', 'education'),
    ('матеріальне забезпечення', 'education'),
    ('безпека освітнього', 'education'),
    ('наукова діяльність', 'science'),
    ('наукове товариство', 'science'),
    ('снт', 'science'),
    ('конференц', 'science'),
    ('форум', 'science'),
    ('читання', 'science'),
    ('науково-предметний', 'science'),
    ('академічна доброчесність', 'science'),
    ('етики та біоетики', 'science'),
    ('біорізноманіття', 'science'),
    ('звіт з наукової', 'science'),
    ('звіти факультету', 'science'),
    ('science around us', 'science'),
    ('музей історії науки', 'science'),
    ('цікаво про', 'science'),
    ('виховна', 'students'),
    ('студентське життя', 'students'),
    ('студентська рада', 'students'),
    ('спілка студентів', 'students'),
    ('волонтер', 'students'),
    ('козацький кіш', 'students'),
    ('звіт з виховної', 'students'),
    ('творча діяльність', 'students'),
    ('музей іграшки', 'students'),
    ('календар заходів', 'students'),
    ('співпраця', 'cooperation'),
    ('академічна мобільність', 'cooperation'),
    ('міжнародна діяльність', 'cooperation'),
]

# Legacy news pages are not migrated — the Новини tab reads our own articles collection.
SKIP_LABELS = ('новини', 'хроніка подій')

ALLOWED_TAGS = {
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'del', 'sub', 'sup',
    'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
    'a', 'img', 'figure', 'figcaption', 'table', 'caption', 'thead', 'tbody', 'tfoot',
    'tr', 'th', 'td', 'hr', 'iframe',
}
# Kept in the tree but stripped of every attribute; `div`/`span` survive as plain wrappers.
UNWRAP_TAGS = {'font', 'span', 'center', 'section', 'article', 'small', 'div'}
VOID_TAGS = {'br', 'img', 'hr'}
ALLOWED_ATTRS = {
    'a': {'href', 'title'},
    'img': {'src', 'alt', 'title', 'width', 'height'},
    'iframe': {'src', 'allowfullscreen'},
    'td': {'colspan', 'rowspan'},
    'th': {'colspan', 'rowspan'},
}
EMBED_HOSTS = ('youtube.com', 'youtu.be', 'youtube-nocookie.com', 'player.vimeo.com')

# Legacy h1 would compete with the page title; demote it.
TAG_REMAP = {'h1': 'h2', 'strike': 's'}


class LegacyHtmlCleaner(HTMLParser):
    """Rewrites a Drupal body into the subset the site can actually render."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.images: list[str] = []
        self.links: list[str] = []
        self._skip_depth = 0

    # -- helpers ---------------------------------------------------------
    def absolutise(self, url: str) -> str:
        value = html.unescape((url or '').strip())
        if not value or value.startswith(('http://', 'https://', 'mailto:', 'tel:', '#', 'data:')):
            return value
        if value.startswith('//'):
            return f'https:{value}'
        return urljoin(LEGACY_BASE, value)

    @staticmethod
    def keep_style(value: str) -> str | None:
        """Only alignment survives; the rest is 2008-era presentation."""
        for part in (value or '').split(';'):
            name, _, val = part.partition(':')
            if name.strip().lower() == 'text-align' and val.strip().lower() in ('left', 'center', 'right', 'justify'):
                return f'text-align: {val.strip().lower()}'
        return None

    def attrs_for(self, tag: str, attrs: dict[str, str]) -> str:
        allowed = ALLOWED_ATTRS.get(tag, set())
        parts = []
        for key in sorted(allowed):
            value = attrs.get(key)
            if not value:
                continue
            if key in ('src', 'href'):
                value = self.absolutise(value)
                if not value:
                    continue
            parts.append(f'{key}="{html.escape(value, quote=True)}"')
        style = self.keep_style(attrs.get('style', ''))
        if style and tag not in ('img', 'iframe'):
            parts.append(f'style="{style}"')
        if tag == 'img':
            parts.append('loading="lazy"')
        return (' ' + ' '.join(parts)) if parts else ''

    # -- parser callbacks ------------------------------------------------
    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = {k.lower(): (v or '') for k, v in attrs_list}
        tag = TAG_REMAP.get(tag, tag)

        if tag in ('script', 'style'):
            self._skip_depth += 1
            return
        if tag in UNWRAP_TAGS:
            return
        if tag == 'iframe':
            src = self.absolutise(attrs.get('src', ''))
            if any(host in src for host in EMBED_HOSTS):
                self.out.append(f'<iframe src="{html.escape(src, quote=True)}" allowfullscreen></iframe>')
            elif src:
                # Not renderable downstream — keep it reachable as a link instead.
                self.out.append(f'<p><a href="{html.escape(src, quote=True)}">{html.escape(src)}</a></p>')
            return
        if tag not in ALLOWED_TAGS:
            return

        if tag == 'img':
            src = self.absolutise(attrs.get('src', ''))
            if not src:
                return
            self.images.append(src)
        if tag == 'a':
            href = self.absolutise(attrs.get('href', ''))
            if href:
                self.links.append(href)

        rendered = f'<{tag}{self.attrs_for(tag, attrs)}>'
        self.out.append(rendered.replace('>', ' />') if tag in VOID_TAGS and tag != 'br' else rendered)

    def handle_startendtag(self, tag: str, attrs_list) -> None:
        self.handle_starttag(tag, attrs_list)

    def handle_endtag(self, tag: str) -> None:
        tag = TAG_REMAP.get(tag, tag)
        if tag in ('script', 'style'):
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in UNWRAP_TAGS or tag in VOID_TAGS or tag == 'iframe':
            return
        if tag in ALLOWED_TAGS:
            self.out.append(f'</{tag}>')

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self.out.append(html.escape(data.replace('\xa0', ' '), quote=False))

    def result(self) -> str:
        return ''.join(self.out)


def tidy(markup: str) -> str:
    markup = re.sub(r'<p>(?:\s|<br\s*/?>)*</p>', '', markup)
    markup = re.sub(r'(<br\s*/?>\s*){3,}', '<br /><br />', markup)
    markup = re.sub(r'[ \t]{2,}', ' ', markup)
    markup = re.sub(r'\n{3,}', '\n\n', markup)
    return markup.strip()


def clean_body(body: str) -> tuple[str, list[str]]:
    cleaner = LegacyHtmlCleaner()
    cleaner.feed(body or '')
    cleaner.close()
    return tidy(cleaner.result()), cleaner.images


def bucket_for(label: str) -> str | None:
    lowered = label.strip().lower()
    if any(skip in lowered for skip in SKIP_LABELS):
        return None
    for needle, tab in BUCKET_RULES:
        if needle in lowered:
            return tab
    return None


NAME_RE = r"[А-ЯІЇЄҐ][а-яіїєґ'’ʼ\-]+"
HEAD_ROLE_RE = re.compile(
    rf"(?:декан|в\.?\s*о\.?\s*декана|директор(?:ка)?)[\s:|,—-]*((?:{NAME_RE}[\s|]+){{1,2}}{NAME_RE})",
    re.I)
# Degree/rank that follows the name, up to the first phone or the next role.
POSITION_RE = re.compile(r'^[\s,|]*((?:доктор|кандидат|професор|доцент|PhD)[^0-9]{0,90}?)(?=\s*(?:тел|моб|e-?mail|$))', re.I)
PHONE_RE = re.compile(r'(?:тел|моб)[^\d+(]{0,10}(\+?[\d(][\d\s()\-]{7,17}\d)', re.I)
ADDRESS_RE = re.compile(r'(\d{5}\s*,?[^|]{5,120}?)(?=\s*(?:тел|моб|e-?mail|$))', re.I)


def absolutise_link(url: str) -> str | None:
    """Keeps only real, followable web links: no mailto:, no site-relative fragments."""
    value = html.unescape((url or '').strip())
    if not value or value.startswith(('mailto:', 'tel:', '#')):
        return None
    if value.startswith('//'):
        return f'https:{value}'
    if value.startswith('/'):
        return urljoin(LEGACY_BASE, value)
    return value if value.startswith(('http://', 'https://')) else None


def parse_contacts(address_html: str | None, chief_html: str | None) -> dict:
    """
    The legacy contact block is free-form HTML holding the dean, deputies, phones and the
    address in one blob. Only the head of the unit and the unit-level contacts are extracted;
    deputies stay in the body text where they came from.
    """
    contacts: dict[str, str] = {}

    def flatten(markup: str | None) -> str:
        text = re.sub(r'<(br|/p|/div|/li)[^>]*>', ' | ', html.unescape(markup or ''), flags=re.I)
        text = re.sub(r'<[^>]+>', ' ', text)
        return re.sub(r'[ \t\xa0]+', ' ', text).strip()

    address_text = flatten(address_html)
    chief_text = flatten(chief_html)

    email = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', address_text)
    if email:
        contacts['email'] = email.group(0)
    phone = PHONE_RE.search(address_text) or PHONE_RE.search(chief_text)
    if phone:
        contacts['phone'] = re.sub(r'\s{2,}', ' ', phone.group(1)).strip()
    address = ADDRESS_RE.search(address_text.replace('|', ' '))
    if address:
        contacts['address'] = re.sub(r'\s{2,}', ' ', address.group(1)).strip(' ,')

    for match in re.finditer(r'href="([^"]+)"', address_html or ''):
        url = match.group(1)
        if 'facebook.com' in url:
            contacts.setdefault('facebook', absolutise_link(url) or url)
        elif 'instagram.com' in url:
            contacts.setdefault('instagram', absolutise_link(url) or url)

    head = HEAD_ROLE_RE.search(chief_text)
    if head:
        contacts['dean'] = re.sub(r'\s*\|\s*', ' ', head.group(1)).strip()
        rest = chief_text[head.end():]
        position = POSITION_RE.search(rest)
        if position:
            contacts['position'] = re.sub(r'\s*\|\s*', ' ', position.group(1)).strip(' ,')
    elif chief_text:
        # No role word — the field is just a name on some units.
        first = re.match(rf"\s*((?:{NAME_RE}\s+){{1,2}}{NAME_RE})", chief_text)
        if first:
            contacts['dean'] = first.group(1).strip()

    chief_link = re.search(r'href="([^"]+)"', chief_html or '')
    if chief_link:
        link = absolutise_link(chief_link.group(1))
        if link:
            contacts['deanUrl'] = link
    return contacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pages', default=str(HERE / 'pages.raw.jsonl'))
    parser.add_argument('--menu', default=str(HERE / 'menu.draft.json'))
    parser.add_argument('--map', dest='map_path', default=str(HERE / 'tabs.map.json'))
    parser.add_argument('--out', default=str(HERE / 'content.draft.json'))
    parser.add_argument('--images-out', default=str(HERE / 'images.list.json'))
    parser.add_argument('--report', action='store_true')
    return parser.parse_args()


def build_draft_map(menu: dict) -> dict:
    """Keyword-bucket every sidebar entry; unmatched labels are reported, not guessed."""
    draft: dict[str, dict] = {}
    unmatched: list[str] = []
    for slug, unit in menu.items():
        tabs: dict[str, list[dict]] = {}
        links: dict[str, list[dict]] = {}
        seen: set[str] = set()
        for alias, page in unit['pages'].items():
            for item in page['menu']:
                tab = bucket_for(item['label'])
                if tab is None:
                    if not any(skip in item['label'].lower() for skip in SKIP_LABELS):
                        unmatched.append(f"{slug}: {item['label']}")
                    continue
                if item['external'] or not item['alias']:
                    links.setdefault(tab, []).append({'label': item['label'], 'url': item['href']})
                    continue
                if item['alias'] in seen:
                    continue
                seen.add(item['alias'])
                tabs.setdefault(tab, []).append({'alias': item['alias'], 'heading': item['label']})
        draft[slug] = {
            'legacy': unit['legacy'],
            'tabs': {tab: tabs[tab] for tab in TAB_IDS if tab in tabs},
            'links': {tab: links[tab] for tab in TAB_IDS if tab in links},
        }
    if unmatched:
        print(f'! {len(unmatched)} menu entries did not match a tab rule:', file=sys.stderr)
        for entry in unmatched[:20]:
            print(f'    {entry}', file=sys.stderr)
    return draft


def main() -> int:
    args = parse_args()
    menu = json.loads(Path(args.menu).read_text(encoding='utf-8'))
    pages = {}
    for line in Path(args.pages).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        pages[(row.get('alias'), row.get('language'))] = row

    draft_map = build_draft_map(menu)
    draft_path = Path(args.map_path).with_suffix('.draft.json')
    draft_path.write_text(json.dumps(draft_map, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    map_path = Path(args.map_path)
    tabs_map = json.loads(map_path.read_text(encoding='utf-8')) if map_path.exists() else draft_map
    source = 'tabs.map.json' if map_path.exists() else 'generated rules'

    content: dict[str, dict] = {}
    images: set[str] = set()

    for slug, unit in tabs_map.items():
        landing_alias = unit['legacy'][0]
        landing = pages.get((landing_alias, 'uk')) or pages.get((landing_alias, 'und'))
        contacts = parse_contacts(landing.get('address') if landing else None,
                                  landing.get('chief') if landing else None)

        unit_content: dict[str, dict] = {}
        for tab, entries in unit.get('tabs', {}).items():
            for locale in ('uk', 'en'):
                sections = []
                source_urls = []
                for entry in entries:
                    row = pages.get((entry['alias'], locale))
                    if row is None and locale == 'uk':
                        row = pages.get((entry['alias'], 'und'))
                    if row is None or not row.get('body'):
                        continue
                    cleaned, found = clean_body(row['body'])
                    if not cleaned:
                        continue
                    images.update(found)
                    sections.append({
                        'heading': entry['heading'] if len(entries) > 1 else None,
                        'html': cleaned,
                    })
                    source_urls.append(f"{LEGACY_BASE}{locale}/{entry['alias']}")
                if sections:
                    unit_content.setdefault(tab, {})[locale] = {
                        'sections': sections,
                        'sourceUrls': source_urls,
                    }

        for tab, links in unit.get('links', {}).items():
            unit_content.setdefault(tab, {}).setdefault('links', links)

        content[slug] = {'contacts': contacts, 'legacyUrl': f'{LEGACY_BASE}uk/{landing_alias}',
                         'tabs': unit_content}

    Path(args.out).write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    Path(args.images_out).write_text(json.dumps(sorted(images), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    total_sections = sum(
        len(locale_content.get('sections', []))
        for unit in content.values()
        for tab in unit['tabs'].values()
        for key, locale_content in tab.items()
        if key in ('uk', 'en')
    )
    print(
        f'Bucketing from {source}\n'
        f'Units: {len(content)}  sections: {total_sections}  images: {len(images)}\n'
        f'→ {args.out}\n→ {args.images_out}\n→ {draft_path} (draft bucketing, copy to tabs.map.json to edit)',
        file=sys.stderr,
    )
    if args.report:
        for slug, unit in content.items():
            tabs = {tab: sorted(k for k in data if k in ('uk', 'en')) for tab, data in unit['tabs'].items()}
            print(f'  {slug:26} {tabs}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
