#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root on the VPS." >&2
    exit 1
fi

APP_DIR="${APP_DIR:-/opt/cryptosentinelv2/app}"
SERVICE_USER="${SERVICE_USER:-cryptosentinelv2}"
SERVICE_GROUP="${SERVICE_GROUP:-cryptosentinelv2}"

if [ "$(pwd)" != "$APP_DIR" ]; then
    echo "Run this script from $APP_DIR after cloning or releasing the repository there." >&2
    echo "Current directory: $(pwd)" >&2
    exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip nodejs npm nginx curl sqlite3 chrony ca-certificates

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    adduser --system --home "/home/$SERVICE_USER" --group "$SERVICE_USER"
fi

mkdir -p /etc/cryptosentinelv2 /var/backups/cryptosentinelv2 "/home/$SERVICE_USER/.twak" "$APP_DIR/logs"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$APP_DIR" /var/backups/cryptosentinelv2 "/home/$SERVICE_USER/.twak"
chmod 700 /etc/cryptosentinelv2 /var/backups/cryptosentinelv2 "/home/$SERVICE_USER/.twak"

if [ ! -f /etc/cryptosentinelv2/backend.env ]; then
    install -m 600 -o root -g root /dev/null /etc/cryptosentinelv2/backend.env
    cat >/etc/cryptosentinelv2/backend.env <<'EOF'
# Fill on the VPS only. Do not commit this file.
# API_READ_TOKEN=
# API_ADMIN_TOKEN=
# API_DEVICE_TOKEN=
# API_ALERTS_TOKEN=
# CMC_API_KEY=
# ANTHROPIC_API_KEY=
# TWAK_ACCESS_ID=
# TWAK_HMAC_SECRET=
# TWAK_WALLET_PASSWORD=
# WALLET_ENCRYPTED_PRIVATE_KEY_PATH=
# WALLET_KEY_PASSPHRASE_ENV=
# FCM_CREDENTIALS_PATH=
# TATUM_RPC_API_KEY=
EOF
    chmod 600 /etc/cryptosentinelv2/backend.env
fi

if [ ! -f "$APP_DIR/configs/instance.yaml" ]; then
    cp "$APP_DIR/configs/instance.example.yaml" "$APP_DIR/configs/instance.yaml"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$APP_DIR/configs/instance.yaml"
    chmod 600 "$APP_DIR/configs/instance.yaml"
fi

runuser -u "$SERVICE_USER" -- python3 -m venv "$APP_DIR/backend/.venv"
runuser -u "$SERVICE_USER" -- "$APP_DIR/backend/.venv/bin/python" -m pip install --upgrade pip
runuser -u "$SERVICE_USER" -- "$APP_DIR/backend/.venv/bin/python" -m pip install -r "$APP_DIR/backend/requirements.txt"

runuser -u "$SERVICE_USER" -- npm ci
runuser -u "$SERVICE_USER" -- npm run dashboard:build

chmod 755 "$APP_DIR/deploy/scripts/backup_sqlite.sh" "$APP_DIR/deploy/scripts/healthcheck.sh"

cp "$APP_DIR/deploy/systemd/cryptosentinelv2-backend.service" /etc/systemd/system/
cp "$APP_DIR/deploy/systemd/cryptosentinelv2-backup.service" /etc/systemd/system/
cp "$APP_DIR/deploy/systemd/cryptosentinelv2-backup.timer" /etc/systemd/system/
cp "$APP_DIR/deploy/systemd/cryptosentinelv2-healthcheck.service" /etc/systemd/system/
cp "$APP_DIR/deploy/systemd/cryptosentinelv2-healthcheck.timer" /etc/systemd/system/
cp "$APP_DIR/deploy/nginx/cryptosentinelv2.conf" /etc/nginx/sites-available/cryptosentinelv2.conf
ln -sf /etc/nginx/sites-available/cryptosentinelv2.conf /etc/nginx/sites-enabled/cryptosentinelv2.conf

systemctl daemon-reload
systemctl enable chrony nginx cryptosentinelv2-backend.service cryptosentinelv2-backup.timer cryptosentinelv2-healthcheck.timer

nginx -t
systemctl restart chrony
systemctl restart cryptosentinelv2-backend.service
systemctl restart cryptosentinelv2-backup.timer cryptosentinelv2-healthcheck.timer
systemctl reload nginx

echo "Install complete. Configure DNS/TLS and fill /etc/cryptosentinelv2/backend.env before live operation."
