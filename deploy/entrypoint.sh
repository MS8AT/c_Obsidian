#!/bin/sh
set -eu
mkdir -p /state /vault /data/caddy /config/caddy
# These are dedicated volumes for this application, never the workbook root.
if [ -z "$(ls -A /vault)" ]; then
    cp -R /app/demo-vault/. /vault/
fi
chown -R app:app /state /vault /data /config
if [ ! -s /state/accounts.json ]; then
    echo 'Account not provisioned; HTTPS service will stay stopped.' >&2
    echo 'Provision with auth_store.py --state /state --username <name> in a protected TTY.' >&2
    exit 78
fi
exec su -s /bin/sh app -c /app/run-services.sh
