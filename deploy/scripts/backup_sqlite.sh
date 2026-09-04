#!/usr/bin/env bash
# Backup of the SQLite database, of the runtime settings and of the versioned
# config defaults.
#
# Safety rule (NOTE/54, 2026-08-18): this script never OPENS the production
# database. The running service is the only process allowed to hold it; opening
# it from a second process is what removed the -wal/-shm files under the live
# backend and corrupted the database. Here the files are COPIED (cp reads a
# file, it does not open a database) and every sqlite3 command runs against the
# copy.
#
# The artifact is built in a staging directory and published only on success, so
# a failed run can never leave behind a directory that looks like a backup.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/cryptosentinelv2/app}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/cryptosentinelv2}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
# Backups older than this are stored gzipped. The recent ones stay uncompressed
# so a restore under pressure needs no extra step, while the tail - which is
# rarely read - costs about a quarter of the space. Measured on the real file:
# 140MB -> 36MB (3.9x), 1.1s to decompress. Set to 0 to disable compression.
COMPRESS_AFTER_HOURS="${COMPRESS_AFTER_HOURS:-48}"
DB_PATH="${DB_PATH:-$APP_DIR/backend/local.db}"
TWAK_HOME="${TWAK_HOME:-/home/cryptosentinelv2/.twak}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target_dir="$BACKUP_DIR/$timestamp"
stage_dir="$BACKUP_DIR/.staging_$timestamp"
status="failed"
integrity="not_checked"
db_bytes=0

chmod 700 "$BACKUP_DIR"
mkdir -p "$stage_dir"
chmod 700 "$stage_dir"

# Always publish the outcome, so a failure can never be silent.
write_result() {
    cat > "$BACKUP_DIR/last_result.json" <<EOF
{"timestamp": "$timestamp", "status": "$status", "integrity": "$integrity", "db_bytes": $db_bytes}
EOF
    chmod 600 "$BACKUP_DIR/last_result.json"
}

on_exit() {
    rc=$?
    # Keep the staging directory only when it has been published: "ok" and
    # "integrity_failed" are the two outcomes that produce an artifact.
    if [ "$status" != "ok" ] && [ "$status" != "integrity_failed" ]; then
        rm -rf "$stage_dir"
    fi
    write_result
    exit "$rc"
}
trap on_exit EXIT

copy_database() {
    cp "$DB_PATH" "$stage_dir/local.db"
    if [ -f "$DB_PATH-wal" ]; then cp "$DB_PATH-wal" "$stage_dir/local.db-wal"; fi
    if [ -f "$DB_PATH-shm" ]; then cp "$DB_PATH-shm" "$stage_dir/local.db-shm"; fi
}

if [ -f "$DB_PATH" ]; then
    copy_database

    if command -v sqlite3 >/dev/null 2>&1; then
        # Consolidate the copy into a single file, then verify it. A hot copy can
        # be inconsistent if a checkpoint ran while copying: retry once before
        # declaring the backup unusable, to keep false alarms rare.
        for attempt in 1 2; do
            sqlite3 "$stage_dir/local.db" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
            # `|| true`: a corrupt database makes sqlite3 exit non-zero, and under
            # `set -o pipefail` that would abort the run before the artifact can be
            # kept and flagged. The failure is carried in $integrity instead.
            integrity="$(sqlite3 "$stage_dir/local.db" 'PRAGMA integrity_check;' 2>&1 | head -1 || true)"
            if [ "$integrity" = "ok" ]; then
                break
            fi
            if [ "$attempt" = "1" ]; then
                rm -f "$stage_dir/local.db" "$stage_dir/local.db-wal" "$stage_dir/local.db-shm"
                sleep 5
                copy_database
            fi
        done
        rm -f "$stage_dir/local.db-wal" "$stage_dir/local.db-shm"

        # The effective configuration lives only inside the database. Export it in
        # readable form so it can be audited, diffed over time and used as the
        # source of truth for analysis, without anyone opening the live database.
        sqlite3 "$stage_dir/local.db" \
            "SELECT key || char(9) || value FROM runtime_state ORDER BY key;" \
            > "$stage_dir/runtime_state.tsv" 2>/dev/null || true
        sqlite3 "$stage_dir/local.db" \
            "SELECT value FROM runtime_state WHERE key = 'mobile_agent_settings';" \
            > "$stage_dir/agent_settings.json" 2>/dev/null || true
        if command -v python3 >/dev/null 2>&1 && [ -s "$stage_dir/agent_settings.json" ]; then
            python3 -m json.tool "$stage_dir/agent_settings.json" \
                > "$stage_dir/agent_settings.pretty.json" 2>/dev/null \
                && mv "$stage_dir/agent_settings.pretty.json" "$stage_dir/agent_settings.json" \
                || rm -f "$stage_dir/agent_settings.pretty.json"
        fi
        chmod 600 "$stage_dir/runtime_state.tsv" "$stage_dir/agent_settings.json" 2>/dev/null || true
    else
        integrity="sqlite3_missing"
    fi

    db_bytes="$(stat -c %s "$stage_dir/local.db" 2>/dev/null || echo 0)"
else
    # A backup without the database is not a backup. Fail loudly rather than
    # publish an artifact that looks complete: a wrong path, a renamed file or an
    # unmounted volume would otherwise be reported as a successful run.
    status="db_missing"
    echo "backup_sqlite: no database found at the configured path" >&2
    exit 1
fi

# Export only versioned non-secret defaults. Local instance config and env files
# remain outside the backup artifact produced by this repo script.
if [ -d "$APP_DIR/configs" ]; then
    mkdir -p "$stage_dir/configs"
    find "$APP_DIR/configs" -maxdepth 1 -type f -name '*.yaml' ! -name 'instance.yaml' \
        -exec cp -p {} "$stage_dir/configs/" \;
fi

# Preserve encrypted TWAK headless state if present. Do not print contained paths
# or file names in normal output; this archive is stored with 0600 permissions.
if [ -d "$TWAK_HOME" ]; then
    tar -C "$TWAK_HOME" -czf "$stage_dir/twak-state.tar.gz" .
    chmod 600 "$stage_dir/twak-state.tar.gz"
fi

# An unreadable copy is still published: when the live database is corrupt this
# artifact may be the only surviving material. It is flagged, and the non-zero
# exit makes the timer report a failure instead of passing silently.
if [ -f "$stage_dir/local.db" ] && [ "$integrity" != "ok" ] && [ "$integrity" != "sqlite3_missing" ]; then
    status="integrity_failed"
    mv "$stage_dir" "$target_dir"
    : > "$target_dir/INTEGRITY_FAILED"
    echo "backup_sqlite: integrity check failed on the database copy: $integrity" >&2
    exit 1
fi

status="ok"
mv "$stage_dir" "$target_dir"

find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -name '2*' -mtime +"$RETENTION_DAYS" \
    -exec rm -rf {} +

# Compress the database copy of older backups. Only local.db is worth it: it is
# ~99% of a backup's size, and leaving the small companion files (settings,
# config, runtime state) readable keeps a backup directory inspectable at a
# glance without unpacking anything.
#
# A failure here must never fail the backup: at this point the artifact is
# already published and verified, so a compression problem is a space issue,
# not a data issue.
if [ "${COMPRESS_AFTER_HOURS:-0}" -gt 0 ] && command -v gzip >/dev/null 2>&1; then
    compress_minutes=$((COMPRESS_AFTER_HOURS * 60))
    find "$BACKUP_DIR" -mindepth 2 -maxdepth 2 -type f -name 'local.db'         -mmin +"$compress_minutes" -print 2>/dev/null | while IFS= read -r old_db; do
        if gzip -6 "$old_db" 2>/dev/null && [ -f "$old_db.gz" ]; then
            continue
        fi
        echo "backup_sqlite: could not compress $old_db, left as is" >&2
        rm -f "$old_db.gz"
    done || true
fi
