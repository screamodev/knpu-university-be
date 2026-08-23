# admin.hnpu.edu.ua — plain HTTP.
#
# No hardcoded redirect to HTTPS here: before the certificate exists there is no vhost on
# 443 for this name, so the default server answers instead and Let's Encrypt sees a
# redirect loop. Hestia's own force-SSL snippet is included below and takes over once
# v-add-web-domain-ssl-force is on.
#
# Ports are written for a Hestia *proxy* template; install-templates.sh rewrites
# %proxy_port% to %web_port% when nginx is the web server itself.
server {
    listen      %ip%:%proxy_port%;
    server_name %domain_idn% %alias_idn%;

    # Let's Encrypt http-01: Hestia drops the token into public_html, so it is served from
    # disk and never reaches the app.
    location ^~ /.well-known/acme-challenge/ {
        root         %home%/%user%/web/%domain%/public_html;
        default_type text/plain;
        try_files    $uri =404;
    }

    # Written by v-add-web-domain-ssl-force; absent until then, and the trailing * keeps
    # nginx quiet about that.
    include %home%/%user%/conf/web/%domain%/nginx.forcessl.conf*;

    client_max_body_size 512m;

    location / {
        proxy_pass http://127.0.0.1:8055;
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
