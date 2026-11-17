# Правки 17.11.2026

Документ «Правки 16-20.11.2026», вкладка «Правки 17.11.26». Матеріали — лист В. В. Піддубної
«сайт кафедри українознавстсва і лінгводидактики» (17.11, 08:15): `10_2026_1.png`, `10_2026_2.png`,
`УкрСтудіяЖовтень 2026.docx`.

| Пункт | Що | Куди (FE) |
| --- | --- | --- |
| Кафедра українознавства і лінгводидактики, «Наукова діяльність» → Студентський науковий гурток → Секція "Українознавчі студії" → «Новини гуртка» | «Музичні історії: «Пісня і Доля»» (засідання студії «Бджола» з Іваном Ганзерою, 29.10.2026) — першим записом; фото 1 після рядка «Іваном Ганзерою.», фото 2 після абзацу про спогади (як позначено в docx) | `app/content/structure/kafedra-ukrayinoznavstva-i-lingvodydaktyky/science.uk.json` |

Файли — два зображення в `files/` (оригінали з листа, 640×360), `files.map.json` — карта uuid5.

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-11-17/push_assets.py --dry-run && DRUN fixes-2026-11-17/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

## Чого тут немає і чому

- Пункт 16.11 (кафедра психологічної і педагогічної антропології, лінк на персональну сторінку
  Дорожко І. І.) — позначений «ОЧІКУЄТЬСЯ ВІДПОВІДЬ», самого лінка в документі немає.
- Лист 08:17 «Прошу розмістити інформацію у Новинах кафедри…» (`10_2026_1_1.png`, `Жовтень 2026_новини.docx`)
  — у документі правок такого пункту немає, не чіпали.

## Місця, де текст не дослівний

- «А.О  Новиков» (без крапки, подвійний пробіл) → «А.О. Новиков».
- «Варич Н.І., Петрова Озель Л. П.» — розбиті на кілька жирних фрагментів у docx зведено в один.
