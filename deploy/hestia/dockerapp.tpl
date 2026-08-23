# hnpu.edu.ua — plain HTTP.
#
# No hardcoded redirect to HTTPS here: before the certificate exists there is no vhost on
# 443 for this name, so the default server answers instead and Let's Encrypt sees a
# redirect loop. Hestia's own force-SSL snippet is included below and takes over once
# v-add-web-domain-ssl-force is on.
#
# Ports are written for a Hestia *proxy* template; install-templates.sh rewrites
# %proxy_port% to %web_port% when nginx is the web server itself.
# ACME is not handled here: Hestia writes conf/web/<domain>/nginx.conf_letsencrypt with a
# regex location that returns the token response, and the `include … nginx.conf_*` at the
# bottom pulls it in. A `location ^~ /.well-known/acme-challenge/` of our own would take
# precedence over that regex and break issuance.
server {
    listen      %ip%:%proxy_port%;
    server_name %domain_idn% %alias_idn%;

    # Written by v-add-web-domain-ssl-force; absent until then, and the trailing * keeps
    # nginx quiet about that.
    include %home%/%user%/conf/web/%domain%/nginx.forcessl.conf*;

    client_max_body_size 512m;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        $connection_upgrade;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }

    include %home%/%user%/conf/web/%domain%/nginx.conf_*;
}
