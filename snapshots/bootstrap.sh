#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────────
# First-boot bootstrap for a fresh Directus instance.
#
# 1. Wait for Directus to respond on its HTTP port (admin user is seeded by
#    the Directus entrypoint from ADMIN_EMAIL / ADMIN_PASSWORD on first boot).
# 2. Verify we can log in as that admin — this doubles as the "admin user
#    exists?" smoke test.
# 3. Apply the committed schema snapshot (collections, fields, relations).
# 4. Seed the Public policy + unauthenticated read permissions.
#
# This script is idempotent: re-running it on an already-bootstrapped instance
# is a no-op for the schema (Directus diffs) and resets-then-reseeds public
# permissions.
#
# Run from the host:
#   docker compose -f docker-compose.dev.yml exec directus \
#     sh /directus/snapshots/bootstrap.sh
# ──────────────────────────────────────────────────────────────────────────────
set -eu

API="${PUBLIC_URL:-http://localhost:8055}"
EMAIL="${ADMIN_EMAIL:?ADMIN_EMAIL must be set}"
PASSWORD="${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set}"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"

log() { printf '[bootstrap] %s\n' "$*"; }

# ── 1. Wait for Directus ─────────────────────────────────────────────────────
log "Waiting for Directus at $API ..."
i=0
until curl -sSf -o /dev/null "$API/server/health"; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    log "Directus did not become healthy within 60s. Aborting."
    exit 1
  fi
  sleep 1
done
log "Directus is up."

# ── 2. Verify admin login (proves the env-seeded admin user exists) ──────────
log "Verifying admin login for $EMAIL ..."
LOGIN=$(
  curl -sS -X POST "$API/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}"
)
if ! printf '%s' "$LOGIN" | grep -q '"access_token"'; then
  log "Admin login failed. Directus did not seed the admin user, or credentials are wrong."
  log "Response: $LOGIN"
  exit 1
fi
log "Admin login OK — ADMIN_EMAIL/ADMIN_PASSWORD are correctly seeded."

# ── 3. Apply the schema snapshot ─────────────────────────────────────────────
log "Applying schema from /directus/snapshots/schema.yaml ..."
cd /directus
# `schema apply` is a no-op when the diff is empty, so re-runs are safe.
npx directus schema apply /directus/snapshots/schema.yaml -y

# ── 4. Seed Public policy + permissions ──────────────────────────────────────
log "Seeding Public role permissions ..."
sh "$SCRIPT_DIR/bootstrap-public-access.sh"

log "Bootstrap complete. Admin UI: $API (login: $EMAIL)"
