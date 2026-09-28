#!/usr/bin/env python3
"""
Правка 28.09, п. 5: перенести дочірню категорію новин «Кафедра біології» з ННІ
спеціальної освіти та інклюзії до Факультету математики, інформатики і природничої освіти.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 move_biology_category.py --dry-run
    python3 move_biology_category.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login  # noqa: E402

CATEGORY_ID = '1cde8080-9f9b-4204-9f3d-12155fcdf106'  # Кафедра біології
OLD_PARENT = '5628dc9b-2212-4fca-a695-68d34a3f6bd1'  # ННІ спеціальної освіти та інклюзії
NEW_PARENT = '2f4f7fe6-06eb-4301-9453-820f69d12921'  # Факультет математики, інформатики і природничої освіти


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directus-url',
                        default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    rows = directus.get(f'/items/categories/{CATEGORY_ID}?fields=id,name,parent') or {}
    parent = rows.get('parent')
    if parent == NEW_PARENT:
        print('= вже перенесено', file=sys.stderr)
        return 0
    if parent != OLD_PARENT:
        print(f'! неочікуваний поточний parent={parent}, перевірте вручну', file=sys.stderr)
        return 1

    print(f'~ categories/{CATEGORY_ID}: parent {OLD_PARENT} -> {NEW_PARENT}', file=sys.stderr)
    if not args.dry_run:
        directus.request('PATCH', f'/items/categories/{CATEGORY_ID}', payload={'parent': NEW_PARENT})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
