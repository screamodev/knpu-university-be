#!/usr/bin/env python3
"""
Перетворити .docx, надісланий підрозділом, на HTML для контенту сайту.

Підрозділи надсилають тексти вордівськими файлами, а сторінки структури зберігають HTML
(`knpu-university-fe/app/content/structure/**`). Ручне перенесення таких файлів — найдовша
частина правок, тож тут мінімальний, але передбачуваний конвертер:

* абзац → `<p>`, порожні абзаци пропускаються;
* абзац зі списку (`w:numPr`) → `<li>` у спільному `<ul>`;
* жирний і курсивний прогони → `<strong>` / `<em>`;
* гіперпосилання (`w:hyperlink` + relationships) → `<a href="…">`;
* м'які переноси рядка (`w:br`) → `<br />`.

Зображення не переносяться: у Directus вони заливаються окремо, під власними id.

    python3 docx_to_html.py "Оновлення ФМІПО.docx" > body.html
"""

from __future__ import annotations

import html
import re
import sys
import zipfile
from xml.etree import ElementTree

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PKG_REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'


def relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    try:
        xml = archive.read('word/_rels/document.xml.rels')
    except KeyError:
        return {}
    root = ElementTree.fromstring(xml)
    return {node.get('Id'): node.get('Target') for node in root.iter(f'{PKG_REL}Relationship')}


def run_html(run: ElementTree.Element) -> str:
    text = ''
    for node in run:
        if node.tag == f'{W}t':
            text += html.escape(node.text or '')
        elif node.tag in (f'{W}br', f'{W}cr'):
            text += '<br />'
        elif node.tag == f'{W}tab':
            text += ' '
    if not text.strip():
        return text
    properties = run.find(f'{W}rPr')
    if properties is not None:
        if properties.find(f'{W}b') is not None:
            text = f'<strong>{text}</strong>'
        if properties.find(f'{W}i') is not None:
            text = f'<em>{text}</em>'
    return text


def paragraph_html(paragraph: ElementTree.Element, rels: dict[str, str]) -> str:
    parts: list[str] = []
    for child in paragraph:
        if child.tag == f'{W}r':
            parts.append(run_html(child))
        elif child.tag == f'{W}hyperlink':
            inner = ''.join(run_html(run) for run in child.findall(f'{W}r'))
            target = rels.get(child.get(f'{R}id', ''), '')
            if not inner.strip():
                continue
            parts.append(f'<a href="{html.escape(target, quote=True)}">{inner}</a>' if target else inner)
    return ''.join(parts)


def is_list_item(paragraph: ElementTree.Element) -> bool:
    properties = paragraph.find(f'{W}pPr')
    return properties is not None and properties.find(f'{W}numPr') is not None


def convert(path: str) -> str:
    with zipfile.ZipFile(path) as archive:
        rels = relationships(archive)
        root = ElementTree.fromstring(archive.read('word/document.xml'))

    out: list[str] = []
    open_list = False
    for paragraph in root.iter(f'{W}p'):
        text = paragraph_html(paragraph, rels).strip()
        if not re.sub(r'<[^>]+>|&nbsp;|\s', '', text):
            continue
        if is_list_item(paragraph):
            if not open_list:
                out.append('<ul>')
                open_list = True
            out.append(f'<li>{text}</li>')
            continue
        if open_list:
            out.append('</ul>')
            open_list = False
        out.append(f'<p>{text}</p>')
    if open_list:
        out.append('</ul>')
    return '\n'.join(out)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    print(convert(sys.argv[1]))
