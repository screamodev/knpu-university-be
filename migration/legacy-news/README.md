# Legacy news migration (Drupal 7 → Directus `articles`)

Moves news from the old site's MySQL dump into the Directus `articles` collection.
Three stages, each re-runnable on its own, so a mistake never means starting over.

| Stage | Script | Input | Output |
|---|---|---|---|
| 1 | `1_extract.py` | legacy MySQL container | `news.raw.jsonl` |
| 2 | `2_transform.py` | `news.raw.jsonl` | `articles.json` |
| 3 | `3_load.py` | `articles.json` | rows in Directus |

Only stage 3 writes anything outside this folder, and it is **idempotent**: articles
are matched by `slug`, so re-running updates in place instead of duplicating.

## What the legacy data looks like

- News are `drupal_node` rows of type **`new`** — 1207 in total, **419 created in the
  last 5 years**, all published.
- Body HTML is in `drupal_field_data_body` (`full_html`), exactly one row per node.
- Every node has a `drupal_url_alias` (`news/<slug>`) — that is where slugs come from,
  so old links keep the same last path segment.
- News nodes carry **no** `field_image`, `field_photo` or tags: there are no covers
  and no categories in the legacy data. All imagery is inline in the body
  (1035 unique `<img>`, 996 of them on `hnpu.edu.ua`, still served over HTTP).

## Mapping

| Directus field | Source |
|---|---|
| `title` | `node.title` (entities decoded, whitespace collapsed) |
| `slug` | last segment of `url_alias`, de-duplicated with a numeric suffix |
| `content` | `body_value` HTML → Markdown |
| `excerpt` | first ~220 characters of the text, cut on a word boundary |
| `date_published` | `node.created` (UTC) |
| `status` | `published` when `node.status = 1`, else `draft` |
| `category` | fixed — «Новини університету» (`--category-slug`) |
| `cover` | first inline image, downloaded and uploaded to Directus |
| `author` | *not migrated* — legacy values are CMS usernames ("Anna"), not bylines |
| `titleEn`, `excerptEn`, `contentEn` | *empty* — the legacy site had no English news |

### HTML → Markdown notes

The frontend renders `content` with markdown-it and sanitises with DOMPurify, whose
allow-list has no `iframe`, `table`, `td` or `tr`. So the converter:

- turns YouTube/embed iframes into plain links (`/embed/<id>` → a `watch?v=` URL),
- flattens tables to `|`-separated lines,
- drops `span`/`div`/`font` styling wrappers,
- keeps headings, lists, bold/italic, blockquotes, links and images,
- rewrites relative URLs against `http://hnpu.edu.ua/`.

**Body images still point at the legacy host** (this was a deliberate choice — only
covers were imported into Directus). Two consequences worth tracking: they break if
the old site is retired, and because they are `http://` on an `https://` site,
browsers will block them as mixed content in production. Re-running stage 2 with a
future "import all images" flag is the fix when that becomes a problem.

## Running it

### 0. Legacy database in a throwaway container

```bash
# Extract just the tables we need from the 300 MB dump (a few seconds)
python3 - <<'PY'
import re
WANT = {'drupal_node','drupal_node_type','drupal_field_data_body','drupal_field_data_field_image',
        'drupal_field_data_field_photo','drupal_field_data_field_slideimage','drupal_field_data_field_tags',
        'drupal_file_managed','drupal_file_usage','drupal_url_alias','drupal_users',
        'drupal_taxonomy_term_data','drupal_taxonomy_vocabulary','drupal_taxonomy_index'}
src = 'hnpu_main_temp.sql'
cur, header = None, True
with open(src, encoding='utf-8', errors='replace') as fin, open('subset.sql', 'w', encoding='utf-8') as fout:
    for line in fin:
        m = re.match(r'^-- (?:Table structure for table|Dumping data for table) `([^`]+)`', line)
        if m:
            cur, header = m.group(1), False
        if header or cur in WANT:
            fout.write(line)
PY

docker run -d --name hnpu-legacy-mysql -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=legacy \
  -p 127.0.0.1:33066:3306 mysql:8.0 \
  --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci

docker exec -i hnpu-legacy-mysql mysql -uroot -proot --default-character-set=utf8mb4 legacy < subset.sql
```

### 1–2. Extract and transform

```bash
python3 1_extract.py --since 2021-07-25     # → news.raw.jsonl (419 rows)
python3 2_transform.py --report             # → articles.json
```

Both are read-only with respect to Directus. Inspect `articles.json` before loading.

### 3. Load — local first

The loader needs internet (to fetch cover images) *and* access to Directus. Running it
in a container gives both:

```bash
docker run --rm -v "$PWD":/work -w /work \
  -e DIRECTUS_URL=http://host.docker.internal:8055 \
  -e DIRECTUS_EMAIL=admin@example.com -e DIRECTUS_PASSWORD=admin \
  python:3.12-slim python 3_load.py --dry-run

# trial, then the full set
... python 3_load.py --limit 10
... python 3_load.py
```

Verify at http://localhost:3000/news and on a couple of detail pages.

### 4. Load — production

```bash
docker run --rm -v "$PWD":/work -w /work \
  -e DIRECTUS_URL=https://<prod-directus-host> \
  -e DIRECTUS_TOKEN=<static admin token> \
  python:3.12-slim python 3_load.py --dry-run          # ALWAYS first
... python 3_load.py --limit 10                        # then a small batch
... python 3_load.py                                   # then the rest
```

Notes for the production run:

- Take a database backup first. The loader only creates/updates `articles` and
  `directus_files`, but a backup makes a mistake a 5-minute problem.
- `covers.map.json` caches `source URL → Directus file id`. It is written per
  environment, so **delete or move it before switching between local and prod**,
  otherwise the loader will reference file ids that only exist locally.
- A prefixed static token is safer than admin credentials in shell history.
- Re-running is safe: matching is by `slug`.

## Files produced

- `news.raw.jsonl` — raw legacy rows (git-ignored, regenerate any time)
- `articles.json` — transformed payloads (git-ignored)
- `covers.map.json` — uploaded-cover cache, environment specific (git-ignored)
- `load.full.log` — output of the last full load (git-ignored)
