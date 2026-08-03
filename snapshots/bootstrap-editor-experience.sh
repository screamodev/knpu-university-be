#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────────
# Seed everything the news WYSIWYG needs that a schema snapshot cannot carry.
#
# Snapshots hold collections/fields/relations. Folders, settings, roles, users
# and tokens are *data*, so they are seeded here — idempotently.
#
#   1. A "Новини" file folder, so body images uploaded from the editor land
#      somewhere tidy instead of the library root.
#   2. Image size presets, which appear as a dropdown in the editor's image
#      dialog ("insert as full width / half width / thumbnail").
#   3. Optional: a read-only preview user + token and the collection's
#      preview_url, enabling Directus Live Preview of drafts.
#
# Prereqs (inside the directus container):
#   • /directus/snapshots/schema.yaml already applied
#   • ADMIN_EMAIL and ADMIN_PASSWORD exported (docker-compose passes them)
#
# Optional environment for live preview (all three or none):
#   SITE_URL         public site base, e.g. https://hnpu.dev42hub.uk
#   PREVIEW_SECRET   shared secret, must equal the site's NUXT_PREVIEW_SECRET
#   PREVIEW_TOKEN    static token, must equal NUXT_DIRECTUS_PREVIEW_TOKEN
#
# Usage:
#   docker compose -f docker-compose.dev.yml exec directus \
#     sh /directus/snapshots/bootstrap-editor-experience.sh
# ──────────────────────────────────────────────────────────────────────────────
set -eu

API="${PUBLIC_URL:-http://localhost:8055}"
EMAIL="${ADMIN_EMAIL:?ADMIN_EMAIL must be set}"
PASSWORD="${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set}"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"

# shellcheck source=./http.sh
. "$SCRIPT_DIR/http.sh"

log() { printf '[editor] %s\n' "$*"; }

# A fixed id keeps the field's `folder` option valid in every environment.
NEWS_FOLDER_ID="9f1d4e2a-6c3b-4a51-9e77-1c0b5d2f8a10"
NEWS_FOLDER_NAME="Новини"

# Newspaper «Учитель» PDFs — a fixed id so the folder is the same in every environment.
PAPER_FOLDER_ID="7c2a5b93-4d18-4f60-8a2e-3b6d90f14c55"
PAPER_FOLDER_NAME="Газета «Учитель»"

# Документи сторінок розділу «Відвідувачу».
DOCS_FOLDER_ID="3e5f21c7-8b04-4d92-a6f1-27c48ab5d301"
DOCS_FOLDER_NAME="Документи"

# Directus validates the address, so it must look real; this account can only read.
PREVIEW_EMAIL="${PREVIEW_EMAIL:-site-preview@hnpu.dev42hub.uk}"

log "Logging in as $EMAIL..."
LOGIN_RESPONSE=$(http_json POST "$API/auth/login" "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
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

# ── 1. Upload folder for news imagery ────────────────────────────────────────
ensure_folder() {
  # $1 = id, $2 = name
  EXISTING_FOLDER=$(api GET "/folders/$1?fields=id")
  case "$EXISTING_FOLDER" in
    *"\"id\":\"$1\""*)
      log "Folder $2 already exists."
      ;;
    *)
      log "Creating folder $2..."
      api POST "/folders" "{\"id\":\"$1\",\"name\":\"$2\"}" >/dev/null
      ;;
  esac
}

ensure_folder "$NEWS_FOLDER_ID" "$NEWS_FOLDER_NAME"
ensure_folder "$PAPER_FOLDER_ID" "$PAPER_FOLDER_NAME"
ensure_folder "$DOCS_FOLDER_ID" "$DOCS_FOLDER_NAME"

# ── 2. Image presets offered in the editor's image dialog ────────────────────
# `storage_asset_transform` stays "all": the public site passes its own width/quality
# parameters for covers, and restricting to presets would break that.
log "Setting image presets..."
PRESETS='[
  {"key":"article-full","fit":"contain","width":1200,"height":null,"quality":82,"withoutEnlargement":true,"format":"auto"},
  {"key":"article-half","fit":"contain","width":640,"height":null,"quality":82,"withoutEnlargement":true,"format":"auto"},
  {"key":"article-thumb","fit":"cover","width":320,"height":320,"quality":80,"withoutEnlargement":true,"format":"auto"}
]'
api PATCH "/settings" "{\"storage_asset_transform\":\"all\",\"storage_asset_presets\":$PRESETS}" >/dev/null

# ── 3. Live preview (optional) ───────────────────────────────────────────────
if [ -n "${SITE_URL:-}" ] && [ -n "${PREVIEW_SECRET:-}" ] && [ -n "${PREVIEW_TOKEN:-}" ]; then
  PREVIEW_POLICY_NAME="Preview (drafts)"
  log "Configuring live preview..."

  POLICIES=$(api GET "/policies?filter%5Bname%5D%5B_eq%5D=Preview%20(drafts)&fields=id&limit=1")
  POLICY_ID=$(printf '%s' "$POLICIES" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
  if [ -z "$POLICY_ID" ]; then
    CREATED=$(api POST "/policies" "{\"name\":\"$PREVIEW_POLICY_NAME\",\"icon\":\"visibility\",\"description\":\"Read-only access to drafts for site preview\",\"app_access\":false,\"admin_access\":false}")
    POLICY_ID=$(printf '%s' "$CREATED" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
    for COLLECTION in articles events programmes categories articles_files directus_files; do
      api POST "/permissions" "{\"collection\":\"$COLLECTION\",\"action\":\"read\",\"policy\":\"$POLICY_ID\",\"fields\":[\"*\"],\"permissions\":null,\"validation\":null,\"presets\":null}" >/dev/null
      log "  + read on $COLLECTION"
    done
  fi

  USERS=$(api GET "/users?filter%5Bemail%5D%5B_eq%5D=$PREVIEW_EMAIL&fields=id&limit=1")
  USER_ID=$(printf '%s' "$USERS" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
  if [ -z "$USER_ID" ]; then
    CREATED_USER=$(api POST "/users" "{\"email\":\"$PREVIEW_EMAIL\",\"first_name\":\"Site\",\"last_name\":\"Preview\",\"status\":\"active\",\"token\":\"$PREVIEW_TOKEN\",\"policies\":[{\"policy\":\"$POLICY_ID\"}]}")
    USER_ID=$(printf '%s' "$CREATED_USER" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
    log "  + preview user $USER_ID"
  else
    api PATCH "/users/$USER_ID" "{\"token\":\"$PREVIEW_TOKEN\"}" >/dev/null
    log "  = preview user token refreshed"
  fi

  api PATCH "/collections/articles" \
    "{\"meta\":{\"preview_url\":\"$SITE_URL/news/{{slug}}?preview=$PREVIEW_SECRET\"}}" >/dev/null
  log "  = preview_url set on articles"
else
  log "Skipping live preview (set SITE_URL, PREVIEW_SECRET and PREVIEW_TOKEN to enable)."
fi

log "Done."
