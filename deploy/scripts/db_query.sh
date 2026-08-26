#!/usr/bin/env bash
# Query the production database safely, by never opening the production file.
#
# Installed as `csv2-db`. Exists because the correct procedure - copy the file,
# query the copy - is four lines of shell that nobody remembers under pressure,
# while the wrong one is a single obvious command. Four corruptions (16/08,
# 18/08, 26/08 and one earlier) all came from someone typing that obvious
# command. Making the right thing the easy thing works better than forbidding
# the wrong one, so this does the copying for you.
#
# Usage:
#   csv2-db "SELECT count(*) FROM perp_trades;"
#   csv2-db -header -csv "SELECT * FROM perp_positions WHERE status='open';"
#   csv2-db --backup "SELECT ..."    # query the last automatic backup instead
#   csv2-db --shell                  # interactive sqlite3 shell on the copy
#   csv2-db --keep "SELECT ..."      # leave the copy in place for more queries
#
# Why a copy and not a read-only open: in WAL mode even a pure reader can run a
# checkpoint when it closes and take -wal/-shm away from the running backend,
# which is exactly how the database got corrupted. `cp` reads a file; it never
# opens a database. See NOTE/54 and NOTE/80.
set -uo pipefail

DB_PATH="${DB_PATH:-/opt/cryptosentinelv2/app/backend/local.db}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/cryptosentinelv2}"
WORK_DIR="${WORK_DIR:-/tmp/csv2-db-$$}"

use_backup=0
keep=0
shell_mode=0
args=()

while [ $# -gt 0 ]; do
    case "$1" in
        --backup) use_backup=1; shift ;;
        --keep)   keep=1; shift ;;
        --shell)  shell_mode=1; shift ;;
        --help|-h)
            sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) args+=("$1"); shift ;;
    esac
done

if [ "$shell_mode" -eq 0 ] && [ "${#args[@]}" -eq 0 ]; then
    echo "csv2-db: nothing to run. Pass a SQL statement, or --shell. See --help." >&2
    exit 1
fi

cleanup() {
    if [ "$keep" -eq 1 ]; then
        echo "csv2-db: copy kept in $WORK_DIR (remove it when done)" >&2
    else
        rm -rf "$WORK_DIR"
    fi
}
trap cleanup EXIT

mkdir -p "$WORK_DIR" || { echo "csv2-db: cannot create $WORK_DIR" >&2; exit 1; }

if [ "$use_backup" -eq 1 ]; then
    # The newest published backup. Never older than the backup cadence (6h) and
    # already integrity-checked when it was produced.
    latest="$(sudo ls -1 "$BACKUP_DIR" 2>/dev/null | grep -E '^[0-9]{8}T' | tail -1)"
    if [ -z "$latest" ]; then
        echo "csv2-db: no automatic backup found in $BACKUP_DIR" >&2
        exit 1
    fi
    sudo cp "$BACKUP_DIR/$latest/local.db" "$WORK_DIR/db.sqlite" || exit 1
    echo "csv2-db: querying backup $latest" >&2
else
    # Hot copy of the live file. Both sidecars matter: without -wal the copy is
    # missing every transaction not yet checkpointed into the main file.
    sudo cp "$DB_PATH" "$WORK_DIR/db.sqlite" || exit 1
    [ -f "$DB_PATH-wal" ] && sudo cp "$DB_PATH-wal" "$WORK_DIR/db.sqlite-wal"
    [ -f "$DB_PATH-shm" ] && sudo cp "$DB_PATH-shm" "$WORK_DIR/db.sqlite-shm"
fi
sudo chown "$(id -u):$(id -g)" "$WORK_DIR"/db.sqlite* 2>/dev/null

# Call sqlite3 by absolute path: /usr/local/bin/sqlite3 is the guard wrapper,
# and going through it here would be a pointless round trip.
SQLITE="/usr/bin/sqlite3"
[ -x "$SQLITE" ] || SQLITE="sqlite3"

if [ "$shell_mode" -eq 1 ]; then
    "$SQLITE" "$WORK_DIR/db.sqlite"
else
    "$SQLITE" "$WORK_DIR/db.sqlite" "${args[@]}"
fi
