# Прод-деплой

- **Часть 1** — WYSIWYG, мультикатегории, страницы факультетов, газета «Учитель». **Выполнена на проде.** Оставлена как справка; повторно не гонять.
- **Часть 2** — вторая волна миграции (документы, аспирантура, оголошення). **Не выполнена.**
- **Часть 3** — студентский парламент, партнёры, центр якості, превью газеты, чистка меню.
  **Не выполнена**, едет вместе с частью 2 (сначала часть 2, потом часть 3).
- **Часть 4** — деканаты карточками, финансовая деятельность, виджет закупівель, логотипы
  партнёров, вычистка выдуманных данных. **Не выполнена**, идёт после части 3.

---

# Часть 1: WYSIWYG, мультикатегории, страницы факультетов, газета «Учитель»

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

---

# Часть 2: документы, отдел аспирантуры, оголошення

Вторая волна миграции. Порядок обязателен, команды — из `knpu-university-be` на сервере.

Отличие от части 1: **необратимого почти ничего нет**. `schema apply` только добавляет
коллекцию `documents` и один вариант в списке `documents.section`; ничего не дропается.
Загружается ~250 файлов (~150 МБ) — заметно меньше, чем в первой части.

Что именно приезжает:

- коллекция `documents` — одна на все списки документов раздела «Відвідувачу»;
- ~240 строк документов, перенесённых со старого сайта (нормативная документация, вакансии,
  отчёты ректора, аттестация, МТЗ, супровід ООП, нормативка аспирантуры);
- страница `/university/structure/postgraduate` — отдел аспирантуры и докторантуры с вкладками;
- категории новостей «Аспірантура і докторантура» и «Оголошення», `/news/announcements`;
- статические страницы: `/university/language-exam`, тексты на `/university/inclusive`,
  `/university/vacancies`, `/university/attestation`.

## 0. Бэкапы

Те же две команды, что в шаге 0 части 1 (имя файла поменять, чтобы не затереть прошлый бэкап).

## 1. Стянуть код

```bash
git pull                       # knpu-university-be
cd ../knpu-university-fe && git pull && cd -
```

## 2. Посмотреть, что применится

```bash
docker compose -f docker-compose.prod.yml exec directus \
  npx directus schema apply --dry-run /directus/snapshots/schema.yaml
```

Ожидаемо в диффе:

- **новая коллекция `documents`** (поля `status`, `order`, `section`, `title`/`titleEn`,
  `description`/`descriptionEn`, `documentDate`, `file`, `externalUrl`);
- `Update documents.section` — добавился вариант `postgraduate-regulations`;
- `Update articles → Set preview_url to null` — **это ожидаемо**, `preview_url` возвращает
  шаг 4. Если в диффе есть что-то ещё — остановиться и разобраться.

## 3. Применить схему

```bash
docker compose -f docker-compose.prod.yml exec directus \
  npx directus schema apply /directus/snapshots/schema.yaml -y
```

## 4. Права, папки, роль редактора

Обязательно после **любого** `schema apply`: он стирает `preview_url` и не выдаёт права на новую
коллекцию. Без этого шага `documents` не видны анониму (пустые страницы) и не редактируются
редактором.

```bash
docker compose -f docker-compose.prod.yml exec directus \
  sh /directus/snapshots/bootstrap-public-access.sh

docker compose -f docker-compose.prod.yml exec \
  -e SITE_URL=https://<прод-домен> \
  -e PREVIEW_SECRET=<тот же секрет, что в NUXT_PREVIEW_SECRET> \
  -e PREVIEW_TOKEN=<тот же токен, что в NUXT_DIRECTUS_PREVIEW_TOKEN> \
  directus sh /directus/snapshots/bootstrap-editor-experience.sh

docker compose -f docker-compose.prod.yml exec directus \
  sh /directus/snapshots/bootstrap-editor-role.sh
```

Появится папка «Документи» (`3e5f21c7-…`) — в неё складывает файлы загрузчик из шага 5.

## 5. Документы со старого сайта

`documents.json` закоммичен, так что на проде хватит второй стадии. Токен — **статический**
админский: прогон длится дольше 15 минут, обычный логин-токен протухнет на середине.

```bash
cd migration/documents

# токен без попадания в историю (пробел в начале строки), либо через nano в файл
 export PROD_TOKEN='…'

docker run --rm --network webnet -v "$PWD":/work -w /work \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 -e DIRECTUS_TOKEN="$PROD_TOKEN" \
  python:3.12-slim python 2_load.py --dry-run

# то же без --dry-run: 248 строк, ~220 файлов, ~150 МБ, 10–20 минут
```

Идемпотентно: строки сверяются по `section` + `title`, файлы — по имени и размеру, так что
повторный запуск после обрыва продолжает с места остановки.

**14 файлов ожидаемо упадут с 404** — их нет и на старом сайте (у пяти в имени вшит неразрывный
пробел). Список — в `migration/documents/README.md`; их нужно будет донести руками, когда
университет пришлёт файлы. Всё остальное должно пройти: смотреть на `created=… failed=14`.

## 6. Картинки статических страниц

Три картинки (испит з держмови, две на страницах аспирантуры) лежат в контенте фронта по UUID,
как и картинки факультетов в части 1. Скрипт копирует их из локального Directus на прод,
сохраняя id.

Запускать **с машины разработчика** (нужен доступ к обоим Directus сразу):

```bash
cd migration/pages
SOURCE_URL=http://localhost:8055 SOURCE_EMAIL=… SOURCE_PASSWORD=… \
TARGET_URL=https://<прод-домен-cms> TARGET_TOKEN=$PROD_TOKEN \
python3 sync_images.py --dry-run \
  --path ../../../knpu-university-fe/app/content/pages \
  --path ../../../knpu-university-fe/app/content/structure/postgraduate
```

Ожидается `3 asset(s)`; затем то же без `--dry-run`. Без `--path` скрипт проверит все ~1800
картинок факультетов — это безопасно (уже загруженные пропускаются), просто дольше.

## 7. Категории новостей

Добавляет «Аспірантура і докторантура» и «Оголошення» и проставляет первую по ключевым словам
(локально совпало 13 статей). «Оголошення» намеренно остаётся пустой — её проставляют редакторы.

```bash
cd migration/structure-pages
DIRECTUS_URL=$PROD_URL DIRECTUS_TOKEN=$PROD_TOKEN python3 5_tag_news.py --dry-run
DIRECTUS_URL=$PROD_URL DIRECTUS_TOKEN=$PROD_TOKEN python3 5_tag_news.py
```

Идемпотентно, существующие 9 категорий факультетов не трогаются.

## 8. Фронт

Пересобрать и задеплоить `knpu-university-fe`. Окна даунтайма, в отличие от части 1, нет:
старый фронт не ломается от появления новой коллекции.

## 9. Проверка

```bash
# документы приходят анониму
curl "$PROD_URL/items/documents?fields=section,title&filter[section][_eq]=regulations&limit=3"

# страницы отвечают
for u in rector-report regulations regulation-drafts facilities vacancies attestation \
         language-exam inclusive public-info; do
  printf '%-20s ' "$u"
  curl -s -o /dev/null -w '%{http_code}\n' "https://<прод-домен>/university/$u"
done

curl -s -o /dev/null -w '%{http_code}\n' "https://<прод-домен>/university/structure/postgraduate"
curl -s -o /dev/null -w '%{http_code}\n' "https://<прод-домен>/news/announcements"
```

Глазами:

- `/university/regulations` — 172 документа, PDF скачивается с `/assets/`;
- `/university/regulation-drafts` — пусто и это правильно: страница под заполнение редактором;
- `/university/vacancies` — сверху текст (список вакансий, телефон отдела кадров), снизу 18 приказов;
- `/university/structure/postgraduate` — 8 вкладок, плитки «Розділи та сервіси», в шапке
  «Підрозділ», в карточке контактов «Керівництво» (не «Декан»);
- вкладка «Нормативні документи» — 29 строк, часть ссылками на zakon.rada.gov.ua;
- вкладка «Оголошення» — пусто, пока редакторы не проставят категорию;
- главная — блок «Корисні покликання»: шесть чипсов в одну строку, два внешних со стрелкой ↗,
  «For Abroad Enrollees» серый и некликабельный;
- зайти **редактором** и добавить документ в «Звіт ректора» — появляется на сайте без деплоя.

## Мелочи

- Прод-токен админа, который светился в переписке, **всё ещё не ротирован**.
- `articles_categories_legacy` из части 1 можно дропнуть, если всё подтвердилось.
- Два документа в разделе «Матеріально-технічне забезпечення» — ссылки на страницы факультетов
  на старом сайте (файлов там нет). Умрут вместе со старым доменом; заменить, когда факультеты
  пришлют свои документы.


---

# Часть 3: парламент, партнёри, центр якості, превью газети, чистка меню

Едет сразу после части 2, тем же деплоем фронта. **Схему не меняет вообще** — только данные,
переменные окружения и фронт.

Что приезжает:

- «Студентська рада» → «Студентський парламент»: разделы по структуре KNMU, пустые, плюс живая
  лента новостей и список документов;
- четыре партнёра из документа клиента (МОН, Департамент освіти ХОДА, Урядовий контактний центр,
  Сковорода-хаб); демо-партнёры SoftServe/EPAM убраны из сида;
- «Антикорупція» в меню ведёт на sites.google.com/view/khnpuanticorupcia; страница остаётся;
- `/education/quality` — пустой каркас с вкладками smc.hnpu.edu.ua;
- превью первой страницы PDF в архиве газеты (pdf.js);
- из меню «Студенту» убраны Moodle, АСУ НЗ / Е-відомості, Корпоративна пошта, Їдальні,
  Медичне обслуговування — вместе со страницами;
- `/student/dormitories` — текст со старого сайта вместо заглушки;
- картинки в теле статей и страниц подразделений ограничены по высоте и запрашиваются с
  `?width=1200`.

## 1. Переменные окружения Directus

`docker-compose.prod.yml` уже содержит новую строку:

```
CORS_EXPOSED_HEADERS: ${CORS_EXPOSED_HEADERS:-Content-Range,Accept-Ranges,Content-Length}
```

Без неё pdf.js не видит, что файл можно тянуть по частям, и качает выпуск целиком (5–7 МБ на
карточку). Применяется перезапуском контейнера:

```bash
docker compose -f docker-compose.prod.yml up -d directus
curl -sD - -o /dev/null -H "Origin: https://<прод-домен>" \
  "$PROD_URL/assets/<любой-uuid-pdf>" | grep -i access-control-expose
```

## 2. Партнёри и категория новостей парламента

```bash
# 4 партнёра (идемпотентный upsert по slug)
docker compose -f docker-compose.prod.yml exec -e SEED_CONTENT=true directus \
  sh /directus/snapshots/seed-content.sh

# категория «Студентський парламент»
cd migration/structure-pages
DIRECTUS_URL=$PROD_URL DIRECTUS_TOKEN=$PROD_TOKEN python3 5_tag_news.py
```

`seed-content.sh` трогает и другие демо-записи (галерея, події) — если на проде уже есть
настоящий контент в этих коллекциях, безопаснее завести четырёх партнёров руками в админке,
данные взять из блока «Upserting partners...» этого же скрипта.

Если демо-партнёры SoftServe и EPAM когда-то попали на прод — удалить их в админке, в сиде их
больше нет.

## 3. Гуртожитки

Страница берёт текст из `app/content/pages/dormitories.uk.json` (закоммичен), картинок в нём нет —
отдельных шагов не нужно.

## 4. Фронт

`pnpm install` обязателен: добавилась зависимость `pdfjs-dist` (~15 МБ, воркер и wasm едут в
бандл). Дальше обычная сборка и деплой.

## 5. Проверка

```bash
for u in /student/council /education/quality /university/partners /university/newspaper \
         /student/dormitories /university/prozorro; do
  printf '%-32s ' "$u"; curl -s -o /dev/null -w '%{http_code}\n' "https://<прод-домен>$u"
done

# удалённые страницы должны отдавать 404
for u in /student/moodle /student/grades /student/email /student/canteens /student/medical; do
  printf '%-24s ' "$u"; curl -s -o /dev/null -w '%{http_code}\n' "https://<прод-домен>$u"
done
```

Глазами:

- `/student/council` — заголовок «Студентський парламент», разделы пустые, лента новостей и
  список документов на месте; в меню «Студенту» пункт тоже переименован;
- `/university/partners` — четыре организации, у трёх активные ссылки;
- меню «Міжнародна діяльність» → «Антикорупція» открывает Google Site в новой вкладке;
- `/education/quality` — восемь вкладок, переключаются, адрес меняется на `?tab=…`;
- `/university/newspaper` — у карточек в зоне видимости появляется превью первой страницы;
  в Network только несколько запросов к `/assets/` со статусом 206, а не 97 полных PDF;
- `/university/structure/history-law` — логотип в тексте не больше ~350 px, карточка «Контакти»
  по высоте содержимого и прилипает при прокрутке.

**Превью газеты проверено только частично**: в моём встроенном браузере pdf.js доходит до разбора
документа (страницы читаются, запросы 206 идут), но canvas остаётся пустым — похоже на
ограничение самого превью-браузера. В обычном Chrome/Firefox это нужно посмотреть глазами; если
превью не появится и там, карточки просто останутся с прежней иконкой-заглушкой (фолбэк
отрабатывает через 6 секунд).


---

# Часть 4: деканати, фінанси, закупівлі, логотипи, чистка вигаданих даних

Идёт последней. Меняет схему (одна новая опция + дроп коллекции), переносит ~100 файлов и
**удаляет демо-строки в 15 коллекциях** — читать список до начала.

Что приезжает:

- деканаты факультетов рендерятся карточками, как `/university/rectorate` (данные вынесены в
  `app/content/structure/*/home.uk.json` скриптом `migration/structure-pages/6_extract_people.py`);
- превью первой страницы PDF в блоке газеты на главной;
- `/university/prozorro` — виджет prom.ua вместо выдуманных тендеров;
- `/university/financial-reports` — 99 документов со старого сайта вместо выдуманных миллионов;
- логотипы четырёх партнёров;
- выдуманные люди, цифры, рейтинги и Lorem убраны с ~30 страниц: подробности и список
  «что прислать» — в `knpu-university-fe/docs/mock-data-audit.md`.

## 1. Схема

```bash
docker compose -f docker-compose.prod.yml exec directus \
  npx directus schema apply --dry-run /directus/snapshots/schema.yaml
```

Ожидаемо: в choices поля `documents.section` добавляется `financial-activity`; **удаляется
коллекция `financial_reports`** (на локальной базе в ней было три демо-записи — на проде
проверить `curl "$PROD_URL/items/financial_reports?limit=-1"` до применения). Затем без
`--dry-run`, и следом обязательный `bootstrap-editor-experience.sh` — apply стирает `preview_url`.

## 2. Документы фінансової діяльності

```bash
cd migration/documents
docker run --rm --network webnet -v "$PWD":/work -w /work \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 -e DIRECTUS_TOKEN="$PROD_TOKEN" \
  python:3.12-slim python 2_load.py --only financial-activity --dry-run

# затем без --dry-run: 107 строк, ~99 файлов; 8 ожидаемо упадут с 404 — их нет и на старом сайте
```

## 3. Логотипы партнёров

```bash
cd migration/partners
docker run --rm --network webnet -v "$PWD":/work -w /work \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 -e DIRECTUS_TOKEN="$PROD_TOKEN" \
  python:3.12-slim python load_logos.py --dry-run   # затем без флага
```

`logos.map.json` закоммичен, id файлов совпадают с локальными — повторный запуск ничего не
дублирует.

## 4. Удаление демо-строк

Сид больше их не создаёт, но на проде они могли остаться с прошлых прогонов. **Сначала
посмотреть глазами**, не завёл ли университет там настоящие записи:

```bash
for c in gallery_items gallery_categories memorial_entries vacancies events programmes \
         student_schedule_documents education_schedule_periods education_schedule_key_dates \
         admission_open_days admission_exam_programs university_orders science_defenses \
         science_conferences prozorro_procurements; do
  printf '%-32s ' "$c"
  curl -s -H "Authorization: Bearer $PROD_TOKEN" "$PROD_URL/items/$c?aggregate[count]=*"
  echo
done
```

Признаки демо-строк: тендери `UA-2026-01-15-000001-a`, групи ПП-101 / ІТ-201, дисертанти
Іваненко/Петренко/Сидоренко, «Герой А»/«Герой Б», партнери SoftServe і EPAM, статті
`open-day-2026` и `student-research-grants`, факультет «інформаційних технологій» у програмах.
Удалять через админку или `DELETE /items/<collection>` списком id.

## 5. Фронт

Пересобрать и задеплоить. Новых переменных окружения нет.

## 6. Проверка

```bash
curl "$PROD_URL/items/documents?filter[section][_eq]=financial-activity&aggregate[count]=*"   # ~99
curl "$PROD_URL/items/partners?fields=slug,logo"                                             # 4 логотипа
```

Глазами:

- `/university/structure/history-law` (и preschool, special-education, social-humanities) —
  деканат карточками, фото одного размера, у кого фото нет — плашка с инициалом;
- главная — превью первых страниц у трёх выпусков газеты;
- `/university/prozorro` — виджет Prozorro грузится, выдуманных тендеров нет;
- `/university/financial-reports` — список документов с фильтром по годам;
- `/university/partners` — четыре логотипа;
- выборочно `/science/*`, `/student/*`, `/education/*` — вместо выдуманных фамилий и цифр
  «Розділ наповнюється».
