#!/bin/sh
# Compose sets API_UPSTREAM so nginx proxies /api/. In Kubernetes the Ingress routes /api to the
# api Service and API_UPSTREAM stays empty; then /api/ answers 404 instead of serving index.html.
set -eu
if [ -z "${API_UPSTREAM:-}" ]; then
    printf 'location /api/ {\n    return 404;\n}\n' > /etc/nginx/conf.d/api-proxy.locations
    echo "$0: API_UPSTREAM is empty, /api/ is not proxied"
fi
