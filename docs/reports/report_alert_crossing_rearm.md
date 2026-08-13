# Report Alert Crossing E Riarmo

## 1. COSA È STATO FATTO

- Aggiunta la modalita' alert prezzo "Solo attraversamento" nella modale di creazione alert.
- Aggiunta l'opzione default one-shot e la modalita' "Continua" per mantenere attivo l'alert dopo lo scatto.
- Aggiunto il campo "Riarmo (%)" quando l'alert crossing resta attivo.
- Esteso lo stato frontend degli alert con ultimo prezzo osservato, direzione ultimo crossing, prezzo/ora ultimo scatto e stato di riarmo.
- Estesa la sincronizzazione verso backend con opzioni crossing, keep-active, rearm percent e ultimo prezzo osservato.
- Esteso il checker FCM backend con rilevazione attraversamento up/down e riarmo percentuale.
- Aggiunta regressione backend per verificare che un alert crossing continuo non riscatta dentro la fascia neutra e si riabilita solo dopo l'uscita dalla fascia.

## 2. COME È STATO FATTO

- Frontend:
  - `PriceAlert` ora include campi opzionali per crossing e riarmo.
  - `AlertModal` mostra controlli compatti solo per alert prezzo/percentuale, non per range.
  - `useAlerts` valuta i prezzi correnti per aggiornare stato locale e storico senza generare notifiche autonome.
  - `AlertsTab` mostra badge brevi: `Cross`, `Riarmo`, `Up`, `Down` e percentuale di riarmo.
- Backend:
  - `PriceAlertItem` accetta `crossing_only`, `keep_active_after_trigger`, `rearm_percent`, `last_observed_price`.
  - `CheckerState` persiste ultimo prezzo osservato e set degli alert in attesa di riarmo.
  - `price_checker` confronta prezzo precedente e corrente per rilevare attraversamenti e invia FCM con `cross_direction`.

## 3. COSA È STATO VERIFICATO

- `npx tsc -b` completato con esito positivo.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_alert_store.py backend/tests/unit/test_device_alert_separation.py` completato con esito positivo: 9 test passed.
- Il primo tentativo con `python -m pytest ...` fuori virtualenv e' fallito per dipendenza locale mancante (`sqlalchemy`); la verifica e' stata rieseguita nel virtualenv backend gia' presente.

## 4. SCOSTAMENTI DAL PIANO

- Non e' stato eseguito `npm run build` perche' il build Vite locale puo' caricare `.env`; e' stato usato `npx tsc -b` come verifica sicura lato TypeScript.
- I testi UI restano coerenti con l'app legacy in italiano, usando label corte per non appesantire la modale mobile.

## 5. QUESTIONI APERTE

- Le notifiche reali FCM vanno verificate su dispositivo con backend attivo e token configurati.
- Se in futuro si vuole un edit completo della direzione crossing nella UI, oggi il crossing rileva automaticamente sia up sia down rispetto alla soglia.

## 6. STATO DELIVERABLE

Parziale ma implementato e verificato localmente: logica frontend/backend e test mirati completati; resta verifica end-to-end su device reale con FCM.
