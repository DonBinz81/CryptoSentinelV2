#!/usr/bin/env bash
# Refuse to open the production database while the backend is running.
#
# Installed as /usr/local/bin/sqlite3, which precedes /usr/bin in PATH - and in
# sudo's secure_path too, so `sudo sqlite3 ...` also lands here.
#
# Why this exists: opening the live database read-only corrupted it four times.
# In WAL mode a reader can run a checkpoint when it closes and take -wal/-shm
# away from the running backend, leaving it with an orphaned journal. The rule
# "never open the production DB while the service is up" was written, in red, at
# the top of every session prompt - and was still broken, because "it's only a
# SELECT" is a reasonable thought if you don't know how WAL behaves. Documentation
# failed four times out of four; this makes the mistake impossible to make by
# accident. See NOTE/80.
#
# Deliberately fail-open: anything unexpected in the check below lets the command
# through. A guard that blocks legitimate work by mistake would be worse than the
# problem, and the alarm (db_watchdog, every minute) is still there as a net.
#
# Not a security boundary - `/usr/bin/sqlite3` bypasses it, on purpose. It stops
# the accident, not a determined operator who knows what they are doing.
set -uo pipefail

REAL_SQLITE="/usr/bin/sqlite3"
PROTECTED="${PROTECTED_DB:-/opt/cryptosentinelv2/app/backend/local.db}"
SERVICE="${SERVICE:-cryptosentinelv2-backend}"

# Does any argument point at the protected file? Resolve each one, so a relative
# path from inside the backend directory is caught too.
targets_protected=0
for arg in "$@"; do
    case "$arg" in
        -*) continue ;;
    esac
    resolved="$(readlink -f -- "$arg" 2>/dev/null || true)"
    if [ -n "$resolved" ]; then
        case "$resolved" in
            "$PROTECTED"|"$PROTECTED"-wal|"$PROTECTED"-shm) targets_protected=1; break ;;
        esac
    fi
done

if [ "$targets_protected" -eq 1 ] && [ "$(systemctl is-active "$SERVICE" 2>/dev/null)" = "active" ]; then
    cat >&2 <<'MSG'

  ┌──────────────────────────────────────────────────────────────────────┐
  │  RIFIUTATO: il backend e' ATTIVO e questo aprirebbe il database      │
  │  di produzione.                                                      │
  └──────────────────────────────────────────────────────────────────────┘

  Anche una SELECT puo' corromperlo: il database e' in modalita' WAL, e un
  lettore, quando chiude, puo' fare un checkpoint e portare via i file
  -wal/-shm da sotto il processo del backend. E' successo quattro volte.

  USA INVECE:

    csv2-db "SELECT count(*) FROM perp_trades;"      <- copia e interroga la copia
    csv2-db --backup "SELECT ..."                    <- l'ultimo backup (piu' veloce)
    csv2-db --shell                                  <- shell interattiva sulla copia

  Oppure l'API del backend, che e' la via normale.

  Se devi davvero lavorare sul file (manutenzione), ferma prima il servizio:
  la procedura completa e' in NOTE/54, e comincia SEMPRE con uno snapshot a
  caldo di local.db E local.db-wal.

MSG
    exit 1
fi

exec "$REAL_SQLITE" "$@"
