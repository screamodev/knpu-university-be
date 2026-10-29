# Правки 29.10.2026 — ННІ української філології, лабораторія

П. «Навчально-науковий інститут української філології» документа «Правки 26-29.10.26» («Внести
зміни згідно з описом у листі на пошті»). Лист — Піддубної Вікторії від 29.10 (тема «внесення
змін»): зробити активною рубрику «Науково-практична лабораторія з методики викладання
філологічних дисциплін у закладах освіти» внизу вкладки «Структура» інституту й розмістити там
перший матеріал і фото (місце для фото в тексті — `[18_11_2025]`). Вкладення: «18_11_2025.jpg»,
«Науково-практичний семінар_ХНПУ_2025 (2).docx».

| Що | Куди |
| --- | --- |
| `philology-lab-seminar-2025-11-18.jpg` (JPEG 1048×681 із надісланого `18_11_2025.jpg`, без стиснення) | `app/content/structure/philology-teaching-lab/home.uk.json`, на місці маркера `[18_11_2025]` |

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-29-philology-lab/push_assets.py --dry-run   # 1 файл
DRUN fixes-2026-10-29-philology-lab/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Що зроблено на фронті (без бандла)

* `app/utils/structure.ts`: лабораторія отримала власну сторінку
  `/university/structure/philology-teaching-lab` (запис у `STRUCTURE_DEPARTMENTS`, як у Центру
  ментального здоров'я); у пункті `associations` інституту з'явився `path` — на вкладці
  «Структура» назва тепер посилання.
* `app/content/structure/manifest.json`: запис `philology-teaching-lab` — лише вкладка «Головна»
  (`tabNav: []`, `hideAnnouncements`), порожніх «Новин» немає.
* `app/content/structure/philology-teaching-lab/home.uk.json`: перший матеріал — науково-практичний
  семінар 18.11.2025. Текст із docx дослівно; фото на місці `[18_11_2025]`; «ПРОГРАМА СЕМІНАРУ»
  і «ЗБІРНИК» — посилання на Drive. У Directus `structure_pages` для цього підрозділу рядків немає.

## Чого тут немає і чому

* **Посилання «ЗБІРНИК».** У docx воно розірване: гіперпосилання закінчується на `…/view?usp=`,
  а `sharing` стоїть поза ним. Складено повну адресу `…/view?usp=sharing` (така сама, як у
  «ПРОГРАМА СЕМІНАРУ»). Обидва файли Drive відкриваються без входу (HTTP 200).
* **Англійська версія**: тексту немає, сторінка лише українською (англійська локаль дає
  українську, назва лабораторії англійською є).
* **Хаб `/university/structure`**: лабораторії там не було й раніше (вона лише в списку
  інституту), не чіпали — про це не просили.
* **Меню «Наука»**: лабораторію не додавали, бо про це не просили.
* **Наступні матеріали**: додаватимуться окремими секціями `home.uk.json` — клієнт про них
  написав «перший матеріал».
