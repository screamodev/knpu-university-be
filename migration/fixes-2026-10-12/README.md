# Правки 12.10.2026, п. 2 — факультет історії і права, вкладка «Виховна діяльність»

Документ «Правки 12.10.26», пункт 2: на `/university/structure/history-law/students` додати текст і
фото з пошти. Лист В. Вороніна «Доброго ранку! прошу додати новину на сторінки:» (12.10, 07:42,
переслано на sitehnpu@): `News_10_01.docx` і 5 фото `news_01_10_1…5.jpg`. Просить розмістити матеріал
на двох сторінках: «Виховна діяльність» і «Новини» факультету.

| Що | Куди |
| --- | --- |
| урок «Козацька слава» (01.10.2026): 4 абзаци дослівно з docx + 5 фото | `knpu-university-fe/app/content/structure/history-law/students.uk.json`, над «Посвятою у першокурсники» |
| 5 фото (JPEG ≤1600 px, `files/`) | медіатека (`push_assets.py`) |

Заголовка в docx немає, тож його не вигадували: заголовок «Урок "Козацька слава" (он-лайн)» дала
людина (12.10), він стоїть перед текстом як `<p><strong>…</strong></p>`, як «Посвята у
першокурсники». Підпис до фото в `alt` — «Урок «Козацька слава» (онлайн), 01.10.2026» (на самій
сторінці підписів під фото немає, як і в сусідніх подіях).

## Як це влаштовано

* `build.py` бере 5 фото з розпакованого zip «Скачати все» з листа, стискає їх Pillow у `files/`,
  пише `files.map.json` (uuid5 у просторі `…/migration/fixes-2026-10-12`) і вставляє блок у
  `students.uk.json` одразу після першого `<hr />`. Ідемпотентний: другий запуск блок не дублює
  (маркер — `<strong>01 жовтня 2026 р.</strong>`).
* Вкладку читає статичний JSON: рядків у `structure_pages` для `history-law` немає (перевірено API
  прода 12.10), тож фронт треба перезібрати.
* Команда збірки (Pillow через контейнер) — у докстрингу `build.py`.

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
DRUN fixes-2026-10-12/push_assets.py --dry-run   # 5 у карті · 0 уже на цілі · 5 залити
DRUN fixes-2026-10-12/push_assets.py             # в кінці: uploaded=5 failed=0
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Чого тут немає і чому

* **Новина у «Новини» факультету** — не створювалась. Додається вручну через адмін-панель
  (колекція `articles`, категорія «Факультет історії і права», `fakultet-istoriyi-i-prava`); текст і
  фото ті самі, фото — послідовними `<p><img>` (кнопка «Додати фото до Content»). Заголовок для вкладки
  вже визначено: «Урок "Козацька слава" (он-лайн)».

---

# Правки 12.10.2026, п. 5 — Моніторинг: видалено «Анкету по факультетам» з АНКЕТИ № 1

Документ «Правки 12.10.26», пункт 5 (ТЕРМІНОВО): `/education/monitoring`, розділ «Освітня
екосистема», АНКЕТА № 1 — видалити вкладену «Анкету по факультетам». Людина уточнила (12.10):
видаляється і заголовок, і всі 10 вкладених анкет.

Це 11 рядків `monitoring_surveys`, створені бандлом `fixes-2026-09-30`: `1/0` «Анкета по факультетам»
і `1/1…1/10` (10 факультетів/інститутів). `delete_monitoring_faculties.py` знаходить їх за парою
(number, title) з `fixes-2026-09-30/data/monitoring-faculties.json` (id на локалі й проді різні) і
видаляє. Рядок із результатами чи файлом програми не видаляє — зупиняється з кодом 1. Ідемпотентний.
Сама анкета № 1 (`number = 1`, результати 2021–2026) не чіпається. Фронт без змін — перебудова не потрібна.

## Накотити на прод (виконує людина)

```bash
# 1. Бекап бази
cd /root/knpu-university-be
set -a; . ./.env; set +a
docker run --rm --network dbnet -e PGPASSWORD="$DB_PASSWORD" -v "$PWD":/backup postgres:16-alpine \
  pg_dump -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_DATABASE" \
  -Fc -f /backup/knpu-2026-10-12-before-monitoring-delete.dump
ls -lh knpu-2026-10-12-before-monitoring-delete.dump

# 2. Код і видалення
git pull
cd migration
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-12/delete_monitoring_faculties.py --dry-run   # 11 рядків «- 1/N …», «до видалення: 11»
DRUN fixes-2026-10-12/delete_monitoring_faculties.py             # «видалено: 11»

# 3. Перевірка (має бути порожньо)
curl -s -G "https://admin.hnpu.edu.ua/items/monitoring_surveys" \
  --data-urlencode "filter[number][_starts_with]=1/" --data-urlencode "fields=number,title"
```

Відкат: `DRUN pass2/load.py fixes-2026-09-30/data/monitoring-faculties.json` створить ті самі 11 рядків
заново (або відновлення з дампа кроку 1).

## Чого тут немає і чому

* `CLUSTERED_NUMBERS` у `monitoring.vue` лишається з `1`: механізм «анкета в анкеті» (`N/0`) знадобиться
  надалі й нічого не ламає, коли вкладених рядків немає.
