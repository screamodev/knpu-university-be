# Правки 29.10.2026 — відділ аспірантури і докторантури

П. «Відділ аспірантури і докторантури» документа «Правки 26-29.10.26»
(`/university/structure/postgraduate`):

1. Плитку «Протидія дискримінації, булінгу» лишити, але посилання поки відкріпити (вело на
   `/university/inclusive`).
2. На вкладці «Аспіранту» (`/university/structure/postgraduate/students`) під «Документацією
   аспірантів» додати вкладку «Про підготовку до захисту дисертації» з посиланням
   `https://drive.google.com/file/d/1Xj3q9RUB31RbGkBTPO1LS8EzUx5KUvlo/view?usp=sharing`.
3. У «Розділи та сервіси»: «Соціально-психологічний супровід, консультування» → «Психологічна
   служба», «Публічна інформація» прибрати, решту розставити за абеткою.

## Що куди їде

| Що | Куди |
| --- | --- |
| п. 1 і 3 — плитки | фронт, `app/content/structure/postgraduate/home.uk.json` (`links`), бандл не потрібен |
| п. 1 — некликабельна плитка | фронт, `StructureUnitTiles.vue`: посилання без `url`/`path` рендериться як `disabled` |
| п. 2 — новий блок | рядок `structure_pages` (`postgraduate`/`students`) у Directus — `patch_students.py`; у фронті ще й фолбек `students.uk.json` |

Текст посилання в п. 2 — назва PDF на Drive («Підготовка дисертацій до захисту: правила,
процедури, відповідальність»); в назві файлу описка «дисетацій» виправлена. Вкладка зроблена
згортним блоком, як «Документація аспірантів».

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
DRUN fixes-2026-10-29-postgraduate/patch_students.py --dry-run   # « ~ postgraduate/students »
DRUN fixes-2026-10-29-postgraduate/patch_students.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

Схема й права не міняються. Повторний запуск патча пише «уже виправлено» й нічого не змінює.

## Чого тут немає і чому

* **Куди має вести «Протидія дискримінації, булінгу».** Клієнт просить лише відкріпити
  посилання («пока»); нової адреси немає — плитка лишається без посилання.
* **Англійська версія.** `students.en.json` / `home.en.json` для відділу немає, плитки й вкладка
  лише українською.
