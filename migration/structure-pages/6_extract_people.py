#!/usr/bin/env python3
"""
Stage 6 — pull the «Деканат» block out of the migrated unit pages into structured data.

The legacy pages laid the deanery out as a table of portraits: the transferred HTML therefore
carries a full-width photo inside a `<td>` with the name and degree as loose text. The frontend
renders that as prose, which looks nothing like `/university/rectorate`.

This stage rewrites `app/content/structure/<unit>/home.<locale>.json` in place: it adds

    "people": [{ "photo": "/assets/<uuid>"|null, "position": …, "name": …,
                 "degree": …, "profileUrl": …|null }]

to the section that held the block and removes the consumed markup from `html`, so the page can
render proper cards. Idempotent: a section that already has `people` is skipped.

Four shapes exist on the old site and all four are handled:

  A. `<td>` with `<p><img></p>` + `<p><em>Посада</em></p>` + `<p><a><strong>Ім'я</strong></a></p>`
  B. `<td>` with a bare `<img>` and loose text nodes
  C. a two-row table — portraits in row 1, texts in row 2, paired by column index
  D. no table at all: paragraphs of «Посада: Ім'я — науковий ступінь», with a couple of
     unattributed portraits dumped at the end. Those photos are left in the prose on purpose:
     there is no way to tell whose face is whose, and guessing would put the wrong name under a
     real person.

Usage:
    python3 6_extract_people.py --dry-run
    python3 6_extract_people.py
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_CONTENT = HERE.parents[2] / 'knpu-university-fe' / 'app' / 'content' / 'structure'

VOID_TAGS = {'img', 'br', 'hr', 'input', 'meta', 'link'}

HEADING_RE = re.compile(
    r'<p[^>]*>(?:(?!</p>).)*?(Деканат|Керівництво відділу|Керівництво)(?:(?!</p>).)*?</p>',
    re.IGNORECASE | re.DOTALL,
)

POSITION_WORDS = ('декан', 'заступник', 'координатор', 'керівник', 'завідувач', 'директор',
                  'диспетчер', 'секретар')

# Where a degree starts, when the legacy markup glued it onto the position.
DEGREE_RE = re.compile(r'\b(доктор|доктора|кандидат|канд\.|д\.\s?пед|PhD|професор|доцент|'
                       r'старший викладач|викладач|заслужений)', re.IGNORECASE)


def position_tail(text: str) -> str:
    """
    Legacy runs glue the previous person's degree onto the next person's position, so start the
    position at its first job word: «…доцент. Координатор з виховної роботи» → «Координатор з
    виховної роботи», while «Заступник декана…» keeps its «Заступник».
    """
    lowered = text.lower()
    starts = [found for found in (lowered.find(word) for word in POSITION_WORDS) if found >= 0]
    return clean(text[min(starts):]) if starts else clean(text)


def split_position_degree(text: str) -> tuple[str, str]:
    """«декана факультету доктор педагогічних наук, професор» → position, degree."""
    match = DEGREE_RE.search(text)
    if not match or match.start() == 0:
        return clean(text), ''
    return clean(text[:match.start()]), clean(text[match.start():])


class Node:
    __slots__ = ('tag', 'attrs', 'children', 'text', 'parent')

    def __init__(self, tag: str, attrs: dict[str, str] | None = None, text: str = '') -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[Node] = []
        self.text = text
        self.parent: Node | None = None

    def add(self, node: Node) -> Node:
        node.parent = self
        self.children.append(node)
        return node

    def find_all(self, tag: str) -> list[Node]:
        found: list[Node] = []
        for child in self.children:
            if child.tag == tag:
                found.append(child)
            found.extend(child.find_all(tag))
        return found

    def plain_text(self) -> str:
        if self.tag == '#text':
            return self.text
        return ''.join(child.plain_text() for child in self.children)


class TreeBuilder(HTMLParser):
    """Minimal DOM over the migrated fragments — enough for tables of portraits."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node('#root')
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {key: (value or '') for key, value in attrs})
        self.current.add(node)
        if tag not in VOID_TAGS:
            self.current = node

    def handle_endtag(self, tag: str) -> None:
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent or self.root
        if node is not self.root and node.parent is not None:
            self.current = node.parent

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.current.add(Node('#text', text=data))


def parse(fragment: str) -> Node:
    builder = TreeBuilder()
    builder.feed(fragment)
    builder.close()
    return builder.root


def clean(text: str) -> str:
    text = html_lib.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.strip(' ,;:–—-')


def looks_like_position(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in POSITION_WORDS)


def person_from_cell(cell: Node, photo: str | None = None) -> dict | None:
    """One `<td>` (or one column of a two-row table) → a person record."""
    images = cell.find_all('img')
    if photo is None and images:
        photo = images[0].attrs.get('src') or None

    # The name is the emphasised run — inside a link when the old site had a profile page.
    link = next((a for a in cell.find_all('a') if clean(a.plain_text())), None)
    if link is not None:
        name = clean(link.plain_text())
        profile = link.attrs.get('href') or None
    else:
        strong = next((s for s in cell.find_all('strong') if clean(s.plain_text())), None)
        name = clean(strong.plain_text()) if strong is not None else ''
        profile = None

    if not name:
        return None

    # Everything else in the cell, split around the name: what comes before is the position,
    # what comes after is the academic degree.
    whole = clean(cell.plain_text())
    before, _, after = whole.partition(name)
    position = clean(before)
    degree = clean(after)

    # Shape C keeps «ім'я<br>посада» inside one <strong>, so the position lands after the name.
    if not position and degree and looks_like_position(degree):
        position, degree = split_position_degree(degree)
    elif position:
        position = position_tail(position)

    return {
        'photo': photo,
        'position': position or None,
        'name': name,
        'degree': degree or None,
        'profileUrl': profile if (profile or '').startswith(('http://', 'https://')) else None,
    }


def people_from_table(table_html: str) -> list[dict]:
    root = parse(table_html)
    rows = root.find_all('tr')
    if not rows:
        return []

    cells_by_row = [row.find_all('td') for row in rows]

    # Shape C: portraits in the first row, texts in the second — pair by column index.
    if len(rows) == 2:
        top, bottom = cells_by_row
        top_is_photos = bool(top) and all(cell.find_all('img') and not clean(cell.plain_text()) for cell in top)
        if top_is_photos and len(bottom) == len(top):
            people = []
            for photo_cell, text_cell in zip(top, bottom):
                images = photo_cell.find_all('img')
                photo = images[0].attrs.get('src') if images else None
                person = person_from_cell(text_cell, photo=photo)
                if person:
                    people.append(person)
            return people

    # Shapes A and B: one person per cell.
    people = []
    for row_cells in cells_by_row:
        for cell in row_cells:
            person = person_from_cell(cell)
            if person:
                people.append(person)
    return people


def people_from_paragraphs(fragment: str) -> list[dict]:
    """Shape D: «Посада:» and «Ім'я – ступінь» as a flat run of paragraphs and text nodes."""
    root = parse(fragment)
    people: list[dict] = []
    pending_position: str | None = None

    for child in root.children:
        text = clean(child.plain_text())
        if not text:
            continue

        links = child.find_all('a') if child.tag != 'a' else [child]
        named = next((a for a in links if clean(a.plain_text())), None)

        if named is None:
            if looks_like_position(text):
                pending_position = position_tail(text)
            continue

        name = clean(named.plain_text())
        _, _, after = text.partition(name)
        before = clean(text.partition(name)[0])
        position = position_tail(before) if before else pending_position
        people.append({
            'photo': None,
            'position': clean(position or '') or None,
            'name': name,
            'degree': clean(after) or None,
            'profileUrl': named.attrs.get('href') if (named.attrs.get('href') or '').startswith('http') else None,
        })
        pending_position = None

    return people


def extract(section_html: str) -> tuple[list[dict], str, str | None]:
    """→ (people, html without the consumed block, heading text)."""
    heading = HEADING_RE.search(section_html)
    if heading:
        heading_text: str | None = clean(re.sub(r'<[^>]+>', ' ', heading.group(0)))
        head_end = heading.end()
        head_start = heading.start()
    else:
        # Some units (arts) dropped the «Деканат» caption — recognise the table by its content.
        candidate = None
        for match in re.finditer(r'<table\b.*?</table>', section_html, re.DOTALL):
            body = clean(re.sub(r'<[^>]+>', ' ', match.group(0)))
            if looks_like_position(body) and match.group(0).count('<td') > 1:
                candidate = match
                break
        if candidate is None:
            return [], section_html, None
        people = people_from_table(candidate.group(0))
        if not people:
            return [], section_html, None
        without = section_html[:candidate.start()] + section_html[candidate.end():]
        return people, without, None

    rest = section_html[head_end:]

    table = re.search(r'<table\b.*?</table>', rest, re.DOTALL)
    # A table further down the page (list of departments, say) is not the deanery: only take it
    # when nothing but whitespace and empty tags separate it from the heading.
    if table and not clean(re.sub(r'<[^>]+>', ' ', rest[:table.start()])):
        people = people_from_table(table.group(0))
        if people:
            without = section_html[:head_start] + rest[:table.start()] + rest[table.end():]
            return people, without, heading_text
        return [], section_html, heading_text

    # Shape D: consume paragraphs until one that carries only images (the orphan portraits).
    stop = re.search(r'<p[^>]*>\s*(?:<img[^>]*>\s*)+</p>', rest)
    block = rest[:stop.start()] if stop else rest
    people = people_from_paragraphs(block)
    if not people:
        return [], section_html, heading_text

    without = section_html[:head_start] + (rest[stop.start():] if stop else '')
    return people, without, heading_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--content', default=str(DEFAULT_CONTENT))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    files = sorted(Path(args.content).glob('*/home.*.json'))
    if not files:
        print(f'! no unit content under {args.content}', file=sys.stderr)
        return 2

    changed = 0
    for path in files:
        data = json.loads(path.read_text(encoding='utf-8'))
        sections = data.get('sections') or []
        if any(section.get('people') for section in sections):
            print(f'{path.parent.name:26} already has people — skipped')
            continue

        for section in sections:
            people, without, heading = extract(section.get('html') or '')
            if not people:
                continue

            print(f'{path.parent.name:26} {len(people)} person(s): '
                  + ', '.join(f'{p["name"]} ({p["position"] or "?"})' for p in people))
            if args.dry_run:
                break

            section['people'] = people
            section['peopleHeading'] = heading
            section['html'] = without
            changed += 1
            break
        else:
            print(f'{path.parent.name:26} no deanery block')

        if not args.dry_run and changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    if not args.dry_run:
        print(f'\nrewrote {changed} file(s)', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
