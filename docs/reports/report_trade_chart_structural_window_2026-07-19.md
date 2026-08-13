# Finestra Strutturale Grafici Trade

## 1. COSA È STATO FATTO

- Corretto il punto di partenza dei grafici trade con stop loss strutturale.
- I grafici ora includono tutta la finestra di lookback usata per scegliere la candela riferimento SL.
- Con i default attuali vengono mostrate le 20 candele candidate prima dell'ingresso, non solo 10 candele prima della candela viola.

## 2. COME È STATO FATTO

- `AgentService._snapshot_closed_trade` usa `opened_at - lookback*candle_interval` come inizio dello snapshot quando esiste `stop_reference_time`.
- `views._build_live_chart` usa la stessa finestra per le posizioni aperte.
- `views._enrich_trade_chart_context` usa la stessa finestra anche per arricchire snapshot storici legacy.
- Il metadata `stop_reference.pre_candles` ora riporta il lookback effettivo.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py backend/tests/unit/test_signal_stop_loss_modes.py -q`
  - Esito: 68 passed.
- `backend\.venv\Scripts\python.exe -m compileall -q backend/app/api/routes/views.py backend/app/agent/service.py`
  - Esito: ok.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Nessuna.

## 6. STATO DELIVERABLE

- Implementato e verificato localmente.
