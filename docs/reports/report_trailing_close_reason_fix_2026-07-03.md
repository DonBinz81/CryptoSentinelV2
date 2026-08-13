# Report - Trailing close reason fix

## 1. COSA È STATO FATTO

- Corretto il motivo di chiusura dei trade chiusi da trailing stop.
- Le uscite da trailing ora restano marcate come `trailing_stop` anche quando il livello è già in profitto.
- Il motivo `breakeven` resta riservato allo `stop_loss` spostato a entry/costi.

## 2. COME È STATO FATTO

- In `backend/app/agent/service.py` la logica di uscita Spot/Perp non converte più un trailing profittevole in `breakeven`.
- `_level_fill_price` usa `stop_loss` per `breakeven` e `trailing_stop` per `trailing_stop`, mantenendo separati label e livello di fill.
- Aggiornati i test unitari esistenti e aggiunto un caso Perp short per coprire la casistica segnalata.

## 3. COSA È STATO VERIFICATO

- Eseguito `backend\.venv\Scripts\python.exe -m compileall backend\app\agent\service.py` con esito positivo.
- Eseguito `backend\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_agent_step6.py -k "trailing_above_entry_labeled_trailing_stop or short_trailing_below_entry_labeled_trailing_stop or close_at_breakeven_is_labeled_breakeven"` con esito positivo: 4 test passati.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno: non sono stati modificati sizing, stop, trailing, breakeven o logiche di entrata. È cambiata solo l'etichetta della causa di chiusura.

## 5. QUESTIONI APERTE

- I trade già salvati in DB con `auto_close:breakeven` non vengono riscritti da questa modifica. La correzione vale per le nuove chiusure.

## 6. STATO DELIVERABLE

- Deliverable completato, testato e pronto al push.
