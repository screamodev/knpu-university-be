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

Two things the templates deliberately leave alone:

- **The HTTPS redirect.** Neither `.tpl` redirects on its own — before a certificate exists
  there is no vhost on 443 for the name, the default server answers instead, and
  `v-add-letsencrypt-domain` dies with "Redirect loop detected". Order: install templates →
  issue the certificate → `v-add-web-domain-ssl-force`, which writes the
  `nginx.forcessl.conf` the templates include.
- **The ACME challenge.** Hestia does not drop a token on disk; it writes
  `conf/web/<domain>/nginx.conf_letsencrypt`, a regex location that returns the response
  inline, and the `include … nginx.conf_*` at the bottom of every template pulls it in. A
  `location ^~ /.well-known/acme-challenge/` of our own would win over that regex (a `^~`
  prefix beats regex) and break issuance. Keep that include, and add no acme location.

Full context: [`MIGRATION-TO-HNPU-DOMAIN.md`](../../MIGRATION-TO-HNPU-DOMAIN.md), stage 1.5.
