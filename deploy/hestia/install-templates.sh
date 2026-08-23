#!/usr/bin/env bash
#
# Install the Hestia nginx templates that put the two Docker containers behind
# hnpu.edu.ua (Nuxt on 127.0.0.1:3000) and admin.hnpu.edu.ua (Directus on 127.0.0.1:8055),
# then assign them to the domains.
#
# Run as root on the Hestia server:
#
#   bash ~/knpu-university-be/deploy/hestia/install-templates.sh
#   bash ~/knpu-university-be/deploy/hestia/install-templates.sh --user hnpu \
#        --site hnpu.edu.ua --admin admin.hnpu.edu.ua
#   bash ~/knpu-university-be/deploy/hestia/install-templates.sh --no-assign   # copy only
#
# Idempotent: re-run it after editing a template.
set -euo pipefail

HESTIA=${HESTIA:-/usr/local/hestia}
SRC=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

USER_NAME=hnpu
SITE_DOMAIN=hnpu.edu.ua
ADMIN_DOMAIN=admin.hnpu.edu.ua
ASSIGN=1

while [ $# -gt 0 ]; do
    case "$1" in
        --user)      USER_NAME=$2; shift 2 ;;
        --site)      SITE_DOMAIN=$2; shift 2 ;;
        --admin)     ADMIN_DOMAIN=$2; shift 2 ;;
        --no-assign) ASSIGN=0; shift ;;
        -h|--help)   sed -n '2,16p' "$0"; exit 0 ;;
        *)           echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
[ -r "$HESTIA/conf/hestia.conf" ] || { echo "no $HESTIA/conf/hestia.conf — is this the Hestia server?" >&2; exit 1; }

# shellcheck disable=SC1091
. "$HESTIA/conf/hestia.conf"
export PATH="$PATH:$HESTIA/bin"

# Where the template goes and which port placeholders it uses depend on nginx's role:
# a proxy in front of apache uses %proxy_port%, a standalone web server uses %web_port%.
if [ "${PROXY_SYSTEM:-}" = "nginx" ]; then
    MODE=proxy
    DEST=$HESTIA/data/templates/web/nginx
elif [ "${WEB_SYSTEM:-}" = "nginx" ]; then
    MODE=web
    DEST=$HESTIA/data/templates/web/nginx/php-fpm
    [ -d "$DEST" ] || DEST=$HESTIA/data/templates/web/nginx
else
    echo "nginx is neither WEB_SYSTEM ('${WEB_SYSTEM:-}') nor PROXY_SYSTEM ('${PROXY_SYSTEM:-}')." >&2
    echo "These templates assume nginx terminates TLS. Stop and re-read stage 1.5 of the runbook." >&2
    exit 1
fi
echo "nginx role: $MODE   →   $DEST"

# $connection_upgrade keeps keep-alive requests from being told to upgrade; Hestia does not
# always define the map, so add it once in a conf.d snippet.
if ! grep -rqs 'connection_upgrade' /etc/nginx/nginx.conf /etc/nginx/conf.d/ ; then
    cat > /etc/nginx/conf.d/00-connection-upgrade.conf <<'MAP'
# Websocket-aware Connection header for the dockerapp/dockeradmin templates.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
MAP
    echo "added /etc/nginx/conf.d/00-connection-upgrade.conf"
fi

# `http2 on;` is only understood from nginx 1.25.1; older builds want it on the listen line.
NGINX_VER=$(nginx -v 2>&1 | sed 's#.*nginx/##;s#[^0-9.].*##')
HTTP2_OLD=0
if [ -n "$NGINX_VER" ] && [ "$(printf '%s\n1.25.1\n' "$NGINX_VER" | sort -V | head -1)" = "$NGINX_VER" ] \
   && [ "$NGINX_VER" != "1.25.1" ]; then
    HTTP2_OLD=1
fi
echo "nginx $NGINX_VER (http2 on listen line: $HTTP2_OLD)"

install -d -m 755 "$DEST"
for f in dockerapp.tpl dockerapp.stpl dockeradmin.tpl dockeradmin.stpl; do
    out=$DEST/$f
    [ -f "$out" ] && cp -a "$out" "$out.bak.$(date +%Y%m%d%H%M%S)"
    sed_args=()
    if [ "$MODE" = "web" ]; then
        sed_args+=(-e 's/%proxy_port%/%web_port%/g' -e 's/%proxy_ssl_port%/%web_ssl_port%/g')
    fi
    if [ "$HTTP2_OLD" = "1" ]; then
        sed_args+=(-e '/^ *http2 *on;$/d' -e 's/\(listen .*ssl\);/\1 http2;/')
    fi
    if [ ${#sed_args[@]} -gt 0 ]; then sed "${sed_args[@]}" "$SRC/$f" > "$out"; else cp "$SRC/$f" "$out"; fi
    chmod 644 "$out"
    echo "installed $out"
done

if [ "$ASSIGN" = "1" ]; then
    if [ "$MODE" = "proxy" ]; then
        # Enable the proxy first if the domain has none yet; the second call is what
        # switches an already-proxied domain over. Extensions are left at the Hestia
        # default — these templates serve nothing from disk, so they are unused.
        v-add-web-domain-proxy "$USER_NAME" "$SITE_DOMAIN"  dockerapp   2>/dev/null || true
        v-add-web-domain-proxy "$USER_NAME" "$ADMIN_DOMAIN" dockeradmin 2>/dev/null || true
        v-change-web-domain-proxy-tpl "$USER_NAME" "$SITE_DOMAIN"  dockerapp
        v-change-web-domain-proxy-tpl "$USER_NAME" "$ADMIN_DOMAIN" dockeradmin
    else
        v-change-web-domain-tpl "$USER_NAME" "$SITE_DOMAIN"  dockerapp   'no'
        v-change-web-domain-tpl "$USER_NAME" "$ADMIN_DOMAIN" dockeradmin 'no'
    fi
    echo "templates assigned to $SITE_DOMAIN and $ADMIN_DOMAIN"
fi

nginx -t
v-restart-service nginx || systemctl reload nginx
echo "done"
