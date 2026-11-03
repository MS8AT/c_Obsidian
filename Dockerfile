FROM caddy:2-alpine AS proxy
FROM python:3.12-alpine
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && addgroup -S app && adduser -S -G app -u 10001 app
COPY --from=proxy /usr/bin/caddy /usr/bin/caddy
COPY obsidian.py obsidian_core.py auth_store.py production.py openapi.json ./
COPY web ./web
COPY demo-vault ./demo-vault
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY deploy/Caddyfile.shared /etc/caddy/Caddyfile.shared
COPY deploy/entrypoint.sh /entrypoint.sh
COPY deploy/run-services.sh /app/run-services.sh
RUN chmod 755 /entrypoint.sh /app/run-services.sh && mkdir -p /state /vault /data/caddy /config/caddy && chown -R app:app /state /vault /data /config
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OBSIDIAN_VAULT=/vault OBSIDIAN_STATE=/state OBSIDIAN_DOMAIN=obsidian.ms8at.by OBSIDIAN_SECURE=1 XDG_DATA_HOME=/data XDG_CONFIG_HOME=/config
EXPOSE 8080 8443
ENTRYPOINT ["/entrypoint.sh"]
