# Правки 28.10.2026 — «На допомогу здобувачу»

Документ «Правки 26-28.10.26», сторінка `/science/candidate-support`, розділ «Здобувачу
наукового ступеня доктора філософії». Просять:

1. змінити покликання на перелік документів, що подаються до атестаційної справи;
2. розмістити покликання на «Вимоги до оформлення дисертації»;
3. прибрати відео та покликання на інструкцію щодо підписання документа через «Документ онлайн».

## Що куди їде

| Що | Куди |
| --- | --- |
| пункт 1 — нове покликання на перелік | уже змінено вручну в Directus (`documents`, «Перелік документів, що подаються до атестаційної справи»), тут не чіпається |
| пункт 2 — «Вимоги до оформлення дисертації» → `https://zakon.rada.gov.ua/laws/show/z0155-17#Text` | `documents`, розділ `candidate-support`, `order` 5 (`data/documents.json`) |
| пункт 3 — відео «Як отримати електронний підпис від ПриватБанку» і покликання «Накладання КЕП за допомогою сайту Document.Online» | фронт, `knpu-university-fe` (`pages/science/candidate-support.vue`, локалі) |

Друге відео («Як користуватися е-підписом…») і покликання на ЦЗО лишаються: у позначеному
клієнтом скриншоті виділено лише перше відео й покликання Document.Online.

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
DRUN pass2/load.py fixes-2026-10-28-candidate-support/data/documents.json
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

Схема й права не міняються. `load.py` пропускає вже наявний рядок.

## Чого тут немає і чому

* Файлів немає: усе — покликання.
