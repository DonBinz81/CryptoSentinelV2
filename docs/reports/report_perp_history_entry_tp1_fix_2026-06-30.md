# Report - Fix entry history Perp dopo TP1

## 1. COSA È STATO FATTO

- Verificati gli ultimi record ETH Perp nel DB locale.
- Corretto il calcolo dell'`entry_price` mostrato nella history Perp per chiusure parziali/finali della stessa posizione.
- Aggiunto un test di regressione per TP1 parziale + chiusura finale.

## 2. COME È STATO FATTO

- La vista Perp ora costruisce una mappa `position_id -> entry_price` dalle posizioni storiche.
- Per i close trade automatici `cls_<position_id>_<suffix>` usa l'entry della posizione originale.
- Il fallback storico da `pnl_usd / size` resta disponibile solo quando la posizione non e' trovata.

## 3. COSA È STATO VERIFICATO

- Sul DB locale l'ultimo ETH Perp aveva entry posizione/open trade `1557.74`.
- Le due righe ETH recenti erano chiusure della stessa posizione: `take_profit_1_partial` e `trailing_stop`.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_persistence_layer.py -q -k "perp_history_uses_position_entry_for_partial_closes or spot_and_perp_views_return_open_positions"`
- `backend\.venv\Scripts\python.exe -m py_compile backend/app/persistence/views.py`
- `git diff --check`

## 4. SCOSTAMENTI DAL PIANO

- Nessuno. La correzione riguarda solo la vista/read model, non i dati persistiti o la logica di trading.

## 5. QUESTIONI APERTE

- Le chiusure storiche prive di posizione associabile continuano a usare il fallback stimato dal PnL netto, che puo' differire dall'entry reale se include fee/funding.

## 6. STATO DELIVERABLE

- Implementato e verificato con test mirati.
