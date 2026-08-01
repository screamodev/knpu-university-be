# Прод-деплой: WYSIWYG, мультикатегории, страницы факультетов, газета «Учитель»

Порядок обязателен. Команды — из `knpu-university-be` на сервере, если не сказано иное.
`DB_HOST`, `DB_USER`, `DB_DATABASE`, `DB_PASSWORD`, `PUBLIC_URL` берутся из `.env`.

Что этот деплой делает необратимого — прочитать до начала:

- **дропает** `articles.category` (данные паркуются в шаге 3),
- **дропает** коллекции `faculties` и `faculty_departments` вместе с содержимым (шаг 2),
- переписывает тела всех статей Markdown → HTML (шаг 9, есть откат),
- заливает ~800 МБ файлов (картинки факультетов + PDF газеты).

## 0. Бэкапы (первым делом)

```bash
# база
docker run --rm --network dbnet -e PGPASSWORD="$DB_PASSWORD" -v "$PWD":/backup postgres:16-alpine \
  pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_DATABASE" -Fc -f /backup/knpu-before-deploy.dump

# файлы Directus (том uploads)
docker run --rm -v knpu-university-be_uploads:/uploads -v "$PWD":/backup alpine \
  tar czf /backup/knpu-uploads-before-deploy.tar.gz -C /uploads .
```

Имя тома проверить через `docker volume ls | grep uploads` — префикс зависит от имени проекта
compose.

## 1. Стянуть код

```bash
git pull
```

## 2. Посмотреть, что применится

```bash
docker compose -f docker-compose.prod.yml exec directus \
  npx directus schema apply --dry-run /directus/snapshots/schema.yaml
```

> Команды `schema diff` в Directus CLI **нет** — только `snapshot` и `apply`; предпросмотр даёт
> флаг `--dry-run`. (Проверено на 11.17.4.)

Ожидаемо в диффе:

- новая junction `articles_categories`, удаление `articles.category`;
- `content`/`contentEn` у `articles` → `input-rich-text-html`;
- новая коллекция `newspaper_issues`;
- **удаление `faculties` и `faculty_departments`** — факультеты теперь статические
  (`app/utils/structure.ts`), коллекции больше не читает никто;
- `articles_photos`, `url-helpers-slug` на slug-полях — правки из соседней ветки.
  `url-helpers-slug` требует расширения `@nialto-services/directus-extension-url-helpers`
  в `extensions/`; без него поле станет обычным инпутом.

**Перед применением проверить, что в дропаемых коллекциях нет реальных данных:**

```bash
curl -s -H "Authorization: Bearer $PROD_TOKEN" \
  "$PROD_URL/items/faculties?fields=name,slug&limit=-1"
```

Локально там лежали только две выдуманные демо-записи. Если на проде кто-то завёл настоящие
факультеты — их место в `structure.ts`, а не в базе; вынести до шага 6.

## 3. Припарковать старые связи статья→категория

Снапшот уже без колонки `category`, поэтому `schema apply` снесёт её вместе с данными.
Скрипт складывает пары в таблицу `articles_categories_legacy`.

```bash
docker run --rm -i --network dbnet -e PGPASSWORD="$DB_PASSWORD" postgres:16-alpine \
  psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_DATABASE" -v ON_ERROR_STOP=1 \
  < snapshots/backfill-article-categories.sql
```

Проверить в выводе: `phase 1: parked N legacy link(s)`, где N — число статей с категорией.
N=0 при непустых категориях — стоп.

## 4. Поднять Directus 11.17.4

В `docker-compose.prod.yml` уже прописаны версия `11.17.4` (вместо 11.1.2) и заголовки CSP,
разрешающие фрейм YouTube/Vimeo в редакторе.

```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f directus   # дождаться healthy
```

Directus сам прогонит свои миграции — отсюда и бэкап в шаге 0.

Проверить, что CSP доехал:

```bash
curl -sD - -o /dev/null "$PROD_URL/admin/" | grep -i content-security-policy | tr ';' '\n' | grep frame-src
```

## 5. Картинки страниц факультетов → прод

Статический контент факультетов лежит в репозитории фронта (`app/content/structure/**`) и
ссылается на файлы по UUID: `/assets/<uuid>`. Те же UUID должны существовать в проде — иначе
~1800 битых картинок.

`images.map.json` (URL → UUID) закоммичен, а Directus принимает явный `id` при загрузке, поэтому
файлы приезжают на прод под теми же идентификаторами и контент пересобирать не нужно.

Прямо на сервере:

```bash
cd ~/knpu-university-be/migration/structure-pages

# сеть, в которой видно контейнер Directus
docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' knpu-university-directus

read -s PROD_TOKEN; export PROD_TOKEN        # админский статик-токен, не в истории

docker run --rm --network webnet -v "$PWD":/work -w /work \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 -e DIRECTUS_TOKEN="$PROD_TOKEN" \
  python:3.12-slim python 3_load_images.py --dry-run

# то же без --dry-run: ~1800 файлов, ~370 МБ, 20–40 минут
```

Скрипт сам пропускает то, что уже загружено (сверяет id по `/files`), так что повторный запуск
безопасен и дешёв. 32 картинки отдают 404 на старом сайте — они и в контенте отсутствуют,
в выводе будут как `failed`.

## 6. Фронт + схема (подряд, тут окно даунтайма новостей)

Старый фронт запрашивает поле `category`, новый — `categories`. Между деплоем фронта и
`schema apply` страницы новостей отдают ошибку, поэтому шаги идут вплотную.

Сначала задеплоить `knpu-university-fe` (с контентом из шага 5) и добавить переменные:

```
NUXT_PREVIEW_SECRET=<секрет>
NUXT_DIRECTUS_PREVIEW_TOKEN=<токен>
```

Сразу за ним:

```bash
docker compose -f docker-compose.prod.yml exec directus \
  npx directus schema apply /directus/snapshots/schema.yaml -y
```

## 7. Залить категории в junction

Тот же файл, что в шаге 3 — теперь он отрабатывает вторую фазу.

```bash
docker run --rm -i --network dbnet -e PGPASSWORD="$DB_PASSWORD" postgres:16-alpine \
  psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_DATABASE" -v ON_ERROR_STOP=1 \
  < snapshots/backfill-article-categories.sql
```

Ждём `phase 2: inserted N junction row(s)` с тем же N, что в шаге 3.

## 8. Права, папки, роль редактора

`schema apply` стирает `preview_url` и не трогает права — поэтому этот шаг идёт после **любого**
`schema apply`, в том числе будущего.

```bash
# публичный read: junction категорий, newspaper_issues и всё остальное
docker compose -f docker-compose.prod.yml exec directus \
  sh /directus/snapshots/bootstrap-public-access.sh

# папки «Новини» и «Газета «Учитель»», пресеты картинок, preview_url
docker compose -f docker-compose.prod.yml exec \
  -e SITE_URL=https://<прод-домен> \
  -e PREVIEW_SECRET=<тот же секрет> \
  -e PREVIEW_TOKEN=<тот же токен> \
  directus sh /directus/snapshots/bootstrap-editor-experience.sh

# роль Editor: articles, categories, junctions, newspaper_issues, файлы
docker compose -f docker-compose.prod.yml exec directus \
  sh /directus/snapshots/bootstrap-editor-role.sh

# или сразу с пользователем:
# docker compose -f docker-compose.prod.yml exec \
#   -e EDITOR_EMAIL=editor@hnpu.edu.ua \
#   -e EDITOR_PASSWORD='…' \
#   directus sh /directus/snapshots/bootstrap-editor-role.sh
```

## 9. Конвертация Markdown → HTML

Три прогона, по нарастающей. `$PROD_TOKEN` — админский токен Directus.

```bash
cd migration/md-to-html
docker run --rm -v "$PWD":/work -w /work \
  -e DIRECTUS_URL="$PROD_URL" -e DIRECTUS_TOKEN="$PROD_TOKEN" node:22-slim \
  sh -c "npm install --silent && node convert.mjs --dry-run"

# то же с --limit 10, глянуть 10 статей на сайте, потом без флагов — полный прогон
```

Скрипт печатает путь к бэкапу тел статей. Откат: `node restore.mjs <путь-к-бэкапу>`.
Уже сконвертированные статьи пропускаются, повторный запуск безопасен.

## 10. Категории факультетов для вкладки «Новини»

Создаёт 9 категорий (по одной на институт/факультет) и проставляет их статьям по ключевым
словам. Без этого вкладка «Новини» на странице факультета пустая.

```bash
cd migration/structure-pages
DIRECTUS_URL=$PROD_URL DIRECTUS_TOKEN=$PROD_TOKEN python3 5_tag_news.py --dry-run
DIRECTUS_URL=$PROD_URL DIRECTUS_TOKEN=$PROD_TOKEN python3 5_tag_news.py
```

Идемпотентно: существующие связи не дублируются, чужие категории не трогаются.

## 11. Архив газеты «Учитель»

97 номеров, ~450 МБ. Коллекция `newspaper_issues` появилась в шаге 6.

```bash
cd migration/newspaper
python3 1_fetch.py --report            # читает архив со старого сайта → issues.json

docker run --rm -v "$PWD":/work -w /work \
  -e DIRECTUS_URL="$PROD_URL" -e DIRECTUS_TOKEN="$PROD_TOKEN" python:3.12-slim \
  python 2_load.py --dry-run

... python 2_load.py --limit 5         # проверить 5 номеров на сайте
... python 2_load.py                   # остальные, ~20–40 минут
```

`files.map.json` привязан к окружению — если гонял локально, сначала `mv files.map.json
files.map.local.json`. Повторный запуск безопасен: файлы берутся из карты, строки ищутся
по `serial`.

## 12. Проверка

```bash
# категории приходят анониму
curl "$PROD_URL/items/articles?fields=slug,categories.categories_id.slug&limit=3"

# газета отдаётся анониму
curl "$PROD_URL/items/newspaper_issues?fields=number,serial,issueDate&limit=3&sort=-issueDate"

# на страницах факультетов не осталось ссылок на старый сайт
curl -s https://<прод-домен>/university/structure/arts/science | grep -c 'hnpu.edu.ua/sites'   # 0
```

Глазами:

- новости и пара статей открываются, у статьи видны категории;
- в админке в статье поле Categories даёт выбрать несколько, тело — форматированный текст,
  а не `##` и `**`; кнопка превью открывает сплит-вью с сайтом; видео с YouTube в редакторе
  не блокируется;
- `/university/structure/arts` — вкладки переключаются, картинки грузятся с `/assets/`;
- `/university/newspaper` — 97 номеров, фильтр по годам, PDF скачивается;
- `/university/faculties` и `/education/faculties` открываются (они больше не ходят в Directus);
- зайти **редактором** (не админом) и добавить номер газеты — он появляется на сайте без деплоя.

## Мелочи после деплоя

- `articles_categories_legacy` оставлена как страховка. Когда всё подтвердилось:
  `DROP TABLE articles_categories_legacy;`
- Прод-токен админа, который светился в переписке, всё ещё не ротирован.
- Миграция старых новостей с Drupal (`migration/legacy-news`) пишет M2M — запускать только после
  этого деплоя.
- Диск: ~370 МБ картинок факультетов + ~450 МБ PDF газеты. Проверить свободное место до шага 5.
- В архиве газеты у пяти номеров год в подписи не совпадает с годом в имени файла (например
  `№ 1 (241) Січень 2017` ведёт на файл 2016 года) — это данные заказчика, `1_fetch.py` их
  печатает; спросить редакцию.
