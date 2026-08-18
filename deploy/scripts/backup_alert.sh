#!/usr/bin/env bash
# Send a push alert when a backup run fails.
#
# Triggered by OnFailure= on cryptosentinelv2-backup.service, so it runs only
# when the backup did not complete. Two cases reach here, and the second one is
# the important one:
#   - status "failed"           the backup could not be produced at all
#   - status "integrity_failed" the copy of the database is unreadable, which
#                               means the live database is very likely corrupt
#
# Before this existed, both failures were silent: on 2026-08-18 the database was
# corrupt for three hours and the only trace was a 0-byte file nobody looked at
# (NOTE/54).
#
# The admin token arrives from the environment (EnvironmentFile in the unit) and
# is never printed, logged or included in any message.
set -uo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/cryptosentinelv2}"
API_URL="${API_URL:-http://127.0.0.1:8000/api/v1/notifications/send}"
result_file="$BACKUP_DIR/last_result.json"

if [ -z "${API_ADMIN_TOKEN:-}" ]; then
    echo "backup_alert: no admin token in the environment, cannot notify" >&2
    exit 1
fi

# Build the payload with python3 so that the integrity message, which contains
# quotes and parentheses, is escaped properly. Without python3 fall back to a
# fixed message: an alert with less detail is still an alert.
if command -v python3 >/dev/null 2>&1 && [ -r "$result_file" ]; then
    payload="$(python3 - "$result_file" <<'PY'
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
        "Il backup periodico non e' stato prodotto. Nessun artefatto "
        f"pubblicato. Stato: {status}, verifica: {integrity}"
    )

if timestamp:
    body = f"{body} ({timestamp})"

print(json.dumps({
    "title": title[:120],
    "body": body[:500],
    "severity": "critical",
    "data": {"source": "backup", "status": status},
}))
PY
)"
else
    payload='{"title":"Backup fallito","body":"Il backup periodico non e stato prodotto. Controllare last_result.json sulla VPS.","severity":"critical","data":{"source":"backup"}}'
fi

curl --fail --silent --show-error --max-time 10 \
    -X POST "$API_URL" \
    -H "Authorization: Bearer $API_ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$payload" >/dev/null
