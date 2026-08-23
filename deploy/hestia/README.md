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

Neither `.tpl` redirects to HTTPS on its own. Before a certificate exists there is no vhost
on 443 for the name, the default server answers instead, and `v-add-letsencrypt-domain`
dies with "Redirect loop detected". The order is: install templates → issue the certificate
→ `v-add-web-domain-ssl-force`, which writes the `nginx.forcessl.conf` the templates
include. Both halves serve `/.well-known/acme-challenge/` from `public_html`, so renewals
work with force-SSL on (ACME follows the redirect to 443).

Full context: [`MIGRATION-TO-HNPU-DOMAIN.md`](../../MIGRATION-TO-HNPU-DOMAIN.md), stage 1.5.
