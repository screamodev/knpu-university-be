# migration/pass2 — Навчання, Наука, підрозділи

Second migration pass: the pages the first one deferred (`MIGRATION_REPORT.md`, «Follow-ups»).
Sources are `hnpu.edu.ua`, the quality centre's Joomla site `smc.hnpu.edu.ua`, the university's
Google site of наукові школи and one Google Drive PDF.

All files are re-hosted in Directus — nothing on the site points at the old hosts.

## Layout

| File | What it does |
|---|---|
| `common.py` | fetching + caching (`.cache/`), HTML helpers, Directus client, upload |
| `extract_*.py` | read one source, write `data/<name>.json` — no writes to Directus |
| `load.py` | write any `data/*.json` into Directus (idempotent, resumable) |
| `sources.json` | `documents.section` → legacy page, for the plain «list of files» pages |
| `data/*.json` | the extracted payloads, committed so a load can be replayed |
| `files.map.json` | source URL → uploaded file id; **per environment**, move it aside when switching local ↔ prod |

## Payload format

```json
{
  "batches": [
    { "collection": "…", "identity": ["…"], "rows": [ { "_ref": "d1", "…": "…" } ] },
    { "collection": "…", "identity": ["…"], "parent": {"field": "dossier", "from": "_parent"},
      "rows": [ { "_parent": "d1", "_file": "https://…/file.pdf" } ] }
  ]
}
```

Keys starting with `_` are directives (`_file`, `_fileField`, `_ref`, `_parent`); the rest is
written to Directus as-is. `identity` is what makes a row unique — a re-run skips rows that match.

## Running

```bash
cd migration/pass2
export DIRECTUS_URL=http://localhost:8055
export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin

# 1. schema (once per environment)
docker run --rm --network host -v "$(pwd)/../schema":/work -w /work python:3.12-slim \
  python apply_schema.py

# 2. extract (only when the legacy pages changed; `data/` is committed)
docker run --rm --network host -v "$(pwd)":/work -w /work python:3.12-slim \
  sh -c 'python extract_documents.py && python extract_monitoring.py &&
         python extract_contingent.py && python extract_accreditation_certificates.py &&
         python extract_accreditation_dossiers.py &&
         pip install --quiet pypdf && python extract_science_directions.py'

# 3. load
docker run --rm --network host -v "$(pwd)":/work -w /work python:3.12-slim \
  sh -c 'for f in data/*.json; do python load.py "$f"; done'
```

Add `--dry-run` to see the row counts, `--limit N` to stop early. On production use a **static**
token (`DIRECTUS_TOKEN=…`): a login token expires after 15 minutes and a full run takes longer.

Prose pages are not handled here — they go through `../pages/migrate_page.py`, which now also
understands Joomla bodies (`--body-start` for pages that render text through a module),
`--unlink-legacy` (unwrap links back to the old site) and reads this folder's `data/documents.json`
for `--strip-documents`.

## What each extractor produces

| Extractor | Source | Collections |
|---|---|---|
| `extract_documents.py` | `sources.json` (9 pages) | `documents` (10 sections) |
| `extract_monitoring.py` | `/uk/monitoryng` | `documents` (monitoring), `monitoring_surveys`, `monitoring_survey_results` |
| `extract_contingent.py` | `/uk/division/kontyngent` | `contingent_reports` |
| `extract_accreditation_certificates.py` | `/uk/sertyfikaty-pro-akredytaciyu` | `accreditation_certificates` |
| `extract_accreditation_dossiers.py` | `smc.hnpu.edu.ua/akredytatsiia` | `accreditation_dossiers`, `accreditation_dossier_files` |
| `extract_science_directions.py` | Drive PDF «Основні напрямки…» (needs `pypdf`) | `science_directions` |
| — (hand-written) | `sites.google.com/hnpu.edu.ua/scienceschools` | `science_schools` |

`data/science_schools.json` has no extractor on purpose: the Google site splits names and
supervisors across dozens of styled `<p>` elements, and every parser variant mixed up which
керівник belonged to which школа. The 32 rows are transcribed from the page instead; the file
records the source and the capture date.

## Known gaps

- `smc.hnpu.edu.ua/dokumenty` requires a login («Ви не авторизовані для перегляду сайту»), so its
  documents could not be migrated.
- Nine files 404 on the old site and could not be re-hosted (see `MIGRATION_REPORT_PART_4.md`).
- One «Результати» link on the monitoring page points at a Gmail attachment URL, which is both
  private and longer than the field allows — it was skipped.
- The quality centre's news are still on its own site; they arrive with its database dump.
