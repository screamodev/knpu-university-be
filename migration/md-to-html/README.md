# Markdown → HTML body conversion

Moves stored article bodies from Markdown to HTML so they can be edited in the Directus
WYSIWYG (`input-rich-text-html`) instead of a raw Markdown box.

| Script | What it does |
|---|---|
| `convert.mjs` | Markdown bodies → HTML, after writing a backup file |
| `restore.mjs` | Writes a backup file back, undoing a conversion |
| `directus.mjs` | Shared REST client (auth, Cloudflare-safe headers, argv parsing) |

## Why converting is safe

The public site renders a Markdown body as `sanitize(markdownIt.render(source))` and an HTML
body as `sanitize(source)`. `convert.mjs` stores exactly `markdownIt.render(source)`, using the
same markdown-it version (14.1.1, pinned in `package.json`) and the same options
(`html: true, linkify: true, typographer: false`) as
`knpu-university-fe/app/utils/renderStoredArticleMarkdown.ts`. Sanitizing, URL rewriting and the
resulting DOM are unchanged — **the conversion is a visual no-op**, and that was verified by
diffing rendered pages before and after on the local instance (byte-identical).

Two further properties:

- **Idempotent.** A body that already starts with a block-level tag is classified as HTML and
  skipped, so re-running changes nothing.
- **Reversible.** Every previous value is written to `backup.<host>.<timestamp>.json` *before*
  the first PATCH. `restore.mjs` puts them back.

If converted output would *not* be recognised as HTML by the frontend, the script skips that
field and prints it rather than storing something the site would re-parse as Markdown. The
detection regex is duplicated from `looksLikeHtmlBody` in
`knpu-university-fe/app/utils/articleRichTextNormalize.ts` — the two must stay in sync.

## Order of operations

The frontend must be able to render **both** formats before anything is converted. That support
shipped together with these scripts, so on production: deploy the frontend first, convert
second, switch the Directus interface to `input-rich-text-html` third.

## Running it

The scripts need Node 22 and one dependency; a container gives both:

```bash
cd knpu-university-be/migration/md-to-html

# local
docker run --rm -v "$PWD":/work -w /work \
  -e DIRECTUS_URL=http://host.docker.internal:8055 \
  -e DIRECTUS_EMAIL=admin@example.com -e DIRECTUS_PASSWORD=admin \
  node:22-slim sh -c "npm install --silent --no-audit --no-fund && node convert.mjs --dry-run"

# …then drop --dry-run
```

Production — take a database backup first, then:

```bash
docker run --rm -v "$PWD":/work -w /work \
  -e DIRECTUS_URL=$PROD_URL -e DIRECTUS_TOKEN=$PROD_TOKEN \
  node:22-slim sh -c "npm install --silent --no-audit --no-fund && node convert.mjs --dry-run"

... node convert.mjs --limit 10     # spot-check ten articles on the site
... node convert.mjs                # the rest
```

`node_modules` persists in the mounted directory, so `npm install` only downloads once.

### Flags

`convert.mjs`: `--dry-run`, `--limit N`, `--collection articles|events|programmes`,
`--out <backup path>`, `--url/--token/--email/--password` (override the environment).

`restore.mjs`: `node restore.mjs <backup.json> [--dry-run]`. It refuses to run against a
different instance than the backup came from unless `--url` is passed explicitly — item ids do
not match across environments.

## Notes

- Production is behind Cloudflare, which 403s unknown user agents with `error code: 1010`.
  `directus.mjs` sends browser headers on every request, same as
  `migration/legacy-news/3_load.py`.
- `content` and `contentEn` are both handled; empty and legacy JSON-block bodies are left alone.
- Backups, `node_modules` and `package-lock.json` are git-ignored.
