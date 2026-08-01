# Faculty pages migration (Drupal 7 → static content in the frontend)

Fills the tabs of `/university/structure/<unit>` with the content that used to live behind each
faculty's sidebar menu on the old site.

| Stage | Script | Input | Output |
|---|---|---|---|
| 1 | `1_extract.py` | legacy MySQL container + `units.map.json` | `pages.raw.jsonl`, `menu.draft.json`, `alias.redirects.json` |
| 2 | `2_transform.py` | those + `tabs.map.json` | `content.draft.json`, `images.list.json`, `tabs.map.draft.json` |
| 3 | `3_load_images.py` | `images.list.json` | files in Directus + `images.map.json` |
| 4 | `4_emit.py` | `content.draft.json` + `images.map.json` | `knpu-university-fe/app/content/structure/**` |

Only stages 3 and 4 write outside this folder. Everything is re-runnable; stage 3 is idempotent
through its cache, stage 4 rewrites the same files with stable key order.

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

- **`units.map.json`** — current unit slug → legacy alias(es). Note that the 30.06.2026 chart
  split the old «Факультет природничої, спеціальної і здоров'язбережувальної освіти» across
  `special-education` and `mathematics-informatics`, so `fac-prirodn` is listed twice and both
  units currently receive the same pages. **This split needs a human decision.**
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
