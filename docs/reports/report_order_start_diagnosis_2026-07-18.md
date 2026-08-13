# Report Diagnosi Partenza Ordini - 2026-07-18

## 1. COSA È STATO FATTO

Analizzata la mancata partenza degli ordini Spot e Perp senza modificare la logica applicativa.

## 2. COME È STATO FATTO

Sono stati ispezionati i log backend recenti, le decisioni agente, le tabelle trade/posizioni e i runtime settings persistiti, evitando file sensibili. È stata verificata la coerenza del percorso agente/risk con test unitari mirati.

## 3. COSA È STATO VERIFICATO

- Backend e loop agente risultano attivi.
- Le watchlist Spot e Perp sono valorizzate.
- `markets_enabled` è `both` e `execution_mode` è `dry_run`.
- Non ci sono posizioni aperte.
- Oggi non risultano trade Spot o Perp nel DB locale.
- Le decisioni recenti sono prevalentemente `skip/block` per filtri tecnici non soddisfatti.
- Sono presenti decisioni con segnali validi bloccate da `drawdown_cap_guard`.
- Il portfolio locale mostra `drawdown_pct` sopra la soglia prudente del 15%.
- Test eseguiti: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/unit/test_agent_step6.py -q` con esito `63 passed`.

## 4. SCOSTAMENTI DAL PIANO

Nessuno: è stata effettuata solo diagnosi, senza patch funzionali.

## 5. QUESTIONI APERTE

Decidere se mantenere il blocco prudente sul drawdown oppure modificare parametri/runtime policy. Da valutare separatamente anche la lock SQLite osservata su `/api/v1/alerts/sync`, che non risulta la causa diretta della mancata apertura ordini ma può rallentare o disturbare il backend sotto carico.

## 6. STATO DELIVERABLE

Diagnosi completata. Nessun commit richiesto o creato per modifiche funzionali.
