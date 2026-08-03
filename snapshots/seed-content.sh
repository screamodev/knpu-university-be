#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────────
# Seed the few public records that are part of the product rather than editorial content.
#
# Creates/updates idempotently:
#   - categories        — the two baseline news categories the frontend links to
#   - partners          — the four organisations the university named
#
# Everything else (gallery, events, programmes, orders, schedules, defenses, vacancies…) used to
# be seeded here with invented rows — fake tender numbers, non-existent study groups, made-up
# dissertations. That is editorial content: it belongs to the university, so those blocks were
# removed rather than shipped as plausible-looking placeholders.
# ──────────────────────────────────────────────────────────────────────────────
set -eu

API="${PUBLIC_URL:-http://localhost:8055}"
EMAIL="${ADMIN_EMAIL:?ADMIN_EMAIL must be set}"
PASSWORD="${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set}"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"

# shellcheck source=./http.sh
. "$SCRIPT_DIR/http.sh"

log() { printf '[seed-content] %s\n' "$*"; }

extract_first_id() {
  printf '%s' "$1" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p'
}

api_json() {
  # $1 = method, $2 = path, $3 (optional) = json body
  if [ "$#" -ge 3 ]; then
    http_json "$1" "$API$2" "$3" "$TOKEN"
  else
    http_json "$1" "$API$2" "" "$TOKEN"
  fi
}

api_file_upload() {
  # $1 = file path, $2 = filename_download
  http_upload "$API/files" "$1" "$2" "$TOKEN"
}

upsert_single() {
  # $1 collection, $2 query_url, $3 create_json, $4 update_json
  COLLECTION=$1
  QUERY_URL=$2
  CREATE_BODY=$3
  UPDATE_BODY=$4

  FOUND=$(api_json GET "$QUERY_URL")
  FOUND_ID=$(extract_first_id "$FOUND")

  if [ -n "$FOUND_ID" ]; then
    api_json PATCH "/items/$COLLECTION/$FOUND_ID" "$UPDATE_BODY" >/dev/null
    printf '%s' "$FOUND_ID"
    return
  fi

  CREATED=$(api_json POST "/items/$COLLECTION" "$CREATE_BODY")
  CREATED_ID=$(extract_first_id "$CREATED")
  if [ -z "$CREATED_ID" ]; then
    log "Failed to create item in $COLLECTION. Response: $CREATED"
    exit 1
  fi
  printf '%s' "$CREATED_ID"
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

log "Upserting baseline categories..."
CAT_UNIVERSITY_ID=$(upsert_single "categories" \
  "/items/categories?filter%5Bslug%5D%5B_eq%5D=university-news&fields=id,slug&limit=1" \
  '{"name":"Новини університету","nameEn":"University news","slug":"university-news"}' \
  '{"name":"Новини університету","nameEn":"University news"}')

CAT_SCIENCE_ID=$(upsert_single "categories" \
  "/items/categories?filter%5Bslug%5D%5B_eq%5D=science-and-research&fields=id,slug&limit=1" \
  '{"name":"Наука і дослідження","nameEn":"Science and research","slug":"science-and-research"}' \
  '{"name":"Наука і дослідження","nameEn":"Science and research"}')

log "Upserting partners..."
# The four organisations the client listed. No logo files were supplied, so the partner
# cards fall back to the name — an editor can upload logos later.
upsert_single "partners" \
  "/items/partners?filter%5Bslug%5D%5B_eq%5D=mon&fields=id,slug&limit=1" \
  "{\"status\":\"published\",\"name\":\"Міністерство освіти і науки України\",\"nameEn\":\"Ministry of Education and Science of Ukraine\",\"slug\":\"mon\",\"description\":\"Засновник університету.\",\"descriptionEn\":\"The founding body of the university.\",\"website\":\"https://mon.gov.ua\",\"country\":\"Україна\",\"countryEn\":\"Ukraine\"}" \
  "{\"status\":\"published\",\"name\":\"Міністерство освіти і науки України\",\"nameEn\":\"Ministry of Education and Science of Ukraine\",\"description\":\"Засновник університету.\",\"descriptionEn\":\"The founding body of the university.\",\"website\":\"https://mon.gov.ua\",\"country\":\"Україна\",\"countryEn\":\"Ukraine\"}" \
  >/dev/null

upsert_single "partners" \
  "/items/partners?filter%5Bslug%5D%5B_eq%5D=kharkiv-education-department&fields=id,slug&limit=1" \
  "{\"status\":\"published\",\"name\":\"Департамент освіти і науки Харківської обласної державної адміністрації\",\"nameEn\":\"Department of Education and Science of the Kharkiv Regional State Administration\",\"slug\":\"kharkiv-education-department\",\"description\":\"Регіональний партнер у сфері освіти.\",\"descriptionEn\":\"Regional partner in education.\",\"website\":\"\",\"country\":\"Україна\",\"countryEn\":\"Ukraine\"}" \
  "{\"status\":\"published\",\"name\":\"Департамент освіти і науки Харківської обласної державної адміністрації\",\"nameEn\":\"Department of Education and Science of the Kharkiv Regional State Administration\",\"description\":\"Регіональний партнер у сфері освіти.\",\"descriptionEn\":\"Regional partner in education.\",\"website\":\"\",\"country\":\"Україна\",\"countryEn\":\"Ukraine\"}" \
  >/dev/null

upsert_single "partners" \
  "/items/partners?filter%5Bslug%5D%5B_eq%5D=government-contact-centre&fields=id,slug&limit=1" \
  "{\"status\":\"published\",\"name\":\"Урядовий контактний центр\",\"nameEn\":\"Government Contact Centre\",\"slug\":\"government-contact-centre\",\"description\":\"Урядова гаряча лінія 1545.\",\"descriptionEn\":\"The 1545 government hotline.\",\"website\":\"https://1545.gov.ua\",\"country\":\"Україна\",\"countryEn\":\"Ukraine\"}" \
  "{\"status\":\"published\",\"name\":\"Урядовий контактний центр\",\"nameEn\":\"Government Contact Centre\",\"description\":\"Урядова гаряча лінія 1545.\",\"descriptionEn\":\"The 1545 government hotline.\",\"website\":\"https://1545.gov.ua\",\"country\":\"Україна\",\"countryEn\":\"Ukraine\"}" \
  >/dev/null

upsert_single "partners" \
  "/items/partners?filter%5Bslug%5D%5B_eq%5D=skovoroda-hub&fields=id,slug&limit=1" \
  "{\"status\":\"published\",\"name\":\"Сковорода-хаб\",\"nameEn\":\"Skovoroda Hub\",\"slug\":\"skovoroda-hub\",\"description\":\"Освітній хаб університету.\",\"descriptionEn\":\"The university education hub.\",\"website\":\"https://sites.google.com/hnpu.edu.ua/khnpu-eduhub\",\"country\":\"Україна\",\"countryEn\":\"Ukraine\"}" \
  "{\"status\":\"published\",\"name\":\"Сковорода-хаб\",\"nameEn\":\"Skovoroda Hub\",\"description\":\"Освітній хаб університету.\",\"descriptionEn\":\"The university education hub.\",\"website\":\"https://sites.google.com/hnpu.edu.ua/khnpu-eduhub\",\"country\":\"Україна\",\"countryEn\":\"Ukraine\"}" \
  >/dev/null

log "Seed complete."
