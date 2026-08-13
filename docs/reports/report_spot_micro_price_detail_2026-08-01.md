# Report Spot micro price detail - 2026-08-01

## 1. COSA E STATO FATTO

- Corretto il dettaglio trade spot per asset con prezzo inferiore a 0.00000001, come BABYDOGE.
- Estesa la formattazione prezzi backend, app e dashboard fino a 18 decimali.
- Rifinita la UI: app e dashboard restano a massimo 8 decimali sopra 0.000001 e mostrano piu' decimali solo sotto quella soglia.
- Aumentata la precisione ORM dei campi prezzo Spot/Perp da 8 a 18 decimali dove rappresentano prezzi o livelli.
- Aggiunto fallback nel dettaglio spot: se una posizione storica ha entry salvata a zero, l'entry viene ricostruita da amount_quote / size quando possibile.

## 2. COME E STATO FATTO

- `backend/app/api/routes/views.py` ora formatta i prezzi micro-token senza portarli a zero e recupera l'entry spot da notional/size per record gia' degradati.
- `backend/app/persistence/models/positions.py` usa precisione a 18 decimali per entry, current, SL, TP, trailing, ATR, stop reference, max price e liquidation price.
- `backend/app/persistence/models/trades.py` usa precisione a 18 decimali per il prezzo unitario spot/perp.
- `backend/app/persistence/migration.py` crea le colonne prezzo aggiunte in futuro con precisione a 18 decimali.
- `src/components/AgentTab.tsx` e `dashboard/src/App.tsx` mostrano i prezzi sub-1 USD in modo compatto: 8 decimali fino a 0.000001, full-decimal solo sotto 0.000001.

## 3. COSA E STATO VERIFICATO

- Log backend: le richieste dettaglio BABYDOGE rispondevano 200, quindi il problema non era endpoint non raggiunto.
- Test mirati:
  - `test_spot_trade_detail_preserves_micro_token_prices`
  - `test_spot_trade_detail_recovers_zero_entry_from_trade_notional`
  - `test_perp_trade_detail_exposure_uses_notional_once`
- Suite eseguita: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/test_agent_step6.py -q` con 71 test passati.
- Compile backend: `backend/.venv/Scripts/python.exe -m compileall backend/app -q`.
- Typecheck app: `npx tsc --noEmit -p tsconfig.app.json`.
- Typecheck dashboard: `npx tsc --noEmit -p dashboard/tsconfig.json`.
- Dopo il refinement UI, ripetuti i typecheck app e dashboard.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno. La correzione e' rimasta limitata a precisione prezzo, formatter e fallback dettaglio spot.

## 5. QUESTIONI APERTE

- Se un vecchio record ha SL/TP gia' salvati come zero e non ha snapshot grafico con livelli validi, quei livelli non sono ricostruibili con certezza dal solo DB. Le nuove posizioni manterranno i livelli corretti.

## 6. STATO DELIVERABLE

- Deliverable completato e verificato localmente.
