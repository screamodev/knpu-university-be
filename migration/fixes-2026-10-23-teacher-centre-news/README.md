# Правки 23.10.2026 — Центр розвитку компетентностей учителя: новина про тренінг

Пункт документа «Правки 23.10.26»: на сторінці
`/university/structure/teacher-competence-centre/announcements` (вкладка «Новини») додати текст
і фото у вигляді новини. Матеріали — лист Н. Пономарьової «До новин» від 22.10 о 17:58
(текст і 14 фото: `1.jpg`–`6.jpg` і 8 × `photo_2026-10-22_*.jpg`). У листі просили «всі без
винятку фото» — на сторінці центру всі 14.

| Що | Куди |
| --- | --- |
| `teacher-centre-training-2026-10-22-01…14.jpg` | `/assets/<uuid>` у галереї `photo-grid gallery` нової новини (uuid — у `files.map.json`) |

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-23-teacher-centre-news/push_assets.py --dry-run   # 14 файлів
DRUN fixes-2026-10-23-teacher-centre-news/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Що зроблено на фронті (без бандла)

`app/content/structure/teacher-competence-centre/announcements.uk.json`: нова секція першою
(свіжа новина зверху) — 4 абзаци тексту з листа дослівно + галерея з 14 фото + `<hr />`.
Єдина правка тексту — прибрано пробіл перед крапкою в «практик .». Вкладка читається зі
статичного JSON (у Directus `structure_pages` для центру рядка немає), тож фронт треба
перезібрати (`up -d --build`).

Фото в листі вже 1280 px, тому не стискалися.

## Чого тут немає і чому

* **Новина в новинах університету** (фото 1–5, про що теж просять у листі) — це стаття в
  Directus, її вносить людина через адмінку; у бандлі її немає.
* Заголовка в новини центру немає — як і в попередній новині на цій вкладці (відкриття центру).
