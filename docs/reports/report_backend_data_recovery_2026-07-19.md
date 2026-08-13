# Ripristino Backend Dati Dopo Reset

## 1. COSA È STATO FATTO

- Diagnosticato backend locale appeso: `/health/live` andava in timeout e il processo era stato avviato prima dell'ultima correzione equity.
- Riavviato il backend su porta 8001 usando la virtualenv del progetto.
- Aggiunta creazione automatica del portfolio dry-run base all'avvio se `PortfolioState` manca.
- Corretto `backend/scripts/stop_backend.ps1`, che falliva usando la variabile riservata PowerShell `$PID`.

## 2. COME È STATO FATTO

- Aggiunta `_ensure_base_portfolio` in `backend/app/main.py`, eseguita dopo migrazione DB e prima dei loop runtime.
- Se non esiste un portfolio per `default_user_id`, viene creato con `dry_run_capital_usd`, peak uguale al capitale e stato `idle`.
- Lo script di stop usa ora `$ProcessId` invece di `$pid`.

## 3. COSA È STATO VERIFICATO

- `/health/live` locale risponde `200`.
- `portfolio_state` è presente nel DB locale dopo restart, con equity non zero.
- Test:
  - `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/test_persistence_layer.py backend/tests/unit/test_agent_step6.py -q`
  - Risultato: `88 passed`.
- `backend/app/main.py` compila con `py_compile`.
- Sintassi PowerShell di `backend/scripts/stop_backend.ps1` verificata con parser PowerShell.

## 4. SCOSTAMENTI DAL PIANO

- È stato necessario un fix operativo allo script di stop backend perché impediva il riavvio pulito.

## 5. QUESTIONI APERTE

- I log mostrano che il primo giro market-data dopo restart può impiegare diversi secondi per risolvere identità CMC/CoinGecko; dopo cache calda le richieste tornano rapide.
- Se app/dashboard continuano a mostrare dati vecchi, va forzato refresh lato client dopo il restart backend.

## 6. STATO DELIVERABLE

- Backend ripristinato e correzione implementata. Da verificare su app reale che preferiti/equity si aggiornino dopo refresh.
