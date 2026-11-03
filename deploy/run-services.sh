#!/bin/sh
set -eu
gunicorn 'production:create_app()' --bind 127.0.0.1:8765 --workers 1 --threads 4 --timeout 60 --limit-request-line 4096 --limit-request-fields 40 --limit-request-field_size 8190 --access-logfile /dev/null --error-logfile - &
app_pid=$!
proxy_config=/etc/caddy/Caddyfile
if [ "${OBSIDIAN_SHARED_GATEWAY:-0}" = "1" ]; then
    proxy_config=/etc/caddy/Caddyfile.shared
fi
caddy run --config "$proxy_config" --adapter caddyfile &
proxy_pid=$!
trap 'kill "$app_pid" "$proxy_pid" 2>/dev/null || true' EXIT TERM INT
while kill -0 "$app_pid" 2>/dev/null && kill -0 "$proxy_pid" 2>/dev/null; do
    sleep 2
done
exit 1
