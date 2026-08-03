# Legacy document lists → `documents`

Two stages, same shape as the other migrations here.

```bash
python3 1_extract.py                 # old site  → documents.json
python3 2_load.py --dry-run          # inspect what would be created
python3 2_load.py                    # documents.json → Directus
```

`sources.json` maps a `documents.section` to the page on the old site it comes from. Add a
section there and re-run; nothing else needs to change.

## Notes

- **Stage 2 is idempotent.** Rows are keyed on `section` + `title`, files on
  `filename_download` + `filesize`, so a re-run after a failure resumes rather than duplicating.
- **Dates come from the title** — that is the only place the old site records one. Titles that
  name a period («на 2021 - 2025 рр.») stay undated on purpose; only «за 2025 рік» and explicit
  «від 25 травня 2026 року» / «25.10.2021» forms are read as dates. Most of нормативна
  документація is therefore undated, which is why the frontend sorts on `order` first.
- **`order` is the position on the legacy page**, which is hand-curated and is the only
  meaningful order those lists have.
- **Against production use a static token** (`DIRECTUS_TOKEN`): the run takes longer than the
  15-minute lifetime of a login token.

## Known gaps

Six files 404 on the old site itself and so could not be migrated — five have a non-breaking
space baked into the filename. They need to be re-uploaded by hand once the university supplies
them:

| section | title |
|---|---|
| regulations | Положення про механізми реагування на випадки булінгу (цькування) та мобінгу |
| regulations | Порядок реалізації права на академічну мобільність учасників освітнього процесу |
| regulations | Положення про порядок підготовки та реалізації грантових проєктів |
| regulations | Положення про підготовку здобувачів вищої освіти ступеня доктора філософії |
| regulations | Положення про протидію дискримінації, сексуальним домаганням та підтримку рівності |
| attestation | Положення про атестацію педагогічних працівників ВС-119/23 |

Two `facilities` rows point at faculty pages on the old site rather than at files
(`includeInternalPages` in `sources.json`); they stay external links until those faculties
supply their own documents.

`regulation-drafts` has no source: the page is empty on the old site too, so it ships with no
rows for editors to fill.
