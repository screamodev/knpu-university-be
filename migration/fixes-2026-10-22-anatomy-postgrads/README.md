# Правки 22.10.2026 — кафедра анатомії: «Наукова діяльність» → «Аспірантура»

Пункт документа «Правки 22.10.26»: у вкладці «Наукова діяльність», блок «Аспірантура», список
«Аспіранти кафедри» — видалити Кривко Алевтину Ігорівну і Голєву Ганну Юріївну, додати
Мінєєва Макарія Максимовича і Шелеханя Артема Анатолійовича. Матеріали — лист В. П. Коца
від 21.10 о 22:01 (по `.jpg` і `.docx` на кожного).

Як і в решти аспірантів, на сторінці — ПІБ-посилання; за посиланням відкривається PDF-картка:
фото ліворуч, текст із `.docx` праворуч (дослівно).

| Що | Куди |
| --- | --- |
| `anatomy-postgrad-mineiev.pdf` | `/assets/7d47eabb-c973-5fea-82d1-62fb7528d639` — посилання на ПІБ Мінєєва |
| `anatomy-postgrad-shelekhan.pdf` | `/assets/f67b6075-7088-56a6-9114-e1316fade585` — посилання на ПІБ Шелеханя |

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-10-22-anatomy-postgrads/push_assets.py --dry-run   # 2 файли
DRUN fixes-2026-10-22-anatomy-postgrads/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Що зроблено на фронті (без бандла)

`app/content/structure/kafedra-anatomiyi-i-fiziologiyi-lyudyny/science.uk.json`, секція 0,
`<details>` «Аспірантура»: видалено два `<p>` (Кривко, Голєва); після Возного додано два
`<p><a href="/assets/<uuid PDF>">ПІБ</a></p>`.

Вкладка читається зі статичного JSON (у Directus `structure_pages` для цієї кафедри рядка
немає — перевірено на проді й локалі), тому фронт треба перезібрати (`up -d --build`).

## Як зібрано PDF

`build_pdfs.py` (reportlab, шрифт DejaVu Serif; команда запуску — в докстрингу): A4
альбомна, фото ліворуч (з оригінальних `*.jpg`, що лежать у `files/` лише як джерело і на
прод не заливаються), праворуч — ПІБ жирним і рядки з `.docx`.

## Чого тут немає і чому

* **Посилання не на Google Drive.** У решти аспірантів вони ведуть на Drive кафедри, але
  заливати файли на Drive без підтвердження не можна, тому PDF лежать у Directus, як інші
  файли сайту. Якщо потрібен саме Drive — завантажити PDF на Drive й замінити два `href`.
* **Файли Кривко і Голєвої** на Drive клієнта не чіпаємо — на них просто більше немає посилань.
* **Тексти з `.docx` перенесено дослівно**, зокрема розбіжності: у Мінєєва — «Євгеніївна» й
  двокрапки («Спеціальність: …»), у Шелеханя — «Євгенівна» й тире («Спеціальність - …»).
  Нічого не вирівнювалося.
