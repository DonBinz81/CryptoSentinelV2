#!/usr/bin/env bash
set -euo pipefail

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health/live}"

curl --fail --silent --show-error --max-time 5 "$HEALTH_URL" >/dev/null
