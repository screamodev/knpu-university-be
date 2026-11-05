# Правки 05.11 — PDF відділу наукової, інноваційної і міжнародної діяльності

Лист «Для розміщення на сайті» (Наукова частина, Т. Ярмак, 05.11 о 15:05): розмістити на
`/science/activity` поряд із текстом про відділ (на макеті — дві кнопки праворуч) два PDF.

## Що куди

| Файл | Підпис кнопки | uuid |
|---|---|---|
| `files/science-plan-2026-2027.pdf` | План наукової роботи ХНПУ імені Г. С. Сковороди на 2026-27 навчальний рік | `e441c552-3503-5ca2-8ccf-7e0312bd0cf6` |
| `files/science-week-2026.pdf` | Тиждень науки присвячений Всесвітньому дню науки в ім’я миру та розвитку | `5495865b-3fe7-5224-b8f3-8f91eeb240b8` |

uuid детерміновані (uuid5 від імені файла, namespace
`uuid5(NAMESPACE_URL, 'https://hnpu.edu.ua/migration/fixes-2026-11-05')`), тому `/assets/<uuid>`
у фронті збігається на локалі й на проді. Підписи — `science.activity.documents.*` в
`app/locales/{uk,en}.json` фронта; у підписах лише технічні правки (`"` → `’` в «ім’я», без
кінцевої крапки).

## Як накотити

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-11-05/push_assets.py --dry-run && DRUN fixes-2026-11-05/push_assets.py
```

Потім фронт: `cd /root/knpu-university-fe && git pull && docker compose -f docker-compose.prod.yml up -d --build`.

Схема не змінювалась — `apply_schema.py` і права запускати не треба.

## Чого тут немає і чому

Посилання на сторінку викладача «Васильєва Оксана Вікторівна» (кафедра музичного мистецтва)
внесено лише у фронт (`home.uk.json`), у BE нічого не потрібно: рядка `structure_pages` для цієї
кафедри на проді немає. Посилання з листа веде на **редактор** Google Sites
(`…/edit?pli=1&authuser=1`) і для відвідувача без доступу відкриває логін Google — поставлено
як є за рішенням розробника; клієнту варто попросити опубліковане посилання.
