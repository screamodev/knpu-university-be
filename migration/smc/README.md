# migration/smc — центр забезпечення якості освіти

The centre ran its own Joomla 3 site at `smc.hnpu.edu.ua`. Pass 2 migrated what was publicly
readable; this folder finishes the job from the database dump the client handed over
(`website/hnpu_smc_temp.sql`), which also contains the sections that were behind a login.

| Stage | Script | What it does |
|---|---|---|
| 1 | `1_extract.py` | parses the dump directly (no MySQL container) → `data/news.json`, `data/pages.json` |
| 2 | `2_load_news.py` | the «Новини» page's accordion entries → `articles` + category «Центр забезпечення якості освіти» |
| 3 | `3_emit_pages.py` | the remaining pages → `app/content/pages/quality-centre-<tab>.uk.json` |
| — | `../pass2/mirror_page_files.py` | re-hosts the ~2 300 PDFs and images those pages link to |

```bash
export DIRECTUS_URL=http://localhost:8055
export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin

python3 1_extract.py
python3 2_load_news.py --dry-run && python3 2_load_news.py
python3 3_emit_pages.py

cd ../pass2 && python3 mirror_page_files.py \
  --content ../../../knpu-university-fe/app/content/pages \
  --unlink-host smc.hnpu.edu.ua --unlink-missing
```

Notes:

- The dump has two table prefixes; the live data is `nijst_*` (`jwm8v_*` is an empty leftover).
- «Новини» was one 200 KB page of `{spoiler}` blocks — 138 entries, 117 of which state their date.
  The rest (greetings) are loaded without one.
- `SKIP_IDS` in stage 1 lists what is deliberately left behind: the 2017–2019 rating and schedule
  archives, and per-faculty stubs written for the pre-2026 chart.
- Mirroring a few thousand files makes the local Directus restart; the uploader retries, so a run
  survives it. On production use a static `DIRECTUS_TOKEN` and a separate `files.map.json`.
