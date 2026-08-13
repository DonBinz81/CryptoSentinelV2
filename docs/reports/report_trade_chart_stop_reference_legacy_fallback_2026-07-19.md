# Fallback Legacy Grafici Trade Stop Loss

## 1. COSA È STATO FATTO

- Aggiunto un fallback backend per grafici trade vecchi che non hanno `stop_reference_time` salvato.
- Esteso il dettaglio dei trade aperti per recuperare le candele prima dell'apertura anche quando la posizione e' stata creata prima dei nuovi campi stop-reference.
- Esteso il dettaglio dei trade chiusi per arricchire lo snapshot storico con candele pre-apertura e ricostruire la candela riferimento SL.
- Forzato il dettaglio trade in app e dashboard a richiedere `enrich_chart=true` quando l'utente apre il grafico.

## 2. COME È STATO FATTO

- `views.py` ora calcola il lookback strutturale da Settings, usa 20 candele piu' 10 candele di contesto e fa fetch Binance dal timestamp necessario.
- Se i campi persistiti non esistono, il backend inferisce la candela riferimento: minimo `low` per spot/long, massimo `high` per perp short.
- I payload inferiti includono `stop_reference.inferred=true`, mantenendo compatibile il marker esistente.
- La cache mobile considera completo un grafico trade solo se contiene anche `stop_reference`.
- La dashboard apre i trade detail direttamente in modalita' arricchita.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py backend/tests/unit/test_signal_stop_loss_modes.py -q`
  - Esito: 68 passed.
- `backend\.venv\Scripts\python.exe -m compileall -q backend/app/api/routes/views.py`
  - Esito: ok.
- `npx tsc -b`
  - Esito: ok.
- `npx tsc -p dashboard/tsconfig.json`
  - Esito: ok.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno rilevante.

## 5. QUESTIONI APERTE

- Il fallback e' best-effort: se Binance non restituisce candele per quel simbolo/intervallo, il grafico resta con lo snapshot disponibile.
- I grafici legacy inferiti possono differire dal riferimento originale se il trade era stato aperto con modalita' ATR; il fallback serve a mostrare il contesto strutturale richiesto per ispezionare lo stop loss.

## 6. STATO DELIVERABLE

- Implementato e verificato localmente.
