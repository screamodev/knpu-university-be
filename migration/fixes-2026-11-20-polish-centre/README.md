# Правки 20.11.2026 — ННІ української філології, Регіональний центр польської мови

П. «Навчально-науковий інститут української філології» документа «Правки 16-20.11.2026»: на
сторінці «Структура» (внизу) рубрика «Регіональний центр польської мови, культури і науки»
неактивна — зробити активною й розмістити інформацію та фото. Лист — Піддубної Вікторії від
20.11 10:32 (тема «кафедра українознавства і лінгводидактики»). Вкладення:
`11_11_2026_1.jpg`, `11_11_2026_2.jpg`, `День_Незалежності_2026.docx` (маркери фото в тексті —
`[11_11_2026_1]`, `[11_11_2026_2]`).

| Що | Куди |
| --- | --- |
| `polish-centre-independence-day-2026-11-11-1.jpg` (`11_11_2026_1.jpg`, 1600×900, без змін) | `app/content/structure/polish-centre/home.uk.json`, на місці `[11_11_2026_1]` |
| `polish-centre-independence-day-2026-11-11-2.jpg` (`11_11_2026_2.jpg`, 1920×1080 → 1600×900 через sharp) | там само, на місці `[11_11_2026_2]` |

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-11-20-polish-centre/push_assets.py --dry-run   # 2 файли
DRUN fixes-2026-11-20-polish-centre/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Що зроблено на фронті (без бандла)

* `app/utils/structure.ts`: центр отримав власну сторінку `/university/structure/polish-centre`
  (запис у `STRUCTURE_DEPARTMENTS`, як у лабораторії); у `associations` інституту з'явився `path`,
  тож на вкладці «Структура» назва — посилання.
* `app/content/structure/manifest.json`: запис `polish-centre` — лише вкладка «Головна»
  (`tabNav: []`, `hideAnnouncements`, `hideNews`).
* `app/content/structure/polish-centre/home.uk.json`: текст із docx дослівно, фото на місцях
  маркерів. Підпис «Директорка Центру Яна Василенко…» з docx на прохання розробника прибрано. Заголовка секції в docx немає — не вигадували.

## Чого тут немає і чому

* **Англійська версія**: тексту немає, сторінка лише українською.
* **Меню «Наука»** (`scienceUnits.ts` веде на старий сайт) і **хаб `/university/structure`** —
  не чіпали, про це не просили.
* **Directus `structure_pages`**: рядків для цього підрозділу немає, контент береться з JSON.
