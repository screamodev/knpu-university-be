# Правки 21.10.2026, п. 3 — нове фото кафедри психологічної і педагогічної антропології

П. 3 документа «Правки 19–21.10.26»: на Головній кафедри психологічної і педагогічної
антропології оновити фото. Клієнт надіслав файл «Кафедра психологічної та педагогічної
антропології.png» (1748×1240, колаж із сімох викладачів із підписами).

| Що | Куди |
| --- | --- |
| `antropology-staff-2026-10.jpg` (JPEG 1600×1135 із надісланого PNG) | `home.uk.json`, секція «Головна», замість `/assets/ffea1535-7a71-4dac-87d1-c75e42d9e23c` |

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-21-antropology-photo/push_assets.py --dry-run   # 1 файл
DRUN fixes-2026-10-21-antropology-photo/push_assets.py
```

## Що зроблено на фронті (без бандла)

`app/content/structure/kafedra-psyhologichnoyi-i-pedagogichnoyi-antropologiyi/home.uk.json`: у
першому `<img>` секції «Головна» `/assets/ffea1535-…` замінено на
`/assets/7b1ac0e8-2a25-54ac-a9d0-c4cd5698abf3`. Фронт треба перезібрати (`up -d --build`):
вкладка читається зі статичного JSON (у Directus `structure_pages` рядка немає).

## Чого тут немає і чому

* **Старе фото** (`ffea1535-7a71-4dac-87d1-c75e42d9e23c`, IMG-1459.JPG) з медіатеки не
  видаляється: на нього більше ніщо не посилається, але чистити прод без підтвердження не можна.
