#!/bin/sh

set -e

: "${GRID_UPSTREAM:=127.0.0.1:4444}"

GRID_UPSTREAM="${GRID_UPSTREAM#http://}"
GRID_UPSTREAM="${GRID_UPSTREAM#https://}"
export GRID_UPSTREAM

envsubst '${GRID_UPSTREAM}' \
    < /etc/nginx/nginx.conf.template \
    > /etc/nginx/sites-available/default

echo "[entrypoint] nginx /session/ -> Grid Hub (WebDriver + per-session VNC) at ${GRID_UPSTREAM}"
echo "[entrypoint] nginx /vnc/     -> vendored noVNC static client (/usr/share/novnc)"
echo "[entrypoint] app   -> SELENIUM_REMOTE_URL=${SELENIUM_REMOTE_URL:-<unset>}"

nginx -t

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf