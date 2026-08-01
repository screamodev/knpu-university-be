# Newspaper «Учитель» archive migration

Moves the PDF archive of the university newspaper from the old site into Directus, so the site
serves it and staff can publish the next issue themselves.

| Stage | Script | Input | Output |
|---|---|---|---|
| 1 | `1_fetch.py` | `https://hnpu.edu.ua/uk/arhiv-vydannya-uchytel` | `issues.json` |
| 2 | `2_load.py` | `issues.json` | PDFs + rows in Directus, `files.map.json` |

## Why the live page, not the SQL dump

The dump (`website/hnpu_main_temp.sql`) stops at № 343-344 (March 2025); the archive page runs to
the current issue. More importantly, every link on the page carries a human label —
`№ 8-9 (349-350) вересень 2025` — which already holds the issue number, the continuous number and
the month. The PDF filenames, by contrast, come in eight inconsistent formats and several start
with `##`. So the label is parsed and the filename ignored; files are re-named
`uchytel-<serial>-<YYYY-MM>.pdf` on upload.

97 issues, 2015 → 2026, ~450 MB.

## Running it

```bash
cd knpu-university-be/migration/newspaper

python3 1_fetch.py --report            # → issues.json, prints anomalies

docker run --rm -v "$PWD":/work -w /work \
  -e DIRECTUS_URL=http://host.docker.internal:8055 \
  -e DIRECTUS_EMAIL=admin@example.com -e DIRECTUS_PASSWORD=admin \
  python:3.12-slim python 2_load.py --dry-run

... python 2_load.py --limit 5         # trial, check them on the site
... python 2_load.py                   # the rest, ~20–40 min
```

Both stages are safe to repeat. Uploads are cached in `files.map.json` and rows are matched on
`serial`, so re-running after a new issue is published only does the new work — that is also how
you top the archive up later if the client keeps posting to the old site for a while.

`--from-year 2023` and `--limit N` narrow the run.

## Anomalies it reports (their data, not ours)

`1_fetch.py` prints, without "fixing" anything:

- labels it could not parse (currently none),
- two issues pointing at the same PDF,
- issues whose label year differs from the year in the filename — five of them, e.g.
  `№ 1 (241) Січень 2017` links to `##2016-03(233)CS6.pdf`. Worth asking the editors about.

## Prerequisites in Directus

- collection `newspaper_issues` (in `snapshots/schema.yaml`)
- public read + Editor CRUD (`snapshots/bootstrap-public-access.sh`, `bootstrap-editor-role.sh`)
- the `Газета «Учитель»` folder, id `7c2a5b93-4d18-4f60-8a2e-3b6d90f14c55`
  (`snapshots/bootstrap-editor-experience.sh`) — `2_load.py` uploads into it

## Files produced (git-ignored)

`issues.json`, `files.map.json` (environment specific — move it aside before pointing stage 2 at
production), `*.log`.
