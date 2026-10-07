# Правки 07.10.2026 — нове загальне фото кафедри спеціальної педагогіки

П. 2 документа «Правки 07.10.26»: на Головній кафедри спеціальної педагогіки замінити
загальне фото викладачів. Клієнт надіслав файл «Фото кафедри спеціальної педагогіки (4).png»
(1920×1080).

| Що | Куди |
| --- | --- |
| `specped-staff-2026-10.jpg` (JPEG 1600×900 із надісланого PNG) | `home.uk.json`, секція «Головна», замість `/assets/9f929c75-71c7-487d-8456-35872fa1ef07` |

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-07-specped-photo/push_assets.py --dry-run   # 1 файл
DRUN fixes-2026-10-07-specped-photo/push_assets.py
```

## Що зроблено на фронті (без бандла)

`app/content/structure/kafedra-specialnoyi-pedagogiky/home.uk.json`: у першому `<img>` секції
«Головна» `/assets/9f929c75-…` замінено на `/assets/42a0e59b-a1cb-5201-b0b4-fda263a92fe0`.
Фронт треба перезібрати (`up -d --build`): вкладка читається зі статичного JSON.

## Чого тут немає і чому

* **Старе фото** (`9f929c75-71c7-487d-8456-35872fa1ef07`) з медіатеки не видаляється: на нього
  більше ніщо не посилається, але чистити прод без підтвердження не можна.
* **Шевченко Ю.В.** на новому фото немає, у сітці «Співробітники» її теж немає, тож більше
  нічого міняти не треба.
