# migration/razovi-rady — разові спеціалізовані вчені ради

Архів захистів доктора філософії зі сторінки
[`/uk/razovi-specializovani-vcheni-rady`](https://hnpu.edu.ua/uk/razovi-specializovani-vcheni-rady):
**263 сторінки**, ~1 600 PDF (дисертації, висновки, відгуки, рецензії, рішення) — близько **7 ГБ**.

Особливість цієї міграції: **адреси не можна змінювати**. Посилання на ці сторінки й на самі файли
внесені до державного реєстру дисертацій, тож після переїзду домену вони мають працювати далі:

| Стара адреса | Куди веде після міграції |
|---|---|
| `/uk/razovi-specializovani-vcheni-rady` | `/science/dissertation-councils` |
| `/uk/specializovana-vchena-rada-df-…` | `/science/dissertation-councils/<той самий slug>` |
| `/sites/default/files/files/Rada/Razova_rada/…pdf` | `/assets/<uuid>` |

301 віддає Nuxt: `knpu-university-fe/server/middleware/legacy-redirects.ts` читає колекцію
`legacy_redirects`, яку наповнює `4_build_redirects.py`.

## Файли

| Файл | Що робить |
|---|---|
| `shared.py` | ре-експорт хелперів `../pass2/common.py` + власний кеш сторінок і робота з легасі-шляхами |
| `1_extract_list.py` | перелік → `data/index.json` (slug, рік, підпис) |
| `2_extract_pages.py` | 263 сторінки → `data/councils.json` (конверт pass 2) |
| `3_rewrite_bodies.py` | після завантаження: `href="https://hnpu.edu.ua/…pdf"` → `href="/assets/<uuid>"` |
| `4_build_redirects.py` | → `data/legacy_redirects.json` (сторінки + файли + бекфіл минулих пасів) |
| `5_check_redirects.py` | перевірка: кожна стара адреса має віддавати 301, а ціль — 200 |
| `data/*.json` | закомічені payload'и, щоб завантаження можна було повторити без мережі |
| `.cache/` | HTML старого сайту; повторний запуск екстракторів не ходить у мережу |
| `files.map.json` | source URL → id файлу; **свій для кожного середовища**, локальний і прод не змішувати |

Схема (`dissertation_councils`, `dissertation_council_files`, `legacy_redirects`) створюється
`../schema/apply_schema.py` — окремим снапшотом вона не їде.

## Запуск

```bash
export DIRECTUS_URL=http://localhost:8055
export DIRECTUS_TOKEN=…            # статичний токен; логін-токен живе 15 хв, а прогін — години
cd migration
```

```bash
# 1. схема (один раз на середовище) + права публічного читання
docker run --rm --network host -v "$(pwd)/schema":/work -w /work python:3.12-slim python apply_schema.py
docker compose -f ../docker-compose.dev.yml exec directus sh /directus/snapshots/bootstrap-public-access.sh
```

```bash
# 2. екстракт (тільки якщо старі сторінки змінилися — data/ закомічений)
docker run --rm --network host -v "$(pwd)":/work -w /work/razovi-rady python:3.12-slim \
  sh -c 'python 1_extract_list.py && python 2_extract_pages.py'
```

```bash
# 3. завантаження: 263 ради + 1834 документи, з них ~1620 качаються (~7 ГБ, кілька годин)
docker run --rm --network host -v "$(pwd)":/work -w /work/razovi-rady \
  -e DIRECTUS_URL -e DIRECTUS_TOKEN python:3.12-slim \
  python ../pass2/load.py data/councils.json --map files.map.json
```

`--map files.map.json` **обов'язковий**: без нього `load.py` пише в `../pass2/files.map.json`.
Прогін ідемпотентний і відновлюваний — рядки звіряються за `identity`, а вивантажені файли
кешуються в `files.map.json` після кожного файлу. Спочатку варто `--dry-run`, потім `--limit 20`.

```bash
# 4. переписати посилання в тілах сторінок
docker run --rm --network host -v "$(pwd)":/work -w /work/razovi-rady \
  -e DIRECTUS_URL -e DIRECTUS_TOKEN python:3.12-slim \
  python 3_rewrite_bodies.py --dry-run          # потім без прапорця
```

```bash
# 5. редіректи (сторінки + файли + бекфіл pass2 / structure-pages / partners)
docker run --rm --network host -v "$(pwd)":/work -w /work/razovi-rady \
  -e DIRECTUS_URL -e DIRECTUS_TOKEN python:3.12-slim \
  sh -c 'python 4_build_redirects.py && python ../pass2/load.py data/legacy_redirects.json'
```

```bash
# 6. перевірка (сайт має бути піднятий)
docker run --rm --network host -v "$(pwd)":/work -w /work/razovi-rady \
  -e DIRECTUS_URL -e DIRECTUS_TOKEN -e SITE_URL=http://localhost:3000 python:3.12-slim \
  python 5_check_redirects.py --sample 200
```

Файли, яких старий сайт уже не віддає (404), у `files.map.json` не потрапляють; щоб не лишати
мертвих посилань у тексті, `3_rewrite_bodies.py --unlink-missing` розгортає їх у звичайний текст.

## Що саме дістається зі сторінки

`contentHtml` — усе тіло сторінки (склад ради, документи, дата й час, контакти, записи захисту),
почищене тим самим `structure-pages/2_transform.py`, що й решта міграцій. Решта полів потрібна
лише для переліку й пошуку:

- `councilCode` — «ДФ 011.143.25» із заголовка;
- `candidateName`, `dissertationTitle` — жирні абзаци на початку тіла, з відкатом на заголовок;
- `branch`, `specialty` — «з галузі знань …, за спеціальністю …» з першого абзацу;
- `defenseDate`, `defenseTime` — «Дата захисту:» / «Час захисту:», з відкатом на дату в дужках у
  переліку. У 84 рад ці поля порожні **на самому старому сайті** (захист ще попереду) — це не
  помилка розбору;
- `year` — рік захисту, інакше заголовок року в переліку, інакше останні дві цифри шифру ради.

Тип документа (`kind`) визначається за підписом посилання, а якщо підпис — просто прізвище
опонента, то за іменем файлу (`Dyser_`, `Fakh_`, `Nauker_`, `Op_`, `Retz_`, `Rishennia_`, …).
Посилання на Google Drive лишаються в тілі сторінки; окремим документом стає лише те, що має
змістовний підпис (підписані КЕП відеозаписи), а не «(КЕП)» біля вже перенесеного файлу.
