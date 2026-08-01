#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────────
# Seed Directus "Public" access (read-only for published content).
#
# Directus schema snapshots contain collections/fields/relations but NOT
# roles/policies/permissions — those live in data, not schema. This script
# fills that gap idempotently using the REST API.
#
# Prereqs (inside the directus container):
#   • /directus/snapshots/schema.yaml already applied
#   • ADMIN_EMAIL and ADMIN_PASSWORD exported in the environment (they are,
#     because docker-compose.dev.yml passes them through)
#
# Usage:
#   docker compose -f docker-compose.dev.yml exec directus \
#     sh /directus/snapshots/bootstrap-public-access.sh
# ──────────────────────────────────────────────────────────────────────────────
set -eu

API="${PUBLIC_URL:-http://localhost:8055}"
EMAIL="${ADMIN_EMAIL:?ADMIN_EMAIL must be set}"
PASSWORD="${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set}"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"

# shellcheck source=./http.sh
. "$SCRIPT_DIR/http.sh"

log() { printf '[bootstrap] %s\n' "$*"; }

# ── 1. Login as admin ────────────────────────────────────────────────────────
log "Logging in as $EMAIL..."
LOGIN_RESPONSE=$(
  http_json POST "$API/auth/login" \
    "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}"
)
TOKEN=$(printf '%s' "$LOGIN_RESPONSE" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
if [ -z "$TOKEN" ]; then
  log "Login failed: $LOGIN_RESPONSE"
  exit 1
fi

api() {
  # $1 = method, $2 = path, $3 (optional) = json body
  if [ "$#" -ge 3 ]; then
    http_json "$1" "$API$2" "$3" "$TOKEN"
  else
    http_json "$1" "$API$2" "" "$TOKEN"
  fi
}

# ── 2. Find or create the Public policy ──────────────────────────────────────
# We identify "the public policy" by a stable name we control.
POLICY_NAME="Public"

log "Looking up existing Public policy..."
POLICIES=$(api GET "/policies?filter%5Bname%5D%5B_eq%5D=$POLICY_NAME&fields=id,name&limit=1")
POLICY_ID=$(printf '%s' "$POLICIES" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')

if [ -z "$POLICY_ID" ]; then
  log "Creating Public policy..."
  CREATE=$(
    api POST "/policies" \
      '{"name":"Public","icon":"public","description":"Unauthenticated read-only access to published content.","app_access":false,"admin_access":false,"enforce_tfa":false,"ip_access":null}'
  )
  POLICY_ID=$(printf '%s' "$CREATE" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
  if [ -z "$POLICY_ID" ]; then
    log "Failed to create policy: $CREATE"
    exit 1
  fi
  log "Created Public policy $POLICY_ID"
else
  log "Found existing Public policy $POLICY_ID"
fi

# ── 3. Ensure an Access entry with role=null, user=null attaches this policy ─
# This is what tells Directus the policy applies to unauthenticated requests.
log "Ensuring Access entry for unauthenticated users..."
ACCESS=$(api GET "/access?filter%5Bpolicy%5D%5B_eq%5D=$POLICY_ID&filter%5Buser%5D%5B_null%5D=true&filter%5Brole%5D%5B_null%5D=true&fields=id&limit=1")
ACCESS_ID=$(printf '%s' "$ACCESS" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
if [ -z "$ACCESS_ID" ]; then
  CREATE_ACCESS=$(
    api POST "/access" \
      "{\"policy\":\"$POLICY_ID\",\"role\":null,\"user\":null,\"sort\":1}"
  )
  log "Created access entry."
else
  log "Access entry already exists ($ACCESS_ID)."
fi

# ── 4. Reset permissions for this policy then seed fresh ones ────────────────
# Idempotent: wipe existing rows for this policy before re-inserting.
log "Clearing existing permissions for Public policy..."
api DELETE "/permissions?filter%5Bpolicy%5D%5B_eq%5D=$POLICY_ID" >/dev/null || true

# Helper to upsert a single permission row.
add_perm() {
  # $1 = collection, $2 = action, $3 = fields, $4 = filter_json (raw json or empty)
  COLLECTION=$1; ACTION=$2; FIELDS=$3; PERM_FILTER=$4
  if [ -z "$PERM_FILTER" ]; then
    PERM_FILTER="null"
  fi
  BODY=$(cat <<JSON
{
  "collection": "$COLLECTION",
  "action": "$ACTION",
  "policy": "$POLICY_ID",
  "fields": $FIELDS,
  "permissions": $PERM_FILTER,
  "validation": null,
  "presets": null
}
JSON
)
  api POST "/permissions" "$BODY" >/dev/null
  log "  + $ACTION on $COLLECTION"
}

PUBLISHED_FILTER='{"status":{"_eq":"published"}}'
ALL='["*"]'

log "Seeding Public permissions..."
# Collections with a status workflow — filter to published only.
add_perm articles   read "$ALL" "$PUBLISHED_FILTER"
add_perm events     read "$ALL" "$PUBLISHED_FILTER"
add_perm partners   read "$ALL" "$PUBLISHED_FILTER"
add_perm programmes read "$ALL" "$PUBLISHED_FILTER"
add_perm memorial_entries  read "$ALL" "$PUBLISHED_FILTER"
add_perm gallery_categories read "$ALL" "$PUBLISHED_FILTER"
add_perm gallery_items read "$ALL" "$PUBLISHED_FILTER"
add_perm vacancies read "$ALL" "$PUBLISHED_FILTER"
add_perm student_schedule_documents read "$ALL" "$PUBLISHED_FILTER"
add_perm education_schedule_periods read "$ALL" "$PUBLISHED_FILTER"
add_perm education_schedule_key_dates read "$ALL" "$PUBLISHED_FILTER"
add_perm admission_open_days read "$ALL" "$PUBLISHED_FILTER"
add_perm admission_exam_programs read "$ALL" "$PUBLISHED_FILTER"
add_perm university_orders read "$ALL" "$PUBLISHED_FILTER"
add_perm prozorro_procurements read "$ALL" "$PUBLISHED_FILTER"
add_perm science_defenses read "$ALL" "$PUBLISHED_FILTER"
add_perm science_conferences read "$ALL" "$PUBLISHED_FILTER"
add_perm financial_reports read "$ALL" "$PUBLISHED_FILTER"
add_perm newspaper_issues read "$ALL" "$PUBLISHED_FILTER"

# Categories has no status — read everything.
add_perm categories read "$ALL" ""

# Junction collections — must be readable so M2M expansion works.
add_perm articles_files read "$ALL" ""
add_perm articles_categories read "$ALL" ""

# Files — needed so the frontend can fetch /assets/<uuid> and file metadata.
add_perm directus_files read "$ALL" ""

log "Done. Public policy $POLICY_ID now grants read access to published content."
