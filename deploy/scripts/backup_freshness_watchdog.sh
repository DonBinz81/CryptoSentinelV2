#!/usr/bin/env bash
# Detect the backup pipeline going silent, not just failing.
#
# backup_alert.sh only fires through OnFailure=: an active failure (backup could
# not be produced) or an integrity check that comes back bad. Neither covers the
# timer itself stopping - disabled, removed, or a run that hangs forever without
# ever exiting - because none of those produce a failure event. NOTE/54 SS10 named
# this gap on 2026-08-18 and left it open on purpose, pending this watchdog.
#
# Two independent signals, checked every run:
#   1. cryptosentinelv2-backup.timer is not active: the schedule itself is gone.
#   2. last_result.json is older than the expected 6h cadence by a wide margin:
#      catches a hung run, or a result file that stopped updating for any other
#      reason even while the timer looks fine.
#
# Delivery goes through notify_alert.sh (FCM + Telegram), same as db_watchdog.sh.
set -uo pipefail

TIMER="${TIMER:-cryptosentinelv2-backup.timer}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/cryptosentinelv2}"
result_file="$BACKUP_DIR/last_result.json"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-13}"
STATE_DIR="${STATE_DIRECTORY:-/var/lib/cryptosentinelv2-backup-freshness}"
THROTTLE_SECONDS="${THROTTLE_SECONDS:-21600}"
here="$(dirname "$0")"

findings=""

# --- signal 1: the timer itself ----------------------------------------------
if [ "$(systemctl is-active "$TIMER" 2>/dev/null)" != "active" ]; then
    findings="il timer $TIMER non e' attivo"
fi

# --- signal 2: age of the last result -----------------------------------------
if [ ! -r "$result_file" ]; then
    findings="${findings:+$findings; }last_result.json assente"
elif command -v python3 >/dev/null 2>&1; then
    age_hours="$(python3 - "$result_file" <<'PY'
import json
import sys
from datetime import datetime, timezone

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        result = json.load(handle)
    stamp = datetime.strptime(result.get("timestamp", ""), "%Y%m%dT%H%M%SZ")
    stamp = stamp.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - stamp).total_seconds() / 3600
    print(int(age))
except Exception:
    print(-1)
PY
)"
    if [ "$age_hours" = "-1" ]; then
        findings="${findings:+$findings; }timestamp in last_result.json illeggibile"
    elif [ "$age_hours" -gt "$MAX_AGE_HOURS" ]; then
        findings="${findings:+$findings; }ultimo esito vecchio di ${age_hours}h (atteso ogni 6h)"
    fi
fi
# Without python3 signal 2 is skipped; signal 1 alone still catches the main case.

if [ -z "$findings" ]; then
    exit 0
fi

echo "backup_freshness_watchdog: $findings" >&2

# --- throttle: one alert per expected cycle, not one per hourly run ----------
mkdir -p "$STATE_DIR" 2>/dev/null || true
stamp_file="$STATE_DIR/last_alert_epoch"
now="$(date +%s)"
if [ -r "$stamp_file" ]; then
    last="$(cat "$stamp_file" 2>/dev/null || echo 0)"
    if [ $((now - ${last:-0})) -lt "$THROTTLE_SECONDS" ]; then
        exit 0
    fi
fi

body="Il backup periodico sembra fermo: ${findings}. Nessun fallimento e' stato segnalato: il problema e' nel timer stesso o nel processo, non nell'ultima esecuzione registrata."

if "$here/notify_alert.sh" "Backup silenzioso" "$body" backup_freshness; then
    echo "$now" > "$stamp_file"
else
    echo "backup_freshness_watchdog: alert delivery failed" >&2
    exit 1
fi
