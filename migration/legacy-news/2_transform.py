#!/usr/bin/env python3
"""
Stage 2 — turn raw Drupal rows into Directus `articles` payloads.

Reads `news.raw.jsonl` (stage 1) and writes `articles.json`: one object per
article, already shaped like the Directus collection. Pure and offline — run it
as often as you like and diff the output.

The frontend renders `content` as Markdown (markdown-it + DOMPurify), so the
Drupal HTML is converted to Markdown here. The sanitizer's allow-list has no
`iframe`, `table`, `td` or `tr`, so embeds become plain links and tables are
flattened to lines; anything that would be silently dropped at render time is
turned into something that survives.

Usage:
    python3 2_transform.py
    python3 2_transform.py --report        # also print a per-article summary
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

HERE = Path(__file__).parent

LEGACY_BASE = 'http://hnpu.edu.ua/'

# Tags carrying no meaning once styling is gone.
TRANSPARENT = {'span', 'div', 'font', 'section', 'article', 'tbody', 'thead', 'center', 'small'}
BLOCK_TAGS = {'p', 'div', 'section', 'article', 'blockquote', 'ul', 'ol', 'li', 'table', 'tr', 'hr',
              'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

YOUTUBE_RE = re.compile(r'(youtube\.com|youtu\.be)', re.I)

# Sentinel used while tidying, so "  \n" hard breaks survive whitespace cleanup.
HARD_BREAK = '\x01HARD_BREAK\x01'


class HtmlToMarkdown(HTMLParser):
    """Small, explicit HTML → Markdown converter for legacy article bodies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.images: list[str] = []
        self.list_stack: list[dict] = []
        self._link_href: str | None = None
        self._link_text: list[str] = []
        self._skip_depth = 0
        self._pre_depth = 0
        self._heading: str | None = None

    # -- helpers ---------------------------------------------------------
    def emit(self, text: str) -> None:
        if self._link_href is not None:
            self._link_text.append(text)
        else:
            self.out.append(text)

    def newline(self, count: int = 1) -> None:
        self.emit('\n' * count)

    def absolutise(self, url: str) -> str:
        url = html.unescape((url or '').strip())
        if not url or url.startswith(('http://', 'https://', 'mailto:', 'tel:', '#', 'data:')):
            return url
        return urljoin(LEGACY_BASE, url)

    # -- parser callbacks ------------------------------------------------
    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: (v or '') for k, v in attrs_list}

        if tag in ('script', 'style'):
            self._skip_depth += 1
        elif tag == 'br':
            self.emit('  \n')
        elif tag == 'hr':
            self.newline(2)
            self.emit('---')
            self.newline(2)
        elif tag in ('p', 'div', 'blockquote', 'table', 'tr'):
            self.newline(2)
            if tag == 'blockquote':
                self.emit('> ')
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.newline(2)
            self._heading = tag
            self.emit('#' * int(tag[1]) + ' ')
        elif tag in ('strong', 'b'):
            self.emit('**')
        elif tag in ('em', 'i'):
            self.emit('*')
        elif tag in ('s', 'del', 'strike'):
            self.emit('~~')
        elif tag in ('ul', 'ol'):
            self.list_stack.append({'ordered': tag == 'ol', 'index': 0})
            self.newline(2)
        elif tag == 'li':
            self.newline()
            if self.list_stack:
                current = self.list_stack[-1]
                indent = '  ' * (len(self.list_stack) - 1)
                if current['ordered']:
                    current['index'] += 1
                    self.emit(f"{indent}{current['index']}. ")
                else:
                    self.emit(f'{indent}- ')
            else:
                self.emit('- ')
        elif tag in ('td', 'th'):
            # Tables are not renderable downstream; keep cells as separated text.
            self.emit(' | ' if self.out and not self.out[-1].endswith('\n') else '')
        elif tag == 'a':
            href = self.absolutise(attrs.get('href', ''))
            if href:
                self._link_href = href
                self._link_text = []
        elif tag == 'img':
            src = self.absolutise(attrs.get('src', ''))
            if src:
                alt = html.unescape(attrs.get('alt', '')).replace(']', '')
                self.images.append(src)
                self.newline(2)
                self.out.append(f'![{alt}]({src})')
                self.newline(2)
        elif tag == 'iframe':
            src = self.absolutise(attrs.get('src', ''))
            if src:
                # /embed/<id> only works inside an iframe — link to the watch page instead.
                embed = re.match(r'https?://(?:www\.)?youtube\.com/embed/([\w-]+)', src)
                if embed:
                    src = f'https://www.youtube.com/watch?v={embed.group(1)}'
                label = 'Відео на YouTube' if YOUTUBE_RE.search(src) else 'Переглянути вбудований матеріал'
                self.newline(2)
                self.out.append(f'[{label}]({src})')
                self.newline(2)
        elif tag == 'pre':
            self._pre_depth += 1
            self.newline(2)
            self.emit('```\n')

    def handle_endtag(self, tag: str) -> None:
        if tag in ('script', 'style'):
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in ('strong', 'b'):
            self.emit('**')
        elif tag in ('em', 'i'):
            self.emit('*')
        elif tag in ('s', 'del', 'strike'):
            self.emit('~~')
        elif tag in ('ul', 'ol'):
            if self.list_stack:
                self.list_stack.pop()
            self.newline(2)
        elif tag in ('p', 'div', 'blockquote', 'table', 'tr'):
            self.newline(2)
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._heading = None
            self.newline(2)
        elif tag == 'pre':
            self._pre_depth = max(0, self._pre_depth - 1)
            self.emit('\n```')
            self.newline(2)
        elif tag == 'a' and self._link_href is not None:
            text = ''.join(self._link_text).strip()
            href = self._link_href
            self._link_href = None
            self._link_text = []
            if not text:
                text = href
            if text.startswith('!['):  # an image wrapped in a link — keep the image
                self.out.append(text)
            else:
                self.out.append(f'[{text}]({href})')

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._pre_depth:
            self.emit(data)
            return
        text = data.replace('\xa0', ' ')
        text = re.sub(r'\s+', ' ', text)
        if not text.strip():
            # keep a single separating space, never a blank paragraph
            if self.out and not self.out[-1].endswith((' ', '\n')):
                self.emit(' ')
            return
        # Markdown-escape the characters that would otherwise change meaning.
        text = re.sub(r'(?<!\\)([*_`])', r'\\\1', text)
        self.emit(text)

    def result(self) -> str:
        return ''.join(self.out)


def tidy_markdown(text: str) -> str:
    # Protect markdown hard breaks ("  \n") before trailing whitespace is stripped.
    text = text.replace('  \n', HARD_BREAK)
    text = re.sub(r'[ \t]+(\n)', r'\1', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.replace(HARD_BREAK, '  \n')
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'(?m)^[ \t]+', '', text)
    text = re.sub(r'(?m)^>\s*$', '', text)
    return text.strip()


def html_to_markdown(body: str) -> tuple[str, list[str]]:
    parser = HtmlToMarkdown()
    parser.feed(body or '')
    parser.close()
    return tidy_markdown(parser.result()), parser.images


def plain_text(markdown: str) -> str:
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', markdown)   # images
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)     # links → their text
    text = re.sub(r'[#>*_`~\\-]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def build_excerpt(markdown: str, limit: int = 220) -> str:
    text = plain_text(markdown)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0].rstrip(' ,.;:—-')
    return f'{cut}…'


def slug_from_alias(alias: str | None, nid: int, title: str) -> str:
    if alias:
        slug = alias.split('/')[-1].strip()
        if slug:
            return slug[:255]
    fallback = re.sub(r'[^a-z0-9]+', '-', (title or '').lower()).strip('-')
    return (fallback or f'news-{nid}')[:255]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--in', dest='src', default=str(HERE / 'news.raw.jsonl'))
    parser.add_argument('--out', default=str(HERE / 'articles.json'))
    parser.add_argument('--report', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    src = Path(args.src)
    if not src.exists():
        print(f'{src} not found — run 1_extract.py first', file=sys.stderr)
        return 1

    rows = [json.loads(line) for line in src.read_text(encoding='utf-8').splitlines() if line.strip()]

    articles: list[dict] = []
    seen_slugs: dict[str, int] = {}
    without_body = without_image = 0

    for row in rows:
        content, images = html_to_markdown(row.get('body') or '')
        if not content:
            without_body += 1
        if not images:
            without_image += 1

        slug = slug_from_alias(row.get('alias'), row['nid'], row.get('title') or '')
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            slug = f"{slug}-{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 1

        published = datetime.fromtimestamp(row['created'], tz=timezone.utc)
        title = html.unescape(re.sub(r'\s+', ' ', row.get('title') or '')).strip()

        articles.append({
            'legacy_nid': row['nid'],
            'legacy_alias': row.get('alias'),
            'title': title[:255],
            'slug': slug,
            'excerpt': build_excerpt(content),
            'content': content,
            'date_published': published.isoformat(),
            'status': 'published' if row.get('status') == 1 else 'draft',
            # Cover: the first inline image of the article; uploaded in stage 3.
            'cover_source_url': images[0] if images else None,
            'inline_image_count': len(images),
        })

    Path(args.out).write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(
        f'Transformed {len(articles)} articles → {args.out}\n'
        f'  empty content:     {without_body}\n'
        f'  without any image: {without_image}\n'
        f'  covers available:  {sum(1 for a in articles if a["cover_source_url"])}',
        file=sys.stderr,
    )
    if args.report:
        for a in articles[:20]:
            print(f'  {a["date_published"][:10]}  {a["slug"][:48]:<50} {len(a["content"]):>6} chars  '
                  f'{a["inline_image_count"]} img', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
