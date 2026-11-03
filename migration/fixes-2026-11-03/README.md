# Правки 03.11.2026

Документ «Правки 02-06.11.2026», вкладка «Правки 03.11.26». Матеріали — лист Н. О. Пономарьової
«Оновлення сторінки Lecture» (03.11, 11 вкладень: 6 docx + PL.png, PL1–PL3.jpg, news.png).

| Пункт | Що | Куди (FE) |
| --- | --- | --- |
| Лабораторія з методики викладання філологічних дисциплін | заголовок «Звіт про роботу лабораторій у 2025 р.» → «Звіт роботи лабораторії у 2025 році» | `app/content/structure/philology-teaching-lab/home.uk.json` |
| LECTURE, головна | `mainLecture` дослівно; зверху PL1, PL2, PL3 (ЄС, лого проєкту, герб ХНПУ) | `app/content/pages/erasmus-lecture.uk.json` |
| LECTURE, «Партнери проєкту» | `partnerLecture`; зверху по центру PL | `erasmus-lecture-partners.uk.json` |
| LECTURE, «Документація проєкту» | `docLecture` | `erasmus-lecture-documents.uk.json` |
| LECTURE, «Робоча група» | `teamLecture` | `erasmus-lecture-team.uk.json` |
| LECTURE, «Контакти» | `contactLecture`; жовтий фрагмент (ПІБ координатора) — посилання на sites.google.com/hnpu.edu.ua/ponomarova/ | `erasmus-lecture-contacts.uk.json` |
| LECTURE, «Новини проєкту» | `newsrLecture`; по центру news, під нею посилання на Facebook | `erasmus-lecture-news.uk.json` |

Сторінки — окремі маршрути `/university/erasmus/lecture[/partners|documents|team|contacts|news]`
з рядком вкладок (`app/components/shared/ErasmusLectureShell.vue`, `app/utils/lectureTabs.ts`).

Файли — п'ять зображень у `files/` (оригінали з листа, усі ≤1600 px), `files.map.json` — карта uuid5.

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-11-03/push_assets.py --dry-run && DRUN fixes-2026-11-03/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Чого тут немає і чому

- Розміщення Erasmus+ у меню («Сторінка проєкту Lecture», ланцюжок 03.11) — не пункт документа;
  клієнтка пише, що коригувати буде Ярмак Т. Л. Меню не чіпали.
- Лист говорить «Вкладені три сторінки», але перелічує п'ять (партнери, документація, робоча
  група, контакти, новини) і п'ять описів — зроблено п'ять.

## Місця, де текст не дослівний або викликає питання

- Головна: e-mail координаторки в docx — `ponomna@gmal.com`; виправлено на `ponomna@gmail.com`
  (як у «Контактах»).
- «Документація»: у docx стоять підказки «(посилання на файл …)». Назви документів зроблено
  посиланнями на ці адреси Drive, самі підказки на сторінку не потрапили.
- Залишено як у клієнтки: «в. Алчевських, 29» (імовірно «вул.»), «інженера кафедри інформатики»,
  «Тернопільський академічний ліцей «Генеза» … Бердянськ», «Уманська гімназія Уманська гімназія»,
  непарна лапка в «EDEN DIGITAL LEARNING EUROPE MITTETULUNDUSUHING».
