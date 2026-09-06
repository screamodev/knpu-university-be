# Faculty pages migration (Drupal 7 → static content in the frontend)

Fills the tabs of `/university/structure/<unit>` with the content that used to live behind each
faculty's sidebar menu on the old site.

| Stage | Script | Input | Output |
|---|---|---|---|
| 1 | `1_extract.py` | legacy MySQL container + `units.map.json` | `pages.raw.jsonl`, `menu.draft.json`, `alias.redirects.json` |
| 2 | `2_transform.py` | those + `tabs.map.json` | `content.draft.json`, `images.list.json`, `tabs.map.draft.json` |
| 3 | `3_load_images.py` | `images.list.json` | files in Directus + `images.map.json` |
| 4 | `4_emit.py` | `content.draft.json` + `images.map.json` | `knpu-university-fe/app/content/structure/**` |
| 8 | `8_fix_unit_content.py` | emitted content | repairs one unit: drops sections shared with another unit, moves a «Деканат» block between tabs |
| 9 | `9_export_to_directus.py` | emitted content | `data/structure-pages.json` — конверт для `../pass2/load.py`, щоб вкладки редагувалися в адмінці |

Only stages 3 and 4 write outside this folder. Everything is re-runnable; stage 3 is idempotent
through its cache, stage 4 rewrites the same files with stable key order.

## Stage 9 — віддати вкладки редакторам

Стадії 1–8 кладуть тексти у фронт, звідки їх може змінити лише розробник зі складанням образу.
Стадія 9 переносить те саме в колекцію `structure_pages`, і сайт починає читати вкладку звідти:
`app/composables/useStructureTabContent.ts` спершу питає Directus, а якщо рядка немає або
Directus недоступний — бере мігрований JSON, як раніше.

Тому переносити можна **підрозділами**, а не все за раз, і будь-коли відкотитися — досить
видалити рядки.

```bash
export DIRECTUS_URL=http://localhost:8055
export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin

python3 9_export_to_directus.py kafedra-horeografiyi
python3 ../pass2/load.py data/structure-pages.json --dry-run
python3 ../pass2/load.py data/structure-pages.json
```

Що варто знати:

- **Секції схлопуються в одне поле.** Заголовок секції стає `<h2>` у тілі, `[collapse]` —
  `<details>`. У контенті підрозділів згорнутих секцій немає жодної, але конвертер той самий
  знадобиться для `app/content/pages`, де їх 334.
- **Підрозділ із блоком `people` експорт зупиняє.** Картки керівництва (54 особи в 11 файлах)
  ще не мають куди переїхати; мовчки їх втратити гірше, ніж не мігрувати підрозділ.
- **`links` лишаються у статиці** — їх читає ще й плитковий список на «Головній».
- **`load.py` пропускає наявні рядки** (звірка за `unit_slug` + `tab`), тож повторний прогін не
  затре написане редактором. Щоб перезалити вкладку з нуля, спершу видаліть рядок в адмінці.
- **Пошук по сайту індексується зі статичних файлів на складанні**, тож правки редактора
  потраплять у пошук лише після наступного білду. Коли дійде до масової міграції, це лікується
  зворотним вивантаженням Directus → JSON перед складанням.

## Where the content comes from

Faculty landing pages **and** every page behind their sidebar are Drupal `division` nodes, and
the sidebar itself is a field on the landing node (`field_usefulness`) — so the whole structure
comes out of the 300 MB dump. Contacts come from `field_chief` (dean) and `field_address`
(address/phone/email/socials).

Two wrinkles the pipeline handles:

- **Renamed aliases.** Sidebars still link to aliases that were later renamed
  (`division/istoriya-pryrodnychogo-fakultetu` → `…-fakultetu-pryrodnychoyi-specialnoyi-…`).
  The dump only keeps the current alias, so stage 1 follows the live site's redirect for
  anything it cannot resolve and caches the result in `alias.redirects.json`. Run with
  `--no-network` to use the cache only.
- **English is thin.** Only the landing nodes have an `en` twin (`drupal_node.tnid`); sub-pages
  are Ukrainian-only. The frontend falls back to the Ukrainian body with a notice.

Legacy news pages ("Новини факультету", "Хроніка подій") are **deliberately not migrated** — the
Новини tab reads our own `articles` collection filtered by a per-faculty category.

## Editorial files (committed, hand-edited)

- **`units.map.json`** — current unit slug → legacy alias(es). The 30.06.2026 chart split the old
  «Факультет природничої, спеціальної і здоров'язбережувальної освіти» across `special-education`
  and `mathematics-informatics`; `fac-prirodn` was listed under both, so фізмат received the
  природничий факультет's sections and деканат. **Resolved:** those pages belong to
  `special-education` only (client decision), and `8_fix_unit_content.py` cleaned the content that
  had already been emitted.
- **`tabs.map.json`** — which legacy page goes on which tab. Stage 2 always writes a
  keyword-bucketed `tabs.map.draft.json`; copy it to `tabs.map.json` and edit. The committed
  file wins, so hand fixes survive re-runs.

## Running it

### 0. Legacy database in a throwaway container

Same recipe as `../legacy-news/README.md`, with three more tables in the `WANT` set:
`drupal_field_data_field_usefulness`, `drupal_field_data_field_chief`,
`drupal_field_data_field_address`.

### 1–2. Extract and transform

```bash
python3 1_extract.py                 # → pages.raw.jsonl, menu.draft.json
python3 2_transform.py --report      # → content.draft.json, images.list.json
```

Both are read-only with respect to Directus and the frontend. Inspect `content.draft.json`
before going further; `--report` prints which tabs each unit ended up with.

### 3. Images → Directus

```bash
docker run --rm -v "$PWD":/work -w /work \
  -e DIRECTUS_URL=http://host.docker.internal:8055 \
  -e DIRECTUS_EMAIL=admin@example.com -e DIRECTUS_PASSWORD=admin \
  python:3.12-slim python 3_load_images.py --dry-run

... python 3_load_images.py --limit 20     # trial
... python 3_load_images.py                # ~1 800 images, tens of minutes
```

`images.map.json` is **environment specific** — move it aside before pointing stage 3 at
production, or you will emit file ids that only exist locally.

### 4. Emit into the frontend

```bash
python3 4_emit.py --dry-run
python3 4_emit.py
```

Images that never uploaded are **dropped** from the HTML — every one of them is a 404 on the
legacy host, and an `http://` src would be blocked as mixed content on the HTTPS site anyway.
Pass `--keep-missing-images` to leave the tags in place instead. The count is reported either
way; at the last run it was 32 out of 1 829.

## Files produced (all git-ignored)

`pages.raw.jsonl`, `menu.draft.json`, `alias.redirects.json`, `content.draft.json`,
`images.list.json`, `images.map.json`, `tabs.map.draft.json`, `*.log`.
