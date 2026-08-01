# knpu-university-be

Directus 11 backend for the KNPU University website. Provides the REST/GraphQL/WebSocket API, admin UI, auth, and file storage consumed by the Nuxt frontend (`knpu-university-fe`).

Runs fully in Docker — the only host requirement is Docker Desktop (or Docker Engine + Compose v2).

## Stack

- [Directus 11](https://directus.io/) (`directus/directus:11`) — headless CMS.
- [PostgreSQL 16](https://www.postgresql.org/) (`postgres:16-alpine`) — primary database.
- Local file storage driver — uploads live in the `uploads` named volume.

## First-time setup

```bash
cp .env.example .env
# Generate strong values for KEY and SECRET and set them in .env.
# On macOS / Linux:
#   node -e "console.log(require('crypto').randomUUID())"
#   node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"

docker compose -f docker-compose.dev.yml up -d
```

On first boot, Directus will:

1. Wait for Postgres to become healthy.
2. Run its internal migrations to create the core system tables.
3. Create the admin user using `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`.

At this point the admin UI is reachable at <http://localhost:8055> but the
project has **no content collections yet**. Bootstrap them in one command:

```bash
docker compose -f docker-compose.dev.yml exec directus \
  sh /directus/snapshots/bootstrap.sh
```

`bootstrap.sh` is idempotent and does four things:

1. Waits for `GET /server/health` to return 200.
2. Logs in as `ADMIN_EMAIL` — this verifies the env-seeded admin account
   actually exists (if login fails, the admin user was not seeded).
3. Runs `npx directus schema apply /directus/snapshots/schema.yaml -y` to
   create/diff the content collections (`articles`, `categories`, `events`,
   `partners`, `programmes`, plus the `articles_files` and `articles_categories`
   M2M junctions).
4. Seeds the `Public` policy + unauthenticated read permissions
   (`status=published` filter on articles/events/partners/programmes; no
   filter on `categories`, `articles_files`, `articles_categories`, and
   `directus_files`).

Re-run it any time you need to re-apply the committed schema or reset the
public permissions.

### News editing (WYSIWYG, image presets, live preview)

`articles.content` / `contentEn` use `input-rich-text-html`: a WYSIWYG with a
link dialog (own link text + open-in-new-tab), an image dialog (alt text, size,
preset), tables, alignment, media embeds and a source-code view. Bodies are
therefore **HTML**; the site also still renders older Markdown bodies, and
`migration/md-to-html/` converts existing ones (reversibly — read its README
before running it on production).

A second bootstrap script seeds what a schema snapshot cannot carry:

```bash
docker compose -f docker-compose.dev.yml exec directus \
  sh /directus/snapshots/bootstrap-editor-experience.sh
```

It creates the `Новини` upload folder, registers the `article-full` /
`article-half` / `article-thumb` image presets shown in the editor's image
dialog, and — when `SITE_URL`, `PREVIEW_SECRET` and `PREVIEW_TOKEN` are set —
a read-only preview account plus the `preview_url` that powers Directus Live
Preview of drafts. The secret and token must match `NUXT_PREVIEW_SECRET` and
`NUXT_DIRECTUS_PREVIEW_TOKEN` on the frontend.

**Covers:** the site scales cover images through `/assets/<id>?width=…` and
anchors the crop on the file's focal point. When a subject sits off-centre,
open the file in Directus and set the focal point — otherwise the crop stays
centred.

### Regenerating the schema snapshot

If you change the schema via the admin UI and want to commit it:

```bash
docker compose -f docker-compose.dev.yml exec directus \
  npx directus schema snapshot ./snapshots/schema.yaml -y
```

Commit the updated `snapshots/schema.yaml`. Note that schema snapshots do
**not** capture roles, policies, or permissions — those live in
`bootstrap-public-access.sh` (Public) and `bootstrap-editor-role.sh` (Editor).

To create the **Editor** role (App Access + CRUD on articles/categories/files):

```bash
docker compose -f docker-compose.dev.yml exec directus \
  sh /directus/snapshots/bootstrap-editor-role.sh

# optional: also create/update a user for that role
docker compose -f docker-compose.dev.yml exec \
  -e EDITOR_EMAIL=editor@example.com \
  -e EDITOR_PASSWORD='…' \
  directus sh /directus/snapshots/bootstrap-editor-role.sh
```

### Article categories (M2M)

An article links to any number of categories through the `articles_categories`
junction (`articles.categories` in the admin UI). The old single-value
`articles.category` M2O is gone. Deploying this to an environment that still has
the old column, in this order:

```bash
# 1. Park the legacy article→category mapping (the schema apply drops the column).
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U "$DB_USER" -d "$DB_DATABASE" -v ON_ERROR_STOP=1 \
  < snapshots/backfill-article-categories.sql

# 2. Apply the schema: creates articles_categories, drops articles.category.
docker compose -f docker-compose.prod.yml exec directus \
  npx directus schema apply /directus/snapshots/schema.yaml -y

# 3. Same file again — now it fills the junction from the parked rows.
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U "$DB_USER" -d "$DB_DATABASE" -v ON_ERROR_STOP=1 \
  < snapshots/backfill-article-categories.sql

# 4. Refresh public permissions so the junction is publicly readable.
docker compose -f docker-compose.prod.yml exec directus \
  sh /directus/snapshots/bootstrap-public-access.sh
```

Step 1 must run before step 2 — once the column is dropped the mapping only
exists in the `articles_categories_legacy` holding table the script creates.

## Day-to-day commands

```bash
# Start in the background.
docker compose -f docker-compose.dev.yml up -d

# Tail logs.
docker compose -f docker-compose.dev.yml logs -f directus

# Stop (keep data).
docker compose -f docker-compose.dev.yml down

# Stop and wipe data (postgres + uploads).
docker compose -f docker-compose.dev.yml down -v
```

## Connecting from the frontend

The frontend container talks to Directus via `host.docker.internal:8055`; the browser uses `http://localhost:8055`. Those values are wired up in `knpu-university-fe/docker-compose.dev.yml`.

## Directory layout

```
.
├── docker-compose.dev.yml   # Postgres + Directus services
├── .env.example             # Template for .env
├── snapshots/
│   ├── schema.yaml                   # Committed schema (collections/fields/relations)
│   ├── bootstrap.sh                  # First-boot: health-check → schema apply → perms
│   ├── bootstrap-public-access.sh    # Seeds Public policy + read permissions
│   └── backfill-article-categories.sql  # One-off: articles.category → articles_categories
├── database/
│   └── migrations/          # Optional custom SQL migrations (mounted into Directus)
└── extensions/              # Directus extensions (bind-mounted), e.g. slug autofill
```

`uploads/` is a Docker named volume (not committed). `extensions/` is bind-mounted from the repo.
