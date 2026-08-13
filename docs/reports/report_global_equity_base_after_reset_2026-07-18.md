# Equity Globale Dopo Reset DB

## 1. COSA È STATO FATTO

- Corretta la vista globale quando il portfolio non è ancora presente nel DB.
- La UI non deve più mostrare equity a 0 USD dopo un reset o prima del primo tick agente.

## 2. COME È STATO FATTO

- `ViewService` ora riceve `base_equity_usd`.
- Gli endpoint `/api/v1/views/spot`, `/api/v1/views/perp`, `/api/v1/views/global` e asset breakdown passano il capitale dry-run da `Settings`.
- Se `PortfolioState` è assente, `/api/v1/views/global` restituisce `total_equity_usd` e `initial_equity_usd` pari al capitale dry-run configurato, con drawdown a zero.

## 3. COSA È STATO VERIFICATO

- Compilazione Python dei file modificati.
- Test mirati:
  - `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/test_persistence_layer.py -q`
  - Risultato: `25 passed`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- In runtime va confermato che il backend in esecuzione sia aggiornato/restartato dopo il deploy, perché il comportamento a equity 0 corrispondeva anche al codice precedente quando `PortfolioState` mancava.

## 6. STATO DELIVERABLE

- Implementato e verificato con test mirati.
