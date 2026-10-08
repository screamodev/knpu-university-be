# Правки 08.10.2026 — нові PDF програм моніторингових досліджень

П. 1 документа «Правки 08.10.26»: Навчально-методичний центр забезпечення якості освіти,
`/education/quality?tab=quality`, вкладка «Якість освіти», розділ «Анкети» →
«Програми моніторингових досліджень в ХНПУ імені Г.С. Сковороди» — замінити вкладені файли.
Клієнт надіслав 6 PDF (скани, без текстового шару); відповідність визначена за полем «Тема»
на першій сторінці кожного.

| Файл у `files/` | Посилання на сторінці | Замість |
| --- | --- | --- |
| `monitoring-bakalavr-op.pdf` | …першого (бакалаврського) рівня вищої освіти | `0403f160-…` |
| `monitoring-mahistr-op.pdf` | …другого (магістерського) рівня вищої освіти | `03e49689-…` |
| `monitoring-pislia-dystsypliny.pdf` | Опитування… якості викладання (після вивчення дисципліни) | `33b84535-…` |
| `monitoring-robotodavtsi.pdf` | Оцінювання співпраці з роботодавцями | `d9ebcc5c-…` |
| `monitoring-bakalavr-praktyka.pdf` | …бакалаврського… (після проходження практики) | `252965cc-…` |
| `monitoring-mahistr-praktyka.pdf` | …магістерського… (після проходження практики) | `72bea3f6-…` |

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-08-monitoring/push_assets.py --dry-run   # 6 файлів
DRUN fixes-2026-10-08-monitoring/push_assets.py
```

## Що зроблено на фронті (без бандла)

`app/content/pages/quality-centre-quality.uk.json`: у секції «Програми моніторингових
досліджень…» шість `href="/assets/<старий>"` замінено на нові uuid (uuid5 від імені файла).
Тексти посилань не мінялися. Вкладка читається зі статичного JSON (рядка `static_pages` зі slug
`quality-centre-quality` немає), тож фронт треба перезібрати (`up -d --build`).

## Чого тут немає і чому

* **Старі 6 файлів** з медіатеки не видаляються: на них більше ніщо не посилається, але чистити
  прод без підтвердження не можна.
