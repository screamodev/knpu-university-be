# Правки 31.10.2026 — Центр розвитку компетентностей учителя: новина про тренінг з ПТСР

Пункт документа «Правки 31.10.26»: на
`/university/structure/teacher-competence-centre/announcements` додати новину. Матеріали — лист
Н. Пономарьової «Новина на сайт та на сторінку Центру» від 30.10 о 16:58 (текст і 13 фото:
`1.jpg`–`6.jpg` і 7 × `photo_2026-10-30_*.jpg`). У листі просили «всі без виключення фото» на
сторінці центру, а фото 1–6 — для новини університету.

| Що | Куди |
| --- | --- |
| `teacher-centre-training-2026-10-30-01…13.jpg` | `/assets/<uuid>` у галереї `photo-grid gallery` нової новини (uuid — у `files.map.json`) |

Порядок фото — як у листі: 01=`photo_…16-37-25`, 02=`photo_…16-12-49`, 03=`5.jpg`, 04=`6.jpg`,
05=`4.jpg`, 06=`photo_…16-05-16`, 07=`photo_…15-50-03`, 08=`2.jpg`, 09=`3.jpg`,
10=`photo_…15-27-35`, 11=`photo_…15-12-19`, 12=`photo_…15-06-10`, 13=`1.jpg`.

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-31-teacher-centre-news/push_assets.py --dry-run   # 13 файлів
DRUN fixes-2026-10-31-teacher-centre-news/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Що зроблено на фронті (без бандла)

`app/content/structure/teacher-competence-centre/announcements.uk.json`: нова секція першою
(свіжа новина зверху) — 5 абзаців тексту з листа дослівно (кожен `text-align: justify`, за
побажанням) + галерея з 13 фото + `<hr />`. Правки тексту — лише технічні: «обговоренореальні» →
«обговорено реальні», прибрано пробіл перед крапкою в «практик .». Підпис і контакти авторки з
листа не переносилися. Вкладка читається зі статичного JSON (у Directus `structure_pages` для
центру рядка немає), тож фронт треба перезібрати (`up -d --build`).

Фото в листі вже ≤1280 px, тому не стискалися.

## Новина в новини університету (стаття в Directus, вносить людина через адмінку)

У листі: «в новинах університету — туди можна взяти фото 1–6» → файли `13`, `08`, `09`, `05`, `03`,
`04` з `files/` цього бандла (= `1.jpg`…`6.jpg`). Текст — той самий, що на сторінці центру.
Заголовка в листі немає; пропонується за зразком попередньої статті: «Відбувся тренінг «Адаптація
освітнього середовища для здобувачів освіти із ПТСР»». Лід (`excerpt`) — перший абзац. Категорія —
«Новини університету» (`university-news`). Обкладинка — `1.jpg` (файл 13). Абзаци по ширині
(`<p style="text-align: justify;">`), фото — по одному `<p><img src="/assets/<uuid>"></p>` після
тексту, як у попередній статті.

## Чого тут немає і чому

* Заголовка в новини центру немає — як і в попередніх новинах на цій вкладці.
* Статті в Directus тут немає: її створює людина через адмінку (див. вище) — після того, як
  `push_assets.py` залив фото на прод.
