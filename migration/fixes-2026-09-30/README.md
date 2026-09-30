# Правки 30.09.2026, п. 6 — Моніторинг: «Анкета по факультетам»

Документ клієнта «Правки 30.09.26», пункт «Моніторинг» (`/education/monitoring`): у розділі
«Освітня екосистема» під **АНКЕТА № 1** розмістити «Анкету по факультетам» (клікабельний заголовок)
і під нею 10 факультетів/інститутів — кожен посиланням на свою Google-форму.

Анкета № 1 та всі інші рядки `monitoring_surveys` **не змінюються**: бандл лише створює 11 нових.

## Що в бандлі

`data/monitoring-faculties.json` — 11 нових рядків `monitoring_surveys`
(`area: educational-ecosystem`, `status: published`):

| number | title | formUrl | order |
| --- | --- | --- | --- |
| `1/0` | Анкета по факультетам | — (заголовок вкладеного акордеона) | 29 |
| `1/1` … `1/10` | 10 факультетів/інститутів дослівно з документа | форма факультету | 30–39 |

## Як накотити на прод

```bash
# 1. Бекап бази
cd /root/knpu-university-be
set -a; . ./.env; set +a
docker run --rm --network dbnet -e PGPASSWORD="$DB_PASSWORD" -v "$PWD":/backup postgres:16-alpine \
  pg_dump -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_DATABASE" \
  -Fc -f /backup/knpu-2026-09-30-before-monitoring.dump
ls -lh knpu-2026-09-30-before-monitoring.dump

# 2. Код
git pull

# 3. Дані
cd migration
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN pass2/load.py fixes-2026-09-30/data/monitoring-faculties.json --dry-run   # 11 rows
DRUN pass2/load.py fixes-2026-09-30/data/monitoring-faculties.json             # created=11

# 4. Перевірка
curl -s -G "https://admin.hnpu.edu.ua/items/monitoring_surveys" \
  --data-urlencode "filter[number][_starts_with]=1/" --data-urlencode "fields=number,title" \
  --data-urlencode "limit=-1"

# 5. Фронт
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

Відкат: в адмінці **Content → Monitoring surveys**, фільтр `Number` починається з `1/`, виділити
11 рядків → Delete. Або відновити базу з дампа кроку 1 (крайній випадок).

## Як зробити те саме руками в адмінці (наступного разу)

Схема: «анкета в анкеті» = кілька рядків колекції **Monitoring surveys** з номерами `N/0`, `N/1`,
`N/2`… Фронт сам збирає їх в один акордеон за номером; окремо нічого налаштовувати не треба.

1. Адмінка `admin.hnpu.edu.ua` → **Content → Monitoring surveys**.
2. Знайти батьківську анкету (наприклад, №1) — вона лишається як є.
3. **Create Item** (плюс) і створити **заголовок групи**:
   - `Number` = `1/0`; `Area` = така сама, як у батьківської (Освітня екосистема);
   - `Title` = назва групи («Анкета по факультетам»); `Form url` — порожньо;
   - `Order` = число більше за поточні (на 30.09 максимум було 28; беріть 29 і далі);
   - `Status` = Published → Save.
4. Створити кожну вкладену анкету: `Number` = `1/1`, `1/2`… (по одному на кожен факультет),
   та сама `Area`, `Title` = назва факультету, `Form url` = посилання на форму,
   `Order` = 30, 31… (послідовно), `Status` = Published.
5. **Головне обмеження:** якщо номер батьківської анкети (тут `1`) ще не входить до списку
   `CLUSTERED_NUMBERS` у `knpu-university-fe/app/pages/education/monitoring.vue`, група не
   з'явиться — її треба додати в код (так зроблено для `1`, `11`, `22`). Для номера, якого там
   ще немає, потрібна правка фронта й ребілд.
6. Перевірити `hnpu.edu.ua/education/monitoring` (Ctrl+F5): у картці анкети — заголовок групи, він
   розкривається і показує список.

## Чого тут немає

- Посилання для самого заголовка «Анкета по факультетам» клієнт не надав: заголовок лише розкриває
  список (клікабельний як акордеон). Якщо пізніше знадобиться, щоб він вів на форму, це окрема правка
  фронта.
