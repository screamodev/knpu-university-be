# Правки 06.10.2026 — фото голів студентських рад факультетів

Продовження `fixes-2026-10-06-parliament`: у PDF «Голови факультетів» з того ж листа
Студентського Парламенту на кожному слайді є портрети. Їх вирізано й додано до карток
блоку «Голови студентських рад факультетів» на `/student/council`.

## Що куди їде

| Що | Куди |
| --- | --- |
| 10 портретів (JPEG, 500–600 px по ширині) | медіатека (`push_assets.py`) |
| поле `photo` у 10 записах `student_council_members` (група `faculty-chair`) | `patch_photos.py` |

Фронт не міняється: картка вже вміє показувати `photo`.

## Як це зроблено

Кожен слайд PDF має до трьох фото в рамці одного розміру. На слайді воно обрізане рамкою,
а в файлі лежить ширше. Тому вирізано саме видиму частину з оригінального зображення, без
повторного стискання сторінки; білих полів по краях немає. Хто є хто, визначено за підписом
під кожним фото (зліва направо), по обличчях нічого не зіставлялося.

## Як накотити

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-06-parliament-photos/push_assets.py --dry-run   # 10 файлів
DRUN fixes-2026-10-06-parliament-photos/push_assets.py
DRUN fixes-2026-10-06-parliament-photos/patch_photos.py --dry-run
DRUN fixes-2026-10-06-parliament-photos/patch_photos.py
```

Фронт перезбирати не треба: сторінка читає дані з Directus на кожен запит. Скрипти
ідемпотентні.

## Чого тут немає і чому

* **Фото голови (Чижик С.) і заступника (Лісовий В.)** — у листі їх немає: у PDF «Контакти
  студентського самоврядування» лише таблиця, у «Голови факультетів» лише 10 голів
  студрад. Картки лишаються з літерою; фото можна додати в адмінці прямо в запис.
* **Кадрування в картці.** Фото майже квадратні, а картка має пропорцію 4:5
  (`object-cover object-top`), тож по боках зрізається близько п'ятої частини.
