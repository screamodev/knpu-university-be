# Правки 16.10.2026, п. 3 — Факультет фізичного виховання і спорту

Документ «Правки 15.10.26 / 16.10.26», пункт 3 («ТЕРМІНОВО»): оновити вкладки сторінки
`/university/structure/physical-education`. Матеріали — лист «Fwd: Оновлення сторінки факультету
ФВіС» (faculty-sport@, 16.10 13:26, переслано на sitehnpu@): `Оновлення стор. факультету.docx` і
17 фото (`Фото1.jpg` … `Фото 17.jpg`).

| Що | Куди |
| --- | --- |
| розділ 1 «ІСТОРІЯ»: новий текст, Фото 1 на початку, Фото 2 після рядка «Декан» (текст замінює колишній) | `knpu-university-fe/app/content/structure/physical-education/history.uk.json` |
| розділ 2 «ОСВІТА → Створити нову вкладку СПОРТИВНІ СПОРУДИ»: текст + Фото 3–17 | нова вкладка `facilities` → `…/physical-education/facilities.uk.json` |
| 17 фото (JPEG ≤ 1600 px, `files/`) | медіатека (`push_assets.py`) |

Новий id вкладки `facilities` («Спортивні споруди» / «Sports facilities») додано у
`STRUCTURE_TAB_IDS` (одразу після `education`), в іконки плиток (`award`), локалі, `manifest.json`
факультету та `STRUCTURE_TABS` в `apply_schema.py` (щоб вкладку можна було вести в адмінці).
Рядків у `structure_pages` для `physical-education` на проді немає (перевірено API 16.10), тож
вкладки читає статичний JSON і фронт треба перезібрати.

## Як це влаштовано

* `data/history.html`, `data/facilities.html` — текст docx дослівно (жирне/курсив → `<strong>`/`<em>`,
  посилання на папку конференції → `<a>`, пункти → `<ul>`). `{{img:N|alt}}` — місце фото N.
* `build.py` стискає фото, пише `files.map.json` (uuid5 у просторі `…/migration/fixes-2026-10-16-fvis`)
  і збирає обидва JSON фронту. Команда збірки (Pillow через контейнер) — у докстрингу.
* Технічні правки: абзаци, злиті в docx табуляціями (історія 1925–1930 рр., кінець 50-х, 1962 р.),
  розбито на окремі `<p>`; подвійні пробіли стиснуто; рядки-вказівки («ВСТАВИТИ ФОТО N»,
  «Створити нову вкладку…», «Добрий день…», адреси сторінок) на сторінку не потрапили.
* Спортивні споруди: зали комплексу Пояркова й відкрите футбольне поле — вкладений список під
  «в спеціалізованих залах…», решта пунктів — того ж рівня; фото — сітки `photo-grid gallery`
  одразу після відповідного пункту.

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
DRUN schema/apply_schema.py                                  # варіант «Спортивні споруди» у structure_pages.tab
DRUN fixes-2026-10-16-fvis/push_assets.py --dry-run          # 17 у карті · 0 уже на цілі · 17 залити
DRUN fixes-2026-10-16-fvis/push_assets.py                    # в кінці: uploaded=17 failed=0
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Чого тут немає і чому

* **Підписів до фото** — у docx їх немає, свого не вигадували; `alt` — назви місць із тексту клієнта.
* **Вирівнювання списку** — крапки з комою в кінці пунктів лишено як у клієнта (в «зал гімнастики…»
  її немає, бо в docx вона стоїть після вказівки про фото, а не після тексту).
* **Повтор у «Історії»** — державна тема № 0119U100634 у переліку тем стоїть двічі (так у docx),
  лишено як є.
* **Відео/інші вкладки** — лист стосується лише «Історії» і «Освіти»; решту вкладок (Вступнику,
  Наука, Студентство, Співпраця) не чіпали.
