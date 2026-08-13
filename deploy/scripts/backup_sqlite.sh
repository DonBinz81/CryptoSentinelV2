#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/cryptosentinel/app}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/cryptosentinel}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_PATH="${DB_PATH:-$APP_DIR/backend/local.db}"
TWAK_HOME="${TWAK_HOME:-/home/cryptosentinel/.twak}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target_dir="$BACKUP_DIR/$timestamp"
mkdir -p "$target_dir"
chmod 700 "$BACKUP_DIR" "$target_dir"

if [ -f "$DB_PATH" ]; then
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "$DB_PATH" ".backup '$target_dir/local.db'"
    else
        cp -p "$DB_PATH" "$target_dir/local.db"
    fi
fi

# Export only versioned non-secret defaults. Local instance config and env files
# remain outside the backup artifact produced by this repo script.
if [ -d "$APP_DIR/configs" ]; then
    mkdir -p "$target_dir/configs"
    find "$APP_DIR/configs" -maxdepth 1 -type f -name '*.yaml' ! -name 'instance.yaml' \
        -exec cp -p {} "$target_dir/configs/" \;
fi

# Preserve encrypted TWAK headless state if present. Do not print contained paths
# or file names in normal output; this archive is stored with 0600 permissions.
if [ -d "$TWAK_HOME" ]; then
    tar -C "$TWAK_HOME" -czf "$target_dir/twak-state.tar.gz" .
    chmod 600 "$target_dir/twak-state.tar.gz"
fi

find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" -exec rm -rf {} +
