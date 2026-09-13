#!/usr/bin/env python3
"""
Наукові заходи (правка 12.09): посилання на інформаційні листи трьох уже опублікованих
конференцій і четверта — ХІІ Всеукраїнська конференція кафедри філософії.

Конференції вже є на цілі (їх завели в адмінці), тож тут не `load.py`: рядок шукається за
назвою, у ньому заповнюється лише порожнє `url`. Нова конференція створюється, якщо рядка з такою
назвою немає. Повторний запуск нічого не міняє.

    export DIRECTUS_URL=http://localhost:8055
    export DIRECTUS_EMAIL=… DIRECTUS_PASSWORD=…   (або DIRECTUS_TOKEN)
    python3 update_conferences.py --dry-run
    python3 update_conferences.py
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pass2'))

from common import Directus, login  # noqa: E402

LINKS = {
    'МОДЕЛІ ЖИТТЄТВОРЧОСТІ У СУЧАСНИХ СОЦІОКУЛЬТУРНИХ КОНТЕКСТАХ':
        'https://drive.google.com/file/d/1c3Kiq_nt3bKJgkUdYu3cSmcLNso9jPlB/view?usp=sharing',
    'АКТУАЛЬНІ ПРОБЛЕМИ ДОШКІЛЬНОЇ ОСВІТИ':
        'https://drive.google.com/file/d/11kvIMg8ETZ0mwSFr2cqkpYjz2mWXL7Y5/view?usp=sharing',
}

NEW_CONFERENCE = {
    'status': 'published',
    'title': 'ПІД ЗНАКОМ ГРИГОРІЯ СКОВОРОДИ: ЗОРЯНИЙ ЧАС УКРАЇНСЬКОЇ КУЛЬТУРИ',
    'description': 'Кафедра філософії імені професора М. Д. Култаєвої Харківського національного '
                   'педагогічного університету імені Г. С. Сковороди запрошує взяти участь у ХІІ '
                   'Всеукраїнській (з міжнародною участю) науково-практичній конференції «Під знаком '
                   'Григорія Сковороди: зоряний час української культури».',
    'conferenceType': 'Всеукраїнська (з міжнародною участю)',
    'location': 'Харків',
    'eventDate': '2026-12-03T09:00:00',
    'isUpcoming': True,
}


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
    rows = directus.get('/items/science_conferences?fields=id,title,url&limit=-1') or []

    for title, url in LINKS.items():
        row = next((r for r in rows if title in (r.get('title') or '')), None)
        if not row:
            print(f'  ! немає конференції «{title}»', file=sys.stderr)
            continue
        if (row.get('url') or '').strip():
            print(f'  = «{title}»: посилання вже є', file=sys.stderr)
            continue
        print(f'  ~ «{title}»: url', file=sys.stderr)
        if not args.dry_run:
            directus.request('PATCH', f'/items/science_conferences/{row["id"]}', payload={'url': url})

    if any(NEW_CONFERENCE['title'] in (r.get('title') or '') for r in rows):
        print(f'  = «{NEW_CONFERENCE["title"]}»: уже є', file=sys.stderr)
    else:
        print(f'  + «{NEW_CONFERENCE["title"]}»', file=sys.stderr)
        if not args.dry_run:
            directus.request('POST', '/items/science_conferences', payload=NEW_CONFERENCE)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
