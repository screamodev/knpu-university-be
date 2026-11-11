# Правки 11.11 — кафедра українознавства і лінгводидактики, «Наукова діяльність»

Лист «сайт кафедри українознавства і лінгводидактики» (В. Піддубна, 11.11 о 10:28, три вкладення) і
пункт «Правки 11.11.26» у Google Doc клієнта. Сторінка:
`/university/structure/kafedra-ukrayinoznavstva-i-lingvodydaktyky/science`.

## Що зроблено

1. Рубрика «Науково-методичні та практичні семінари» — додано 5 семінарів з файлу «Науково-методичні і
   практичні семінари» (2026 → 2024, нові зверху, далі наявні 2023 → 2013), нумерацію знято
   (`<ol>` → `<ul>`).
2. Рубрика «Підготовка аспірантів і докторантів кафедри» — зверху новий запис «Перемога в конкурсі
   наукових робіт» (текст з файлу «Перемога в конкурсі наукових робіт_Штефан» + фото `2026_1.png`).

Контент лежить у фронті: `app/content/structure/kafedra-ukrayinoznavstva-i-lingvodydaktyky/science.uk.json`
(рядка `structure_pages` для цієї кафедри на проді немає, тож BE-патч не потрібен). У BE — лише фото.

## Що куди

| Файл | Де | uuid |
|---|---|---|
| `files/gedroyts-contest-2026.jpg` (1080×1350, з `2026_1.png`) | запис про конкурс Ґедройця | `eea63334-fefb-5e0d-abe2-b6dca0266264` |

uuid детерміновані (uuid5 від імені файла, namespace
`uuid5(NAMESPACE_URL, 'https://hnpu.edu.ua/migration/fixes-2026-11-11')`), тому `/assets/<uuid>` у
фронті збігається на локалі й на проді.

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
DRUN fixes-2026-11-11/push_assets.py --dry-run && DRUN fixes-2026-11-11/push_assets.py
```

Потім фронт: `cd /root/knpu-university-fe && git pull && docker compose -f docker-compose.prod.yml up -d --build`
(перевірити `docker ps --filter name=knpu-university-fe` — «Up N seconds»).

Схема не змінювалась — `apply_schema.py` і права запускати не треба.

## Чого тут немає і чому

Текст клієнта перенесено дослівно, тому в нього лишилися дрібні друкарські огріхи — вони НЕ виправлені,
потрібне рішення клієнта/розробника:

- семінар 27.10.2026: «на уроках **українскої** мови та літератури» (має бути «української»);
- семінар 18.11.2025: у кінці подвійна дужка «… 18 листопада 2025**))**».
