# Правки 30.10.2026 — Центр розвитку компетентностей учителя: новина про тренінг

Пункт документа «Правки 30.10.26»: на сторінці
`/university/structure/teacher-competence-centre/announcements` додати новину. Матеріали — лист
Н. Пономарьової «Новина на сайт та на сторінку Центру» від 29.10 о 20:20 (текст і 14 фото:
`11.jpg`–`15.jpg` і 9 × `photo_2026-10-29_*.jpg`). У листі просили «всі без виключення фото» на
сторінці центру, а фото 11–15 — для новини університету.

| Що | Куди |
| --- | --- |
| `teacher-centre-training-2026-10-29-01…14.jpg` | `/assets/<uuid>` у галереї `photo-grid gallery` нової новини (uuid — у `files.map.json`) |

Порядок фото — як у листі: 01=`11.jpg`, 02=`photo_…15-24-03`, 03=`photo_…15-15-59`, 04=`12.jpg`,
05=`13.jpg`, 06=`photo_…15-28-44`, 07=`photo_…15-26-03`, 08=`photo_…15-42-07`,
09=`photo_…15-39-42`, 10=`14.jpg`, 11=`photo_…15-47-37`, 12=`15.jpg`, 13=`photo_…16-07-58`,
14=`photo_…16-16-24`.

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-30-teacher-centre-news/push_assets.py --dry-run   # 14 файлів
DRUN fixes-2026-10-30-teacher-centre-news/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Що зроблено на фронті (без бандла)

`app/content/structure/teacher-competence-centre/announcements.uk.json`: нова секція першою
(свіжа новина зверху) — 5 абзаців тексту з листа дослівно + галерея з 14 фото + `<hr />`.
Єдина правка тексту — прибрано пробіл перед крапкою в «практик .». Вкладка читається зі
статичного JSON (у Directus `structure_pages` для центру рядка немає), тож фронт треба
перезібрати (`up -d --build`).

Фото в листі вже 1280 px, тому не стискалися.

## Новина в новини університету (стаття в Directus, вносить людина через адмінку)

У листі: «в новинах університету — туди можна взяти фото 11–15» → файли `01`, `04`, `05`, `10`,
`12` з `files/` цього бандла (= `11.jpg`…`15.jpg`). Текст — той самий, що на сторінці центру.
Заголовка в листі немає; пропонується назва тренінгу з першого абзацу: «Цифрові навички для
забезпечення сталості освіти в Україні». Лід (`excerpt`) — перший абзац.

## Чого тут немає і чому

* Заголовка в новини центру немає — як і в попередніх новинах на цій вкладці.
* Статті в Directus тут немає: її створює людина через адмінку (див. вище).
