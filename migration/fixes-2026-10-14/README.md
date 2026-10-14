# Правки 14.10.2026, п. 2 — Центр розвитку компетентностей учителя, вкладка «Анонси подій»

Документ «Правки 12.10.26 / 14.10.26», пункт 2: на `/university/structure/teacher-competence-centre`
створити вкладку «Анонси подій» і наповнити її з файлів листа Н. Пономарьової (14.10, 16:21,
переслано на sitehnpu@): `пРО ТРЕНІНГИ.docx`, `Тренінги 2026 ХНПУ.png` (постер),
`пРО НАУМОВСЬКІ ЧИТАННЯ.docx`.

| Що | Куди |
| --- | --- |
| онлайн-тренінги 22, 29, 30 жовтня: текст дослівно з docx + постер одразу за текстом | `knpu-university-fe/app/content/structure/teacher-competence-centre/events.uk.json` |
| конференція «Наумовські читання» (19–20.11.2026): текст дослівно з docx, після `<hr />` | там само |
| постер (JPEG, `files/`) | медіатека (`push_assets.py`) |

Новий id вкладки `events` («Анонси подій» / «Event announcements») додано у `STRUCTURE_TAB_IDS`,
іконку плитки (`globe`), локалі та `manifest.json` центру (`tabs` і `tabNav`, останньою після «Новини»).
Наявна вкладка `announcements` цього підрозділу підписана «Новини» — її не чіпали.

## Як це влаштовано

* `data/events-trainings.html` і `data/events-naumov.html` — текст docx дослівно (жирне → `<strong>`,
  посилання → `<a>`, пункти «Форми участі» → `<ul>`). Рядок-вказівка «ВНИЗУ ДОДАЙТЕ ПОСТЕР
  ТРЕНІНГІВ» виконана, на сторінку не перенесена.
* `build.py` перекодовує постер у JPEG, пише `files.map.json` (uuid5 у просторі
  `…/migration/fixes-2026-10-14`) і збирає `events.uk.json`. Команда збірки (Pillow через контейнер) —
  у докстрингу.
* Вкладку читає статичний JSON: рядків у `structure_pages` для `teacher-competence-centre` немає
  (перевірено API прода 14.10), тож фронт треба перезібрати.

## Накотити на прод (виконує людина)

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-14/push_assets.py --dry-run   # 1 у карті · 0 уже на цілі · 1 залити
DRUN fixes-2026-10-14/push_assets.py             # в кінці: uploaded=1 failed=0
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Чого тут немає і чому

* **Новин у «Новини»** — не створювалось: клієнт просив саме розділ «Анонси подій».
* **Заголовків над блоками** — немає: у docx їх нема, свого не вигадували (кожен блок починається
  першим рядком документа, «📢 Запрошуємо…»).
