# Правки 12.11 — структура університету: нова оргсхема (заміна файла)

Пункт «Структура університету» в Google Doc клієнта (Правки 12.11.26): «Замінити схему на нову (файл на пошті)».
Файл — «Структура 05.11.2026 — копия.pdf» з пошти (9 с., 1 307 862 байт, створений 12.11 об 11:48 UTC; попередній
`struktura-2026-11-05.pdf` — 1 305 696 байт).

## Що зроблено

BE (цей бандл):

1. «Організаційно-структурна схема» на `/university/structure` (розділ документів `university-structure`):
   у тому самому рядку `documents` (`0d1c82cb-7456-4373-9b79-1d6b10d02a91`) підмінено файл на новий PDF.
   Назва лишається «Організаційно-структурна схема (станом на 05.11.2026 року)» — на першій сторінці нової схеми
   стоїть та сама дата: «Організаційно-структурна схема ХНПУ імені Г.С. Сковороди (станом на 05.11.2026)».

FE не змінювався (дата під схемою `university.structure.asOf` — 05.11.2026, як і була).

## Що куди

| Файл | Де | uuid |
|---|---|---|
| `files/struktura-2026-11-12.pdf` (9 с.) | документ схеми на `/university/structure` | `2a976ac5-05f4-5bb3-8174-8f0ceb4d433b` |

uuid детерміновані (uuid5 від імені файла, namespace
`uuid5(NAMESPACE_URL, 'https://hnpu.edu.ua/migration/fixes-2026-11-12-structure')`).

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
DRUN fixes-2026-11-12-structure/push_assets.py --dry-run && DRUN fixes-2026-11-12-structure/push_assets.py
DRUN fixes-2026-11-12-structure/patch_chart.py --dry-run && DRUN fixes-2026-11-12-structure/patch_chart.py
```

Фронт перезбирати НЕ треба (код не чіпали): посилання на схему береться з рядка `documents` у Directus.
Схема БД не змінювалась — `apply_schema.py` і права запускати не треба. Обидва скрипти ідемпотентні.

Перевірка після викатки:

```bash
curl -s -G 'https://admin.hnpu.edu.ua/items/documents' \
  --data-urlencode 'filter[section][_eq]=university-structure' --data-urlencode 'fields=title,file'
curl -sI https://admin.hnpu.edu.ua/assets/2a976ac5-05f4-5bb3-8174-8f0ceb4d433b | head -3   # 200, application/pdf
```

## Чого тут немає і чому

- **«Відділ практик».** У попередньому PDF (від 05.11, викачаний 11.11) відділу практик на схемі не було — за листом
  клієнта 11.11 («Ліквідовано Відділ практик») ми прибрали його зі структури на сайті (`app/utils/structure.ts`).
  У НОВОМУ PDF «Відділ практик» знову є в колонці першого проректора (1-а сторінка, під «Навчальний відділ»).
  Сайт (список підрозділів) і схема тепер розходяться. Нічого не міняли — клієнт про це не писав; треба уточнити, чи
  повертати «Відділ практик» у структуру на сайті. Порівнювали лише 1-у сторінку, додатки (с. 2–9) на відмінності не
  переглядали.
- Дата в назві схеми не змінювалась (05.11.2026 на самій схемі).
