"""
Word-документ підрозділу (.doc/.docx) → HTML для статичного контенту сторінки.

`textutil` (macOS) дає HTML зі стилями й полями `HYPERLINK "…"` у тексті — старі .doc
зберігають посилання саме так. Тут поля стають `<a>`, а решта проходить той самий прибиральник,
що й сторінки старого сайту (`clean_body`), тож на виході — лише дозволені теги без стилів.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from fetch_legacy import clean_body

HYPERLINK = re.compile(r'HYPERLINK\s+"([^"]+)"\s*(.*?)(?=<br\s*/?>|</p>)', re.S)


def linkify(html: str) -> str:
    """Адреси в текстових вузлах поза `<a>` → посилання."""
    out, inside = [], 0
    for part in re.split(r'(<[^>]+>)', html):
        if part.startswith('<'):
            if re.match(r'<a\b', part):
                inside += 1
            elif part.startswith('</a'):
                inside = max(0, inside - 1)
            out.append(part)
        elif inside:
            out.append(part)
        else:
            out.append(re.sub(r'https?://[^\s<]+', lambda m: f'<a href="{m.group(0)}">{m.group(0)}</a>', part))
    return ''.join(out)


def doc_to_html(path: Path) -> str:
    raw = subprocess.run(['textutil', '-convert', 'html', '-stdout', str(path)],
                         check=True, capture_output=True, text=True).stdout
    body = re.search(r'<body[^>]*>(.*)</body>', raw, re.S).group(1)
    body = HYPERLINK.sub(lambda m: f'<a href="{m.group(1)}">{m.group(2).strip() or m.group(1)}</a>', body)
    html, _images = clean_body(body)
    html = re.sub(r'<(b|strong)>\s*</\1>', '', html)
    for tag in ('b', 'i', 'em', 'strong'):
        html = re.sub(rf'</{tag}>(\s*)<{tag}>', r'\1', html)
    html = re.sub(r'<(/?)b>', r'<\1strong>', html)
    html = re.sub(r'<(/?)i>', r'<\1em>', html)
    # Голі адреси в тексті — клікабельні.
    html = linkify(html)
    html = html.replace('<p> <a ', '<p><a ')
    html = re.sub(r'<p>\s*(?:<br\s*/?>)?\s*</p>', '', html)
    # Посилання на сторінки старого сайту живуть тепер на old.hnpu.edu.ua.
    html = re.sub(r'https?://(?:www\.)?hnpu\.edu\.ua/(uk/|sites/)', r'https://old.hnpu.edu.ua/\1', html)
    return html.strip()
