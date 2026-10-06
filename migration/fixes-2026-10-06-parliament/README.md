# Правки 06.10.2026 — Студентський Парламент

Лист «Оновлена інформація Студентський Парламент» (studparliamenthnpu@hnpu.edu.ua →
sitehnpu@hnpu.edu.ua, 06.10 о 19:10), сторінка `/student/council`. Просять:

1. замінити логотип на актуальний;
2. замінити два файли з інформацією про голів факультетів;
3. додати на сторінку окремі розділи «Контактні дані» та «Керівництво».

## Що куди їде

| Що | Куди |
| --- | --- |
| новий логотип `IMG_7384.png` (PNG як є, 78 КБ, прозорість збережена) | `student_council_info.emblem` (`patch_council.py`) |
| `Контакти_студентського_самоврядування.pdf` | `documents` «Контакти студентського самоврядування» (`1a5cdd86…`), поле `file` |
| `Голови факультетів.pdf` | `documents` «Голови факультетів» (`2bfb3861…`), поле `file` |
| 12 людей з тіла листа: голова, заступник, 10 голів студрад факультетів | `student_council_members` (`data/members.json`) |
| поля `phone`, `instagram`, `telegram` у `student_council_members` | схема (`apply_schema.py`) |
| картки з контактами, посилання `tel:`/`mailto:`/Instagram/Telegram | фронт, `knpu-university-fe` |

Розділ «Контактні дані» (адреса, пошта, Facebook, Instagram) на проді вже заповнений
і збігається з листом, тож його не чіпаю. Розділ «Керівництво» був порожній — тепер
наповнюється з `student_council_members`.

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
DRUN schema/apply_schema.py                                  # + phone, instagram, telegram
DRUN fixes-2026-10-06-parliament/push_assets.py --dry-run    # 3 файли
DRUN fixes-2026-10-06-parliament/push_assets.py
DRUN pass2/load.py fixes-2026-10-06-parliament/data/members.json
DRUN fixes-2026-10-06-parliament/patch_council.py --dry-run
DRUN fixes-2026-10-06-parliament/patch_council.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

Нова колекція не створюється, права міняти не треба (`student_council_members` уже
читається публічно). Усі скрипти ідемпотентні: `load.py` пропускає наявних людей,
`patch_council.py` — вже замінені файли. Файли лежать у `files/` в git, uuid детерміновані
(uuid5 від імені файла, див. `bundle.py`).

## Чого тут немає і чому

* **Посади «Голова» і «Зам» з листа** не винесені в картку: блоки сторінки й так підписані
  «Голова» та «Заступники голови», а скорочення «Зам» у картці виглядало б помилкою.
* **Виправлення в тексті** — лише очевидні технічні, посади голів факультетів зліплені з
  переносів рядків листа: «технологи» → «технологій» (як у PDF), «Фізичного» → «фізичного»,
  «математики інформатики» → «математики, інформатики», «Голова» → «голова» у Табах С.
  Прізвища, телефони, нікнейми, пошти — як у листі.
* **Склад виконкому** (секретар, голови комітетів; у PDF нумерація йде 1, 2, 4…22 — номера 3
  немає) є лише в PDF «Контакти
  студентського самоврядування». На сторінку окремим блоком не виношу: клієнт про це не
  просив, PDF стоїть у розділі «Документи».
* **Фото людей** у листі немає — картки з літерою, як і раніше.

## Питання до клієнта: розбіжності листа й PDF

Дані на сторінку взяті з тіла листа. Де PDF каже інше:

* **Чижик Софія Олексіївна** — у листі «Голова», пошта `sofia.chizhik@hnpu.edu.ua`; у PDF
  «в.о. Голови Студентського Парламенту», пошта `sofklimova1207@gmail.com`.
* **Гусак Ольга Віталіївна** — у листі пошта `o.gusak@hnpu.edu.ua`; у PDF
  `olia.yalo1501@gmail.com`.
* **Коваленко Дарина Сергіївна** — у листі пошта `ffbdnbkfbkb@gmail.com`, схожа на набір
  літер; у PDF така сама. Можливо, помилка при введенні.
* Посилання на Instagram у листі містить службовий параметр `?stkn=…`; на сайті лишено
  чисте `https://www.instagram.com/parliament_khnpu`, яке там уже стоїть.
