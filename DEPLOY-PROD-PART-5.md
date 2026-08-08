# Прод-деплой, частина 5

Кафедри, центр забезпечення якості освіти (з дампа), студентське самоврядування, накази,
дерево категорій новин — плюс роботи колеги: пошук по сайту, редиректи зі старого домену,
разові вчені ради, розширення Directus, стиснення фото/HEIC.

Виконувати **після** частин 2–4 із `DEPLOY-PROD.md`. Перед стартом звірити, що на проді вже є
`documents`, категорії факультетів і сторінки факультетів — інакше половина кроків нижче впаде.

Команди — з `knpu-university-be` на сервері, якщо не сказано інше.
`DIRECTUS_URL=https://hnpu-admin.dev42hub.uk`, `DIRECTUS_TOKEN` — статичний токен адміністратора
(логін-токен живе 15 хв, цього мало).

---

## 0. Бекап

```bash
docker run --rm --network dbnet -e PGPASSWORD="$DB_PASSWORD" -v "$PWD":/backup postgres:16-alpine \
  pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_DATABASE" -Fc -f /backup/knpu-before-part5.dump
docker run --rm -v knpu-university-be_uploads:/uploads -v "$PWD":/backup alpine \
  tar czf /backup/knpu-uploads-before-part5.tar.gz -C /uploads .
```

## 1. Код

```bash
cd knpu-university-be && git pull
cd ../knpu-university-fe && git pull
```

Роботи колеги (пошук, редиректи, розширення, HEIC) мають бути **закомічені й запушені** — без цього
кроки 3 і 7 не мають сенсу.

## 2. Схема

```bash
cd knpu-university-be/migration/schema
docker run --rm --network host -v "$PWD":/w -w /w python:3.12-slim python apply_schema.py --dry-run
docker run --rm --network host -v "$PWD":/w -w /w python:3.12-slim python apply_schema.py
```

Створює колекції кафедр/центру/самоврядування, розділи `documents`, поле `parent` у категоріях.

## 3. Розширення Directus (від колеги)

Скопіювати `extensions/auto-fill-text`, `extensions/cover-hero-focal`, `extensions/text-with-tooltip`
на сервер (прод бере `./extensions` бінд-маунтом), потім:

```bash
docker compose -f docker-compose.prod.yml restart directus
```

## 4. Права та ролі

```bash
docker compose -f docker-compose.prod.yml exec directus sh /directus/snapshots/bootstrap-public-access.sh
```

Додає публічне читання новим колекціям, зокрема `legacy_redirects` — без нього редиректи зі старого
домену не працюють.

## 5. Дані

Усі скрипти ідемпотентні; `files.map.json` для прода тримати окремо від локального.

```bash
cd ../pass2
export DIRECTUS_URL=https://hnpu-admin.dev42hub.uk DIRECTUS_TOKEN=…

python3 seed_unit_categories.py            # 27 категорій кафедр під факультетськими
python3 load.py data/orders.json           # 127 наказів
python3 load.py data/documents.json        # решта документів пасу 2, якщо ще не залиті

cd ../smc
python3 2_load_news.py                     # 138 новин центру якості
# сторінки центру вже у фронтенді (app/content/pages) — окремо вантажити не треба

cd ../pass2
python3 mirror_page_files.py --content ../../../knpu-university-fe/app/content/pages \
  --unlink-host smc.hnpu.edu.ua --unlink-missing      # ~2 200 файлів, довго
python3 mirror_page_files.py --content ../../../knpu-university-fe/app/content/structure
```

Файли кафедр і сторінок уже мають `/assets/<uuid>` з локального прогону — ті самі ідентифікатори,
тож повторне дзеркалення просто добере те, чого на проді бракує.

Разові вчені ради (від колеги) — за `migration/razovi-rady/README.md`.

## 6. Чистка демо-даних

```bash
cd ../pass2
python3 cleanup_seed_demo.py --seed-orders --seed-files --legacy-links        # спершу список
python3 cleanup_seed_demo.py --seed-orders --seed-files --legacy-links --yes  # після перегляду
```

Саме через ці демо-файли «Накази» показували порожні PDF. Видалення незворотне — читати список.

## 7. Фронтенд

```bash
cd ../../../knpu-university-fe
docker compose -f docker-compose.prod.yml build app     # білд збирає й індекс пошуку
docker compose -f docker-compose.prod.yml up -d app
```

## 8. Перевірка

- `/university/structure/kafedra-informatyky` — вкладки, завідувач, співробітники, новини.
- `/education/quality` — вкладки «Новини» й «Документи» не порожні.
- `/university/orders` — відкрити 2–3 накази (мають відкриватися).
- `/student/council`, `/university/licenses`, `/education/monitoring`, `/education/students`,
  `/university/facilities`, `/university/contacts`, `/feedback` — сторінки на місці.
- Пошук у шапці; стара адреса виду `hnpu.edu.ua/uk/...` віддає 301 на нову сторінку.

## Відкат

Розгорнути дамп із кроку 0 і `docker compose -f docker-compose.prod.yml up -d`; том `uploads`
відновлювати лише якщо щось видалили помилково — нові файли самі по собі нічого не ламають.
