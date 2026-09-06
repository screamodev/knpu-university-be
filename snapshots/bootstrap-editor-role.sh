#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────────
# Create a full Directus "Editor" role for news editing (articles + categories).
#
# Directus 11: permissions live on policies, not on roles. App login requires
# a policy with app_access=true. Collection CRUD alone is not enough — without
# App Access the Data Studio returns Access Denied.
#
# This script idempotently creates:
#   • Role "Editor"
#   • Policy "Editor" (app_access=true, admin_access=false)
#   • Access link: role → policy
#   • Permissions for articles, categories, junctions, and files
#
# Optional — create / update an editor user when both are set:
#   EDITOR_EMAIL=editor@example.com
#   EDITOR_PASSWORD='…'
#
# Usage (dev):
#   docker compose -f docker-compose.dev.yml exec directus \
#     sh /directus/snapshots/bootstrap-editor-role.sh
#
# Usage (prod), optionally with a user:
#   docker compose -f docker-compose.prod.yml exec \
#     -e EDITOR_EMAIL=editor@hnpu.edu.ua \
#     -e EDITOR_PASSWORD='…' \
#     directus sh /directus/snapshots/bootstrap-editor-role.sh
# ──────────────────────────────────────────────────────────────────────────────
set -eu

API="${PUBLIC_URL:-http://localhost:8055}"
EMAIL="${ADMIN_EMAIL:?ADMIN_EMAIL must be set}"
PASSWORD="${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set}"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"

ROLE_NAME="Editor"
POLICY_NAME="Editor"

# shellcheck source=./http.sh
. "$SCRIPT_DIR/http.sh"

log() { printf '[editor-role] %s\n' "$*"; }

json_escape() {
  # Escape a string for embedding in JSON (no surrounding quotes).
  printf '%s' "$1" | node -e '
    let s = "";
    process.stdin.on("data", (c) => { s += c; });
    process.stdin.on("end", () => {
      process.stdout.write(JSON.stringify(s).slice(1, -1));
    });
  '
}

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
  if [ "$#" -ge 3 ]; then
    http_json "$1" "$API$2" "$3" "$TOKEN"
  else
    http_json "$1" "$API$2" "" "$TOKEN"
  fi
}

# ── 1. Role ──────────────────────────────────────────────────────────────────
log "Looking up role \"$ROLE_NAME\"..."
ROLES=$(api GET "/roles?filter%5Bname%5D%5B_eq%5D=$ROLE_NAME&fields=id,name&limit=1")
ROLE_ID=$(printf '%s' "$ROLES" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')

if [ -z "$ROLE_ID" ]; then
  log "Creating role \"$ROLE_NAME\"..."
  CREATE_ROLE=$(
    api POST "/roles" \
      "{\"name\":\"$ROLE_NAME\",\"icon\":\"edit_note\",\"description\":\"Редактори новин: articles і categories. Вхід в адмінку без прав адміністратора.\"}"
  )
  ROLE_ID=$(printf '%s' "$CREATE_ROLE" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
  if [ -z "$ROLE_ID" ]; then
    log "Failed to create role: $CREATE_ROLE"
    exit 1
  fi
  log "Created role $ROLE_ID"
else
  log "Found existing role $ROLE_ID"
fi

# ── 2. Policy (App Access ON, Admin Access OFF) ──────────────────────────────
log "Looking up policy \"$POLICY_NAME\"..."
POLICIES=$(api GET "/policies?filter%5Bname%5D%5B_eq%5D=$POLICY_NAME&fields=id,name,app_access,admin_access&limit=1")
POLICY_ID=$(printf '%s' "$POLICIES" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')

if [ -z "$POLICY_ID" ]; then
  log "Creating policy \"$POLICY_NAME\" (app_access=true)..."
  CREATE_POLICY=$(
    api POST "/policies" \
      "{\"name\":\"$POLICY_NAME\",\"icon\":\"edit_note\",\"description\":\"App Access + CRUD для articles/categories і файлів. Без Admin Access.\",\"app_access\":true,\"admin_access\":false,\"enforce_tfa\":false,\"ip_access\":null}"
  )
  POLICY_ID=$(printf '%s' "$CREATE_POLICY" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
  if [ -z "$POLICY_ID" ]; then
    log "Failed to create policy: $CREATE_POLICY"
    exit 1
  fi
  log "Created policy $POLICY_ID"
else
  log "Found existing policy $POLICY_ID — ensuring app_access=true, admin_access=false..."
  api PATCH "/policies/$POLICY_ID" \
    '{"app_access":true,"admin_access":false,"enforce_tfa":false}' >/dev/null
fi

# ── 3. Attach policy to role ─────────────────────────────────────────────────
log "Ensuring Access link role → policy..."
ACCESS=$(
  api GET "/access?filter%5Bpolicy%5D%5B_eq%5D=$POLICY_ID&filter%5Brole%5D%5B_eq%5D=$ROLE_ID&fields=id&limit=1"
)
ACCESS_ID=$(printf '%s' "$ACCESS" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
if [ -z "$ACCESS_ID" ]; then
  CREATE_ACCESS=$(
    api POST "/access" \
      "{\"policy\":\"$POLICY_ID\",\"role\":\"$ROLE_ID\",\"user\":null,\"sort\":1}"
  )
  ACCESS_ID=$(printf '%s' "$CREATE_ACCESS" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
  if [ -z "$ACCESS_ID" ]; then
    log "Failed to create access link: $CREATE_ACCESS"
    exit 1
  fi
  log "Created access entry $ACCESS_ID"
else
  log "Access entry already exists ($ACCESS_ID)."
fi

# ── 4. Permissions ───────────────────────────────────────────────────────────
# Wipe and re-seed so re-runs stay consistent. App Access Minimum for system
# collections is injected by Directus at runtime when app_access=true — we still
# add the content + files permissions editors need day-to-day.
log "Clearing existing permissions for Editor policy..."
api DELETE "/permissions?filter%5Bpolicy%5D%5B_eq%5D=$POLICY_ID" >/dev/null || true

add_perm() {
  # $1 = collection, $2 = action, $3 = fields JSON, $4 = item filter JSON or empty
  COLLECTION=$1
  ACTION=$2
  FIELDS=$3
  PERM_FILTER=${4:-}
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
  RESULT=$(api POST "/permissions" "$BODY")
  case "$RESULT" in
    *'"id":'*) log "  + $ACTION on $COLLECTION" ;;
    *) log "  ! failed $ACTION on $COLLECTION: $RESULT"; exit 1 ;;
  esac
}

add_crud() {
  COLLECTION=$1
  for ACTION in create read update delete; do
    add_perm "$COLLECTION" "$ACTION" "$ALL" ""
  done
}

ALL='["*"]'
OWN_USER_FILTER='{"id":{"_eq":"$CURRENT_USER"}}'

log "Seeding Editor permissions..."

# Content the editor is meant to manage
add_crud articles
add_crud categories
add_crud articles_files
add_crud articles_categories

# Newspaper «Учитель» — editors publish one issue a month themselves
add_crud newspaper_issues

# Документи розділу «Відвідувачу» — накази, звіти, вакансії тощо
add_crud documents

# Тексти вкладок на сторінках підрозділів, факультетів і кафедр
add_crud structure_pages

# Media library — required for cover, Content images, attachments
add_crud directus_files
add_perm directus_folders read "$ALL" ""

# Own profile (language / last page) — Recommended Defaults style
add_perm directus_users update \
  '["first_name","last_name","email","password","location","title","description","avatar","language","appearance","theme_light","theme_dark","tfa_secret","last_page"]' \
  "$OWN_USER_FILTER"

# ── 5. Optional editor user ──────────────────────────────────────────────────
if [ -n "${EDITOR_EMAIL:-}" ] && [ -n "${EDITOR_PASSWORD:-}" ]; then
  ESCAPED_EMAIL=$(json_escape "$EDITOR_EMAIL")
  ESCAPED_PASSWORD=$(json_escape "$EDITOR_PASSWORD")

  log "Looking up user $EDITOR_EMAIL..."
  # Email may contain +/@ — filter via encoded query is fragile; list and match in node.
  USERS=$(api GET "/users?fields=id,email,role&limit=-1")
  USER_ID=$(
    EDITOR_EMAIL="$EDITOR_EMAIL" USERS_JSON="$USERS" node <<'NODE'
const email = process.env.EDITOR_EMAIL.toLowerCase();
let data;
try {
  data = JSON.parse(process.env.USERS_JSON).data || [];
} catch {
  process.exit(0);
}
const user = data.find((u) => String(u.email || "").toLowerCase() === email);
if (user) process.stdout.write(user.id);
NODE
  )

  if [ -z "$USER_ID" ]; then
    log "Creating editor user $EDITOR_EMAIL..."
    CREATE_USER=$(
      api POST "/users" \
        "{\"email\":\"$ESCAPED_EMAIL\",\"password\":\"$ESCAPED_PASSWORD\",\"status\":\"active\",\"role\":\"$ROLE_ID\",\"first_name\":\"Editor\"}"
    )
    USER_ID=$(printf '%s' "$CREATE_USER" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
    if [ -z "$USER_ID" ]; then
      log "Failed to create user: $CREATE_USER"
      exit 1
    fi
    log "Created user $USER_ID"
  else
    log "Updating existing user $USER_ID → role Editor, status active..."
    api PATCH "/users/$USER_ID" \
      "{\"password\":\"$ESCAPED_PASSWORD\",\"status\":\"active\",\"role\":\"$ROLE_ID\"}" >/dev/null
  fi
else
  log "Skipping user creation (set EDITOR_EMAIL and EDITOR_PASSWORD to create one)."
fi

log "Done."
log "Role:   $ROLE_NAME ($ROLE_ID)"
log "Policy: $POLICY_NAME ($POLICY_ID) — app_access=true, admin_access=false"
log "Assign users to role \"$ROLE_NAME\" in Settings → Users, then they can open the Data Studio."
log "Collections: articles, categories, articles_files, articles_categories, newspaper_issues, documents, structure_pages, directus_files (+ folders read)."
