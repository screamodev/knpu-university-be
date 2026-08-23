# Hestia nginx templates for hnpu.edu.ua

Two proxy vhosts: `hnpu.edu.ua` → Nuxt on `127.0.0.1:3000`, `admin.hnpu.edu.ua` → Directus
on `127.0.0.1:8055`. Both ports are published by the `docker-compose.host.yml` overlay in
each repo, on loopback only.

Install as root on the Hestia server:

```bash
bash ~/knpu-university-be/deploy/hestia/install-templates.sh
```

The script figures out the rest:

- **where the templates go** — `data/templates/web/nginx/` when nginx is a proxy in front
  of apache (`PROXY_SYSTEM=nginx`), `data/templates/web/nginx/php-fpm/` when nginx is the
  web server itself (`WEB_SYSTEM=nginx`), rewriting `%proxy_port%` → `%web_port%` for the
  second case;
- **`http2`** — `http2 on;` for nginx ≥ 1.25.1, `listen … ssl http2;` for older builds;
- **`$connection_upgrade`** — adds the map to `/etc/nginx/conf.d/` if nothing defines it;
- **assignment** — `v-change-web-domain-proxy-tpl` / `v-change-web-domain-tpl`, then
  `nginx -t` and a restart. `--no-assign` copies the files and stops.

Existing templates of the same name are backed up next to them before being overwritten.

Both `.tpl` files serve `/.well-known/acme-challenge/` from `public_html` **before** the
redirect to HTTPS — without that `v-add-letsencrypt-domain` fails, because the ACME server
gets a 301 to a port it does not check.

Full context: [`MIGRATION-TO-HNPU-DOMAIN.md`](../../MIGRATION-TO-HNPU-DOMAIN.md), stage 1.5.
