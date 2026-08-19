#!/usr/bin/env bash
# Detect database trouble while it is happening, instead of six hours later.
#
# On 2026-08-18 the database was corrupt for three hours before anyone noticed
# (NOTE/54). This watchdog runs every minute and looks for the two signatures
# that incident produced, in the order in which they appeared:
#
#   1. orphan file descriptors: the backend holding a deleted -wal/-shm, or two
#      different -wal files at once. This appeared at 09:27:11, twenty seconds
#      BEFORE the first application error.
#   2. corruption errors in the journal: "malformed", "file is not a database",
#      "rolled back". These started at 09:27:38.
#
# The database is never opened, and never even read: only /proc and the journal.
#
# Delivery goes through notify_alert.sh, which fans the alert out to every
# configured channel. Since 2026-08-19 that includes Telegram, which talks to
# api.telegram.org directly: it needs neither the backend nor the database, and so
# it survives the very incident this watchdog exists for. During the 18/08 outage
# the corrupt table was device_tokens - the one FCM needs - so the push had no way
# out; Telegram would have gone through.
set -uo pipefail

SERVICE="${SERVICE:-cryptosentinelv2-backend}"
DB_PATH="${DB_PATH:-/opt/cryptosentinelv2/app/backend/local.db}"
SINCE="${SINCE:--2min}"
STATE_DIR="${STATE_DIRECTORY:-/var/lib/cryptosentinelv2-db-watchdog}"
THROTTLE_SECONDS="${THROTTLE_SECONDS:-1800}"
API_URL="${API_URL:-http://127.0.0.1:8000/api/v1/notifications/send}"
NOTIFY="${NOTIFY:-1}"

# A stopped service has no sidecar files and no fresh log lines: that is not a
# database problem, and the API would be unreachable anyway.
if [ "$(systemctl is-active "$SERVICE")" != "active" ]; then
    exit 0
fi

main_pid="$(systemctl show "$SERVICE" -p MainPID --value)"
findings=""

# --- signature 1: orphan descriptors -----------------------------------------
if [ -n "$main_pid" ] && [ "$main_pid" != "0" ] && [ -d "/proc/$main_pid/fd" ]; then
    fd_list="$(ls -l "/proc/$main_pid/fd" 2>/dev/null | grep "$(basename "$DB_PATH")" || true)"

    deleted_count="$(printf '%s\n' "$fd_list" | grep -c "(deleted)" || true)"
    if [ "${deleted_count:-0}" -gt 0 ]; then
        findings="descrittori orfani sul database ($deleted_count)"
    fi

    # More than one live -wal inode means connections are writing through
    # different journals for the same database.
    wal_inodes="$(printf '%s\n' "$fd_list" | grep -c -- "-wal" || true)"
    if [ "${deleted_count:-0}" -gt 0 ] && [ "${wal_inodes:-0}" -gt 1 ]; then
        findings="$findings, piu di un WAL in uso"
    fi
fi

# A live service in WAL mode must have both sidecars, or neither.
if [ -f "$DB_PATH-wal" ] && [ ! -f "$DB_PATH-shm" ]; then
    findings="${findings:+$findings, }WAL presente senza -shm"
fi

# --- signature 2: corruption errors in the journal ---------------------------
errors="$(journalctl -u "$SERVICE" --since "$SINCE" --no-pager 2>/dev/null \
    | grep -c -E "malformed|file is not a database|transaction has been rolled back" || true)"
if [ "${errors:-0}" -gt 0 ]; then
    findings="${findings:+$findings, }${errors} errori di database nei log"
fi

if [ -z "$findings" ]; then
    exit 0
fi

echo "db_watchdog: $findings" >&2

# --- throttle -----------------------------------------------------------------
# Keep reporting to the journal, but do not send a push every minute for the
# same ongoing incident.
mkdir -p "$STATE_DIR" 2>/dev/null || true
stamp_file="$STATE_DIR/last_alert_epoch"
now="$(date +%s)"
if [ -r "$stamp_file" ]; then
    last="$(cat "$stamp_file" 2>/dev/null || echo 0)"
    if [ $((now - ${last:-0})) -lt "$THROTTLE_SECONDS" ]; then
        exit 0
    fi
fi

if [ "$NOTIFY" != "1" ]; then
    exit 0
fi

body="Anomalia rilevata sul database di produzione: ${findings}. Il backend e' attivo. Verificare prima che peggiori."

if "$(dirname "$0")/notify_alert.sh" "Problema database" "$body" db_watchdog; then
    echo "$now" > "$stamp_file"
else
    # Do not update the stamp: a failed delivery must be retried next minute.
    echo "db_watchdog: alert delivery failed" >&2
    exit 1
fi
