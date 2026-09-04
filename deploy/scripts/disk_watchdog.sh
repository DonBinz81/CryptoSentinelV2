#!/usr/bin/env bash
# Warn before the disk fills up, because a full disk corrupts the database.
#
# On 2026-09-04 the disk reached 97% - about a day and a half from full - and
# nothing rang. It was found only because someone asked to look deeper. With
# SQLite a full disk means failed writes, so this is not a housekeeping alert:
# it is the fifth corruption arriving on its own, without anyone mistyping a
# command (NOTE/112).
#
# Two levels, because the two situations need different reactions:
#   WARN_PCT      there is time to clean up at leisure
#   CRITICAL_PCT  act now
#
# The alert also carries an estimate of the days left, computed from how the
# free space has ACTUALLY moved on this machine rather than from a model: the
# script keeps a small history of readings and compares against one at least
# MIN_TREND_HOURS old. A percentage says nothing about urgency; "about 6 days"
# does.
set -uo pipefail

MOUNT="${MOUNT:-/}"
CONFIG_FILE="${CONFIG_FILE:-/opt/cryptosentinelv2/app/configs/risk.yaml}"

# Thresholds live in configs/risk.yaml (section `monitoring`), not here: the
# alert and anything that displays disk health must read the same numbers. A
# panel showing green while the alert is firing is worse than either alone.
# Falls back to the defaults below when the file is missing or the value is not
# a plain integer - a malformed config must not silence the alert.
read_threshold() {
    local key="$1" fallback="$2" value=""
    if [ -r "$CONFIG_FILE" ]; then
        value="$(awk -v k="$key:" '$1 == k { print $2; exit }' "$CONFIG_FILE" 2>/dev/null)"
    fi
    case "$value" in
        ''|*[!0-9]*) echo "$fallback" ;;
        *) echo "$value" ;;
    esac
}

WARN_PCT="${WARN_PCT:-$(read_threshold disk_warn_pct 85)}"
CRITICAL_PCT="${CRITICAL_PCT:-$(read_threshold disk_critical_pct 92)}"
STATE_DIR="${STATE_DIRECTORY:-/var/lib/cryptosentinelv2-disk-watchdog}"
# A warning can wait a day; a critical one has to keep insisting.
WARN_THROTTLE_SECONDS="${WARN_THROTTLE_SECONDS:-86400}"
CRITICAL_THROTTLE_SECONDS="${CRITICAL_THROTTLE_SECONDS:-21600}"
MIN_TREND_HOURS="${MIN_TREND_HOURS:-12}"
HISTORY_MAX_LINES="${HISTORY_MAX_LINES:-400}"
here="$(dirname "$0")"

mkdir -p "$STATE_DIR" 2>/dev/null || true
history_file="$STATE_DIR/free_bytes_history"
stamp_file="$STATE_DIR/last_alert_epoch"
level_file="$STATE_DIR/last_alert_level"

now="$(date +%s)"

# --- reading -----------------------------------------------------------------
# df in POSIX mode: stable columns regardless of locale and long device names.
read -r _ total_kb used_kb _ <<< "$(df -P -k "$MOUNT" 2>/dev/null | tail -1)"
if [ -z "${total_kb:-}" ] || [ "${total_kb:-0}" -eq 0 ]; then
    echo "disk_watchdog: cannot read disk usage for $MOUNT" >&2
    exit 1
fi
free_kb=$((total_kb - used_kb))
used_pct=$((used_kb * 100 / total_kb))

# --- history, kept small ------------------------------------------------------
echo "$now $free_kb" >> "$history_file" 2>/dev/null || true
if [ -f "$history_file" ]; then
    tail -n "$HISTORY_MAX_LINES" "$history_file" > "$history_file.tmp" 2>/dev/null \
        && mv "$history_file.tmp" "$history_file" 2>/dev/null || true
fi

# --- trend: days left, from measured history ---------------------------------
# Only meaningful when free space is actually shrinking. A growing or flat
# trend produces no estimate rather than a reassuring number.
days_left=""
if [ -r "$history_file" ]; then
    min_age=$((MIN_TREND_HOURS * 3600))
    ref_line="$(awk -v now="$now" -v min_age="$min_age" '$1 <= now - min_age { line = $0 } END { print line }' "$history_file" 2>/dev/null)"
    if [ -n "$ref_line" ]; then
        ref_epoch="${ref_line%% *}"
        ref_free="${ref_line##* }"
        elapsed=$((now - ref_epoch))
        lost=$((ref_free - free_kb))
        if [ "$elapsed" -gt 0 ] && [ "$lost" -gt 0 ]; then
            # kB lost per day, then how many days until free_kb hits zero.
            per_day=$((lost * 86400 / elapsed))
            [ "$per_day" -gt 0 ] && days_left=$((free_kb / per_day))
        fi
    fi
fi

# --- level --------------------------------------------------------------------
level=""
if [ "$used_pct" -ge "$CRITICAL_PCT" ]; then
    level="critical"
    throttle="$CRITICAL_THROTTLE_SECONDS"
elif [ "$used_pct" -ge "$WARN_PCT" ]; then
    level="warning"
    throttle="$WARN_THROTTLE_SECONDS"
fi

if [ -z "$level" ]; then
    # Back below the threshold: forget the previous alert so that crossing it
    # again is reported immediately instead of waiting out the throttle.
    rm -f "$stamp_file" "$level_file" 2>/dev/null || true
    exit 0
fi

echo "disk_watchdog: $MOUNT at ${used_pct}% (${level})" >&2

# --- throttle -----------------------------------------------------------------
# An escalation from warning to critical always goes out, whatever the throttle:
# it is new information, and it is the one that matters.
previous_level="$(cat "$level_file" 2>/dev/null || echo "")"
if [ "$level" = "$previous_level" ] && [ -r "$stamp_file" ]; then
    last="$(cat "$stamp_file" 2>/dev/null || echo 0)"
    if [ $((now - ${last:-0})) -lt "$throttle" ]; then
        exit 0
    fi
fi

free_human="$(awk -v kb="$free_kb" 'BEGIN { printf "%.1f GB", kb/1048576 }')"
if [ "$level" = "critical" ]; then
    title="Disco quasi pieno"
    body="Il disco della VPS e' al ${used_pct}% e restano ${free_human}. Con SQLite un disco pieno significa scritture fallite, quindi rischio di corruzione del database."
else
    title="Spazio disco in esaurimento"
    body="Il disco della VPS e' al ${used_pct}%, restano ${free_human}. Non e' ancora un problema, ma conviene intervenire prima che lo diventi."
fi
if [ -n "$days_left" ]; then
    body="$body Al ritmo attuale si riempie fra circa ${days_left} giorni: e' una proiezione, non una promessa."
fi

if "$here/notify_alert.sh" "$title" "$body" disk_watchdog; then
    echo "$now" > "$stamp_file"
    echo "$level" > "$level_file"
else
    # Do not record the alert: a failed delivery must be retried next run.
    echo "disk_watchdog: alert delivery failed" >&2
    exit 1
fi
