# Valore Stop Iniziale Nei Grafici Trade

## 1. COSA È STATO FATTO

- Corretto il valore dello stop loss esposto nei grafici e nei dettagli trade.
- I grafici usano lo stop iniziale calcolato all'ingresso (`initial_stop_loss`) invece dello stop corrente, che puo' essere stato spostato da breakeven o trailing.
- Se manca `initial_stop_loss` ma esiste il riferimento SL viola, il valore viene ricostruito da `stop_reference.price` e dal buffer strutturale configurato.

## 2. COME È STATO FATTO

- `AgentService._snapshot_closed_trade` salva `initial_stop_loss` nel payload chart quando disponibile.
- `views._build_live_chart` espone lo stesso valore iniziale per i trade aperti.
- `views.py` normalizza i payload legacy applicando lo stop iniziale o ricostruendo lo stop da riferimento strutturale.
- Il calcolo del segnale resta invariato: con buffer `1.10`, long = minimo * 0.989, short = massimo * 1.011.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py backend/tests/unit/test_signal_stop_loss_modes.py backend/tests/unit/test_persistence_layer.py -q`
  - Esito: 93 passed.
- `backend\.venv\Scripts\python.exe -m compileall -q backend/app/api/routes/views.py backend/app/agent/service.py`
  - Esito: ok.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Nessuna.

## 6. STATO DELIVERABLE

- Implementato e verificato localmente.
