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
   `partners`, `programmes`, plus the `articles_files` M2M junction).
4. Seeds the `Public` policy + unauthenticated read permissions
   (`status=published` filter on articles/events/partners/programmes; no
   filter on `categories`, `articles_files`, and `directus_files`).

Re-run it any time you need to re-apply the committed schema or reset the
public permissions.

### Regenerating the schema snapshot

If you change the schema via the admin UI and want to commit it:

```bash
docker compose -f docker-compose.dev.yml exec directus \
  npx directus schema snapshot ./snapshots/schema.yaml -y
```

Commit the updated `snapshots/schema.yaml`. Note that schema snapshots do
**not** capture roles, policies, or permissions — those live in
`bootstrap-public-access.sh` (for the public role) and in the admin UI for
any additional roles.

## Day-to-day commands

```bash
# Start in the background.
docker compose -f docker-compose.dev.yml up -d

# Tail logs.
docker compose -f docker-compose.dev.yml logs -f directus

# Stop (keep data).
docker compose -f docker-compose.dev.yml down

# Stop and wipe data (postgres + uploads + extensions).
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
│   └── bootstrap-public-access.sh    # Seeds Public policy + read permissions
├── database/
│   └── migrations/          # Optional custom SQL migrations (mounted into Directus)
└── extensions/              # Reserved for future custom Directus extensions
```

`uploads/` and `extensions/` are Docker named volumes; they're not committed.
