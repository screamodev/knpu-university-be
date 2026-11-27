# Правки 27.11 — структура університету

Пункт «Структура університету» в Google Doc клієнта (Правки 27.11.26) + лист «СТРУКТУРА» від 27.11
(відділ менеджменту і моніторингу), вкладення «Struktura 05.11.2026 .pdf» (11 с., 1 337 981 байт, створений 27.11).

## Що зроблено

BE (цей бандл): у рядку `documents` `0d1c82cb-7456-4373-9b79-1d6b10d02a91` (розділ `university-structure`)
підмінено файл на новий PDF. Назва та дата під схемою не змінювались — на схемі та сама «станом 05.11.2026».

FE (`knpu-university-fe`):
- «Відділ навчально-наукової та проєктної діяльності» → «Навчально-науковий центр інноваційної та проєктної
  діяльності» (структура — тепер у «Центрах»; меню «Наука»; сторінка `/science/activity`, uk і en);
- обидва «Навчально-методичні відділи» перенесені з «Інші підрозділи» до «Відділи та служби».

## Що куди

| Файл | Де | uuid |
|---|---|---|
| `files/struktura-2026-11-27.pdf` | документ схеми на `/university/structure` | `b5e9a4fc-13d8-5568-a51e-4247af81e669` |

uuid детерміновані (uuid5 від імені файла, namespace
`uuid5(NAMESPACE_URL, 'https://hnpu.edu.ua/migration/fixes-2026-11-27-structure')`).

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
DRUN fixes-2026-11-27-structure/push_assets.py --dry-run && DRUN fixes-2026-11-27-structure/push_assets.py
DRUN fixes-2026-11-27-structure/patch_chart.py --dry-run && DRUN fixes-2026-11-27-structure/patch_chart.py
```

Фронт треба перезібрати (змінено список підрозділів і назву центру); саме посилання на схему береться з рядка
`documents` у Directus.
Схема БД не змінювалась — `apply_schema.py` і права запускати не треба. Обидва скрипти ідемпотентні.

Перевірка після викатки:

```bash
curl -s -G 'https://admin.hnpu.edu.ua/items/documents' \
  --data-urlencode 'filter[section][_eq]=university-structure' --data-urlencode 'fields=title,file'
curl -sI https://admin.hnpu.edu.ua/assets/b5e9a4fc-13d8-5568-a51e-4247af81e669 | head -3   # 200, application/pdf
```

## Що уточнити в клієнта

- «Відділ практик» на 1-й сторінці схеми є, а в текстовій структурі сайту його немає (прибраний за листом 11.11).
- Посада на `/science/activity` лишилась «Начальник відділу» — нову назву посади клієнт не повідомляв.
- Додатки (с. 2–11) на відмінності з текстовою структурою не перевіряли.
