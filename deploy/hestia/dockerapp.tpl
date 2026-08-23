# hnpu.edu.ua — plain HTTP. Everything except the ACME challenge goes to HTTPS.
#
# Ports are written for a Hestia *proxy* template; install-templates.sh rewrites
# %proxy_port% to %web_port% when nginx is the web server itself.
server {
    listen      %ip%:%proxy_port%;
    server_name %domain_idn% %alias_idn%;

    # Let's Encrypt http-01. Hestia drops the token into public_html, so this has to be
    # served from disk and has to come before the redirect — otherwise
    # v-add-letsencrypt-domain fails on a 301 it cannot follow.
    location ^~ /.well-known/acme-challenge/ {
        root         %home%/%user%/web/%domain%/public_html;
        default_type text/plain;
        try_files    $uri =404;
    }

    location / {
        return 301 https://$host$request_uri;
    }

    include %home%/%user%/conf/web/%domain%/nginx.conf_*;
}
