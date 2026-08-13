#!/usr/bin/env bash
# Avvia il backend CryptoSentinel con Uvicorn.
#
# Uso:
#   ./backend/scripts/run_backend.sh          # produzione
#   ./backend/scripts/run_backend.sh --dev    # sviluppo (reload attivo)
#
# Eseguire dalla radice del progetto oppure da qualsiasi directory:
# lo script risolve i path in modo assoluto.

set -euo pipefail

DEV=0
for arg in "$@"; do
    case "$arg" in
        --dev|-d) DEV=1 ;;
        *) echo "Argomento sconosciuto: $arg" >&2; exit 1 ;;
    esac
done

# Radice del progetto = due livelli sopra backend/scripts/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$BACKEND_DIR")"

# Attiva il virtualenv se presente
VENV_ACTIVATE="$BACKEND_DIR/.venv/bin/activate"
if [ -f "$VENV_ACTIVATE" ]; then
    # shellcheck source=/dev/null
    source "$VENV_ACTIVATE"
else
    echo "WARN: virtualenv non trovato in $BACKEND_DIR/.venv — uso il Python di sistema." >&2
fi

# Legge host e porta dalle Settings (instance.yaml + env), senza duplicare valori
read -r API_HOST API_PORT < <(
    python - <<PYEOF
import sys
sys.path.insert(0, "$PROJECT_ROOT")
from backend.app.core.config import get_settings
s = get_settings()
print(s.api_host, s.api_port)
PYEOF
)

if [ -z "$API_HOST" ] || [ -z "$API_PORT" ]; then
    echo "Errore: impossibile leggere la configurazione." >&2
    exit 1
fi

if [ "$DEV" -eq 1 ]; then
    echo "Avvio backend su $API_HOST:$API_PORT [DEV — reload attivo]"
else
    echo "Avvio backend su $API_HOST:$API_PORT"
fi

UVICORN_ARGS=(
    -m uvicorn
    "backend.app.main:app"
    --host "$API_HOST"
    --port "$API_PORT"
)
[ "$DEV" -eq 1 ] && UVICORN_ARGS+=(--reload)

cd "$PROJECT_ROOT"
exec python "${UVICORN_ARGS[@]}"
