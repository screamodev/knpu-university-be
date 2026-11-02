# Правки 02.11.2026 — покажчик Юр’євої і анкети ОП «Прикладна та книжкова графіка»

Документ «Правки 02-06.11.2026», два пункти без позначки «ВИКОНАНО».

| Пункт | Що | Куди |
| --- | --- | --- |
| Бібліографічні покажчики (лист Захарченко «Покажчик Юр'євої для розміщення на сайті») | `bibl-yuryeva-2026.pdf` — текст покажчика (`Yuryeva K. A.pdf`, 2,6 МБ); опис із `Опис покажчика для сайту.docx` дослівно (УДК 016:929](477), Ю 86, вип. 32) | `app/content/pages/science-bibliographic-indexes.uk.json` — одразу після покажчика Штефан; `science-notable-scientists.uk.json` — останнім у списку, після Штефан |
| Якість освіти (`/education/quality?tab=quality`), docx «Опис_якість_БАК_ОП_Прикладна_та_книжкова_графіка» | 3 PDF результатів анкетування 2026 р., ОП «Прикладна та книжкова графіка» | `app/content/pages/quality-centre-quality.uk.json`, «Результати анкетування» → «Мистецтв» |

Місця анкет — за скриншотами в docx:

| Файл | Куди |
| --- | --- |
| `anketa-prykladna-knyzhkova-osvitnii-protses-2026.pdf` (`…otsiniuvannia_osvitnoho_protsesu_26`) | у першому списку, після «…Музичне мистецтво в закладах освіти» 2025 н.р., перед Образотворче мистецтво 2022 |
| `anketa-4-prykladna-knyzhkova-robotodavtsi-2026.pdf` (анкета № 4) | у списку анкет № 4, після «№ 4 ОП Образотворче мистецтво в закладах освіти … 2026 рік» |
| `anketa-5-prykladna-knyzhkova-pislia-praktyky-2026.pdf` (анкета № 5) | у списку анкет № 5, у кінець — після «№5 ОП Музичне мистецтво в закладах освіти … 2025 рік» |

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-11-02-quality-bibl/push_assets.py --dry-run   # 4 файли
DRUN fixes-2026-11-02-quality-bibl/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

PDF лежать у `files/` (надіслано поштою й месенджером, тож у git); uuid файлів — uuid5 від імені,
тож `/assets/<uuid>` у текстах збігається на локалі й на проді.

## Чого тут немає і чому

* **Закривна «»» у пункті анкети № 5.** У docx перед «2026 рік» немає закривної лапки
  («…(після проходження практики) 2026 рік»), у сусідніх пунктах вона є — додано, інакше текст
  не змінено.
* **Ім'я PDF анкети № 4.** У docx вказано `…robotodavtsiamy_26`, а надісланий файл —
  `…robotodavtsiamy.pdf` (без `_26`); це той самий пункт, файл узято надісланий.
* **Опис покажчика Юр’євої** — ПІБ написано з апострофом U+2019 («Юр’єва»), як у docx і на сторінках
  кафедр; у листі й документі правок апостроф прямий.
* Англійських версій цих сторінок немає.
