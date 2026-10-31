# Правки 31.10.2026 — кафедра музичного мистецтва: новий банер

П. «Кафедра музичного мистецтва» документа «Правки 26-30.10.26»: замінити банер кафедри на новий.
Матеріал — лист Миколи Данилюка від 31.10 (тема «НОВИНИ | Каф. муз. мист. | Конференція "Час-2026" +
банер»), вкладення `baner_kmm_hnpu.png`.

| Що | Куди |
| --- | --- |
| `baner-kmm-2026-10.png` (PNG 1640×624, як надіслано) | `app/content/structure/kafedra-muzychnogo-mystectva/{home,education,science,history}.uk.json`, перша картинка вкладки, замість `/assets/17e7fdd6-58e3-4f2e-880e-fdfa2b17551a` |

Новий uuid — `f37847a5-819f-5126-a08b-396343fdb21f`. Ширина банера — як і раніше, на всю текстову
колонку.

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-31-kafedra-muzychnogo/push_assets.py --dry-run   # 1 файл
DRUN fixes-2026-10-31-kafedra-muzychnogo/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Що зроблено на фронті (без бандла)

У чотирьох вкладках кафедри (Головна, Історія кафедри, Освітня діяльність, Наукова діяльність —
статичний JSON, у Directus `structure_pages` для цієї кафедри рядків немає) `/assets/17e7fdd6-…`
замінено на новий uuid. Інший текст не чіпали.

## Чого тут немає і чому

* У тому ж листі є новина про конференцію «Час-2026» (docx + три фото) і два питання клієнта (у
  якому форматі подавати фото в новинах; чи можна прив'язати старі загальні новини до розділу
  «Новини» кафедри). У документі правок цього пункту немає, тому не робилося.
* Старий ассет `17e7fdd6-…` з медіатеки не видаляється: чистити прод без підтвердження не можна.
* `*.en.json` для цих вкладок немає, англійської версії не торкалися.
