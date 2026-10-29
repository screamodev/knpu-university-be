# Правки 29.10.2026 — факультет історії і права, «Виховна діяльність»

П. «Факультет історії і права» документа «Правки 26-29.10.26»: додати банер, а також оголошення
на вкладку «Виховна діяльність» (`/university/structure/history-law/students`). Матеріали — два
листи Владіслава Вороніна від 29.10: «прошу викласти банер на сторінку» (фото
`photo_5406705781299683449_y.jpg`) і «Прошу додати ще одне оголошення на сторінку» (фото
`photo_5404548578140693402_y.jpg` і `news_3_1.docx`).

| Що | Куди |
| --- | --- |
| `history-law-debut-pershokursnyka-banner-2026-10.jpg` (JPEG 904×1280, афіша «Дебют першокурсника», 29.10, 14:30, QR-код; без стиснення) | `app/content/structure/history-law/students.uk.json`, одразу після списку планів і звітів, перед оголошенням |
| `history-law-bran-castle-virtual-tour-2026-10.jpg` (JPEG 1024×1280, афіша «Bran Castle — Virtual Student Tour», 29.10.2026, 16:00; без стиснення) | там само, у блоці оголошення |

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-29-history-law/push_assets.py --dry-run   # 2 файли
DRUN fixes-2026-10-29-history-law/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Що зроблено на фронті (без бандла)

`app/content/structure/history-law/students.uk.json` (вкладка читається зі статичного JSON — у
Directus `structure_pages` для факультету рядків немає):

* **Банер** — картинка одразу під списком планів і звітів (за уточненням клієнта: після документів); ширина обмежена 420 px (`max-width` у `style`),
  бо за замовчуванням висота зображень у тілі сторінки обмежена 22rem і QR-код був би дрібний.
* **Оголошення** — новий блок після банера, перед уроком «Козацька слава» (так само, як
  раніше додавали свіжі блоки): текст із `news_3_1.docx` дослівно, посилання на Zoom зроблено
  активним, нижче афіша «Замок Бран». Заголовка в docx немає, свого не вигадували.

## Чого тут немає і чому

* **Куди веде QR-код на банері.** У листі лише картинка, адреси в тексті немає, тож посиланням
  банер не обплетено.
* **Новини 28.10.** У тих самих скриньках є ще два листи Вороніна («Вітаю, прошу додати новину
  на сторонку» 12:41 і «Прошу додати ще одну новину на сторінку» 12:44, фото `News_28_10_*`) для
  `history-law/news` — у документі правок їх немає, не чіпали.
* **Англійська версія**: `students.en.json` для факультету немає, текст лише українською.
