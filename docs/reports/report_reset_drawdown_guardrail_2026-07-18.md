# Reset Drawdown Guardrail Dopo DB Reset

## 1. COSA È STATO FATTO

- Corretto il reset admin del database per reinizializzare subito lo stato portfolio.
- Il portfolio riparte dal capitale dry-run configurato con drawdown, max drawdown, daily loss, esposizione e contatori a zero.
- Aggiornati i test di persistenza per coprire il caso di drawdown bloccante prima del reset.

## 2. COME È STATO FATTO

- `reset_all_data` accetta ora `reset_portfolio_capital_usd`.
- Dopo la cancellazione di trade, posizioni, snapshot, grafici e portfolio precedente, se il capitale di reset è presente viene creato un nuovo `PortfolioState` neutro.
- L'endpoint admin `/api/v1/agent/dev/reset-db` passa il capitale dry-run da `Settings`, così il reset usato da app/dashboard lascia il bot in uno stato non bloccato.

## 3. COSA È STATO VERIFICATO

- Compilazione Python dei file modificati.
- Test unitari mirati sulla persistenza:
  - `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/test_persistence_layer.py -q`
  - Risultato: `24 passed`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Da verificare in runtime che, dopo reset da dashboard/app, il prossimo tick agente riparta senza `drawdown_cap_guard`.

## 6. STATO DELIVERABLE

- Implementato e verificato con test mirati.
