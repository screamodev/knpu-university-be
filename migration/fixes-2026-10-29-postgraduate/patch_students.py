#!/usr/bin/env python3
"""
Правки 29.10, п. «Відділ аспірантури і докторантури»: на вкладці «Аспіранту» під блоком
«Документація аспірантів» — новий блок «Про підготовку до захисту дисертації».

Вкладку на проді ведуть в адмінці (`structure_pages`), тож правка йде в рядок Directus. Логіка —
`fixes-2026-09-16/patch_structure_pages.py` (точкова заміна, ідемпотентна, `--dry-run`), тут лише
свій список правок.

    python3 fixes-2026-10-29-postgraduate/patch_students.py --dry-run
    python3 fixes-2026-10-29-postgraduate/patch_students.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    'patch_structure_pages',
    Path(__file__).resolve().parents[1] / 'fixes-2026-09-16' / 'patch_structure_pages.py',
)
patch_structure_pages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(patch_structure_pages)

ANCHOR = '</details>\n<p><strong>Наші реквізити для оплати за навчання:</strong></p>'

patch_structure_pages.PATCHES = [
    (
        'postgraduate', 'students',
        ANCHOR,
        '</details>\n'
        '<details>\n'
        '<summary><strong>Про підготовку до захисту дисертації</strong></summary>\n'
        '<ul>\n'
        '<li><a href="https://drive.google.com/file/d/1Xj3q9RUB31RbGkBTPO1LS8EzUx5KUvlo/view?usp=sharing"'
        ' target="_blank" rel="noopener noreferrer">'
        'Підготовка дисертацій до захисту: правила, процедури, відповідальність</a></li>\n'
        '</ul>\n'
        '</details>\n'
        '<p><strong>Наші реквізити для оплати за навчання:</strong></p>',
    ),
]


if __name__ == '__main__':
    raise SystemExit(patch_structure_pages.main())
