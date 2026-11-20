# Правки 20.11.2026 — відділ моніторингу: інфографіка замість «Основних завдань» і «Функцій»

Документ «Правки 16-20.11.2026», вкладка «Правки 20.11.26», пункт «Навчально-методичний відділ
моніторингу та досліджень у сфері освіти». Файл — jpeg з пошти sitehnpu (лист «оформлення
сторінки відділу», 19.11 23:23; клієнт написав, що jpeg чіткіший за pdf).

| Файл | Куди |
| --- | --- |
| `monitoring-zavdannia-funktsii-2026.jpg` (`Navchalno-metodychnyi viddil monitorynhu ta doslidzhen u sferi osvity.jpeg`, 3018×3018, 2,6 МБ) | `app/content/pages/monitoring-department.{uk,en}.json` — одна секція замість «Основні завдання відділу» та «Функції відділу» (uk) / «Main responsibilities» та «Functions» (en) |

Файл НЕ стискався до 1600 px: у нижніх панелях дрібний текст, який при зменшенні не читається
(ліміт Directus на трансформації — 6000 px, 3018 проходить). На сторінці картинка — посилання на
оригінал.

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-11-20/push_assets.py --dry-run && DRUN fixes-2026-11-20/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

uuid файла — uuid5 від імені, тож `/assets/<uuid>` у тексті збігається на локалі й на проді.
