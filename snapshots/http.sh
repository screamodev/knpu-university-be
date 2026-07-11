#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────────
# Shared HTTP helpers for Directus bootstrap scripts.
#
# The official directus/directus image ships BusyBox wget (GET/POST only) and
# no curl. Node is available, so we use fetch for all methods including PATCH,
# DELETE, and multipart uploads.
# ──────────────────────────────────────────────────────────────────────────────

http_ok() {
  # Usage: http_ok URL — exit 0 on HTTP 2xx, else 1.
  HTTP_URL="$1" node <<'NODE'
fetch(process.env.HTTP_URL)
  .then((res) => process.exit(res.ok ? 0 : 1))
  .catch(() => process.exit(1));
NODE
}

http_json() {
  # Usage: http_json METHOD URL [JSON_BODY] [BEARER_TOKEN]
  # Prints response body to stdout. Exit 0 on network success (any HTTP status).
  HTTP_METHOD="$1" HTTP_URL="$2" HTTP_BODY="${3-}" HTTP_TOKEN="${4-}" node <<'NODE'
const method = process.env.HTTP_METHOD;
const url = process.env.HTTP_URL;
const body = process.env.HTTP_BODY || undefined;
const token = process.env.HTTP_TOKEN || undefined;
const headers = {};

if (token) {
  headers.Authorization = `Bearer ${token}`;
}

if (body !== undefined && body !== "") {
  headers["Content-Type"] = "application/json";
}

fetch(url, { method, headers, body: body || undefined })
  .then(async (res) => {
    process.stdout.write(await res.text());
  })
  .catch((err) => {
    console.error(String(err));
    process.exit(1);
  });
NODE
}

http_upload() {
  # Usage: http_upload URL FILE_PATH FILENAME BEARER_TOKEN
  HTTP_URL="$1" HTTP_FILE="$2" HTTP_NAME="$3" HTTP_TOKEN="$4" node <<'NODE'
const fs = require("fs");
const url = process.env.HTTP_URL;
const filePath = process.env.HTTP_FILE;
const fileName = process.env.HTTP_NAME;
const token = process.env.HTTP_TOKEN;
const buf = fs.readFileSync(filePath);
const form = new FormData();

form.append("file", new Blob([buf]), fileName);

fetch(url, {
  method: "POST",
  headers: { Authorization: `Bearer ${token}` },
  body: form,
})
  .then(async (res) => {
    process.stdout.write(await res.text());
  })
  .catch((err) => {
    console.error(String(err));
    process.exit(1);
  });
NODE
}
