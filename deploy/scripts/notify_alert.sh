#!/usr/bin/env bash
# Deliver one operational alert over every channel that is configured.
#
# Usage: notify_alert.sh <title> <body> [source]
#
# Two channels, on purpose:
#
#   FCM       the normal one. Needs the backend to be up AND the device_tokens table
#             to be readable - which is exactly what breaks in the incidents these
#             alerts exist for. On 2026-08-18 that table was the corrupt one, so the
#             push had no way out (NOTE/54).
#   Telegram  the emergency one. Talks to api.telegram.org directly: no backend, no
#             database, no tokens table. It keeps working when the rest does not.
#
# Exit 0 if AT LEAST ONE channel accepted the message: the goal is that the alert
# reaches a human, not that every channel succeeds. Exit 1 only if nothing got out,
# so the caller (and systemd) can still report a real failure.
#
# Secrets arrive from the environment (EnvironmentFile in the unit) and are never
# printed, not even inside an error message: curl runs without --show-error so a
# failing request cannot echo the URL, which carries the bot token.
set -uo pipefail

TITLE="${1:-Allarme}"
BODY="${2:-}"
SOURCE="${3:-system}"
API_URL="${API_URL:-http://127.0.0.1:8000/api/v1/notifications/send}"

delivered=0
attempted=0

# --- channel 1: FCM through the backend --------------------------------------
if [ -n "${API_ADMIN_TOKEN:-}" ]; then
    attempted=$((attempted + 1))
    if command -v python3 >/dev/null 2>&1; then
        payload="$(TITLE="$TITLE" BODY="$BODY" SOURCE="$SOURCE" python3 -c '
import json, os
print(json.dumps({
    "title": os.environ["TITLE"][:120],
    "body": os.environ["BODY"][:500],
    "severity": "critical",
    "data": {"source": os.environ["SOURCE"]},
}))')"
    else
        payload="{\"title\":\"$TITLE\",\"body\":\"alert\",\"severity\":\"critical\",\"data\":{\"source\":\"$SOURCE\"}}"
    fi
    if curl --fail --silent --max-time 10 -o /dev/null \
        -X POST "$API_URL" \
        -H "Authorization: Bearer $API_ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$payload"; then
        delivered=$((delivered + 1))
    else
        echo "notify_alert: FCM delivery failed" >&2
    fi
fi

# --- channel 2: Telegram, independent from backend and database ---------------
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    attempted=$((attempted + 1))
    if curl --fail --silent --max-time 15 -o /dev/null \
        -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=[CryptoSentinelV2] ${TITLE}

${BODY}"; then
        delivered=$((delivered + 1))
    else
        # No --show-error above: an error line could echo the URL, token included.
        echo "notify_alert: Telegram delivery failed" >&2
    fi
fi

if [ "$attempted" -eq 0 ]; then
    echo "notify_alert: no channel configured, alert not delivered" >&2
    exit 1
fi
if [ "$delivered" -eq 0 ]; then
    echo "notify_alert: every channel failed ($attempted attempted)" >&2
    exit 1
fi
exit 0
