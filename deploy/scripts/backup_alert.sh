#!/usr/bin/env bash
# Send an alert when a backup run fails.
#
# Triggered by OnFailure= on cryptosentinelv2-backup.service, so it runs only when
# the backup did not complete. Two cases reach here, and the second one is the
# important one:
#   - status "failed" / "db_missing"  the backup could not be produced at all
#   - status "integrity_failed"       the copy of the database is unreadable, which
#                                     means the live database is very likely corrupt
#
# Before this existed, both failures were silent: on 2026-08-18 the database was
# corrupt for three hours and the only trace was a 0-byte file nobody looked at
# (NOTE/54).
#
# Delivery is delegated to notify_alert.sh, which fans the message out to every
# configured channel (FCM and, since 2026-08-19, Telegram as the emergency route
# that does not depend on the database).
set -uo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/cryptosentinelv2}"
result_file="$BACKUP_DIR/last_result.json"
here="$(dirname "$0")"

title="Backup fallito"
body="Il backup periodico non e' stato prodotto. Controllare last_result.json sulla VPS."

# Read the outcome with python3 so that the integrity message, which contains
# quotes and parentheses, survives intact. Without python3 the fixed message above
# still goes out: an alert with less detail is better than no alert.
if command -v python3 >/dev/null 2>&1 && [ -r "$result_file" ]; then
    parsed="$(python3 - "$result_file" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        result = json.load(handle)
except Exception:
    result = {}

status = str(result.get("status", "unknown"))
integrity = str(result.get("integrity", "unknown"))
timestamp = str(result.get("timestamp", ""))

if status == "integrity_failed":
    title = "Database illeggibile"
    body = (
        "La verifica del backup non passa: il database di produzione e' "
        "probabilmente corrotto. Copia conservata e marcata INTEGRITY_FAILED. "
        f"Esito: {integrity}"
    )
else:
    title = "Backup fallito"
    body = (
        "Il backup periodico non e' stato prodotto. Nessun artefatto pubblicato. "
        f"Stato: {status}, verifica: {integrity}"
    )

if timestamp:
    body = f"{body} ({timestamp})"

# One field per line: the caller reads title from the first, body from the second.
print(title[:120])
print(body[:500].replace("\n", " "))
PY
)"
    if [ -n "$parsed" ]; then
        title="$(printf '%s\n' "$parsed" | sed -n '1p')"
        body="$(printf '%s\n' "$parsed" | sed -n '2p')"
    fi
fi

exec "$here/notify_alert.sh" "$title" "$body" backup
