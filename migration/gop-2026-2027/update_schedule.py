#!/usr/bin/env python3
"""
Перевести «Графік освітнього процесу» на 2026/2027 навчальний рік.

Сторінка `/education/schedule` показує семестри з `education_schedule_periods` і ключові дати
з `education_schedule_key_dates`. Обидві колекції стояли на 2025/2026, і клієнт попросив
оновити роки, коли навчальний відділ надіслав ГОП 2026/2027.

Дати взяті з «Додатка 1 до наказу № 122-од від 30.06.2026» — графіка для **першого
(бакалаврського) рівня**: сторінка показує один загальний графік, а бакалаврат — найбільший
контингент. Графіки магістратури й аспірантури відрізняються (у них інші межі семестрів) і
лежать поруч окремими документами в розділі «Затверджені графіки».

    export DIRECTUS_URL=https://admin.hnpu.edu.ua
    export DIRECTUS_TOKEN=…
    python3 update_schedule.py --dry-run
    python3 update_schedule.py

Ідемпотентний: рядки, які вже стоять на 2026-2027, пропускаються. Рядки шукаються за
`academicYear` + `order`, не за id, бо id на кожному середовищі свої.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

FROM_YEAR = '2025-2026'
TO_YEAR = '2026-2027'

# order → нові значення. Порядок і типи лишаються ті самі, змінюються назви й дати.
PERIODS = {
    1: dict(name='Осінній навчальний семестр', nameEn='Autumn study semester',
            semesterType='autumn', periodType='study',
            dateStart='2026-09-01', dateEnd='2026-12-12'),
    2: dict(name='Зимова екзаменаційна сесія', nameEn='Winter exam session',
            semesterType='autumn', periodType='exam',
            dateStart='2026-12-14', dateEnd='2026-12-26'),
    3: dict(name='Зимові канікули', nameEn='Winter vacation',
            semesterType='spring', periodType='vacation',
            dateStart='2026-12-28', dateEnd='2027-01-17'),
    4: dict(name='Весняний навчальний семестр', nameEn='Spring study semester',
            semesterType='spring', periodType='study',
            dateStart='2027-01-18', dateEnd='2027-06-16'),
    5: dict(name='Літня екзаменаційна сесія та підсумкова атестація',
            nameEn='Summer exam session and final assessment',
            semesterType='spring', periodType='exam',
            dateStart='2027-06-17', dateEnd='2027-06-30'),
    # Було «Виробнича практика»: у графіку 2026/2027 практика не виділена в окремий період —
    # вона входить до «теоретичне навчання / практична підготовка». Натомість показуємо літні
    # канікули, які в графіку є.
    6: dict(name='Літні канікули', nameEn='Summer vacation',
            semesterType='spring', periodType='vacation',
            dateStart='2027-07-01', dateEnd='2027-08-31'),
}

# order → нові значення. «День першокурсника» і «Вручення дипломів» у графіку не названі, тож
# замість них стоять дати, які в ньому є; свої події відділ додасть в адмінці сам.
KEY_DATES = {
    1: dict(event='Початок навчального року', eventEn='Academic year start',
            dateLabel='1 вересня 2026', dateLabelEn='September 1, 2026'),
    2: dict(event='Початок зимової сесії', eventEn='Winter session start',
            dateLabel='14 грудня 2026', dateLabelEn='December 14, 2026'),
    3: dict(event='Останній день І семестру', eventEn='End of the first semester',
            dateLabel='26 грудня 2026', dateLabelEn='December 26, 2026'),
    4: dict(event='Початок ІІ семестру', eventEn='Second semester start',
            dateLabel='18 січня 2027', dateLabelEn='January 18, 2027'),
    5: dict(event='Початок літньої сесії', eventEn='Summer session start',
            dateLabel='17 червня 2027', dateLabelEn='June 17, 2027'),
    6: dict(event='Останній день навчального року', eventEn='End of the academic year',
            dateLabel='30 червня 2027', dateLabelEn='June 30, 2027'),
}


class Directus:
    def __init__(self, base: str, token: str):
        self.base = base.rstrip('/')
        self.token = token

    def request(self, method: str, path: str, payload=None):
        headers = {'Authorization': f'Bearer {self.token}'}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(f'{self.base}{path}', data=data,
                                         headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read()
        return json.loads(body)['data'] if body else None


def login(base: str, email: str, password: str) -> str:
    request = urllib.request.Request(
        f'{base.rstrip("/")}/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())['data']['access_token']


def update(directus: Directus, collection: str, values: dict[int, dict], dry_run: bool) -> int:
    rows = directus.request('GET', f'/items/{collection}?limit=-1&sort=order') or []
    done = [row for row in rows if row.get('academicYear') == TO_YEAR]
    if done:
        print(f'{collection}: {len(done)} рядків уже на {TO_YEAR}, пропускаю')
        return 0
    todo = [row for row in rows if row.get('academicYear') == FROM_YEAR]
    if len(todo) != len(values):
        print(f'{collection}: очікував {len(values)} рядків за {FROM_YEAR}, знайшов {len(todo)} — '
              'зупиняюсь, звірте вручну', file=sys.stderr)
        return -1

    changed = 0
    for row in todo:
        new = values.get(row['order'])
        if not new:
            print(f"{collection}: немає значень для order={row['order']}", file=sys.stderr)
            return -1
        label = new.get('name') or new.get('event')
        was = row.get('name') or row.get('event')
        print(f"  {row['order']}. {was}  →  {label}")
        if not dry_run:
            directus.request('PATCH', f"/items/{collection}/{row['id']}",
                             payload={**new, 'academicYear': TO_YEAR})
        changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    try:
        periods = update(directus, 'education_schedule_periods', PERIODS, args.dry_run)
        key_dates = update(directus, 'education_schedule_key_dates', KEY_DATES, args.dry_run)
    except urllib.error.HTTPError as exc:
        print(f'! {exc.code}: {exc.read().decode("utf-8", "replace")[:600]}', file=sys.stderr)
        return 1

    if periods < 0 or key_dates < 0:
        return 1
    print(f'періодів {periods}, ключових дат {key_dates}'
          + (' — dry run, нічого не записано.' if args.dry_run else ' — оновлено.'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
