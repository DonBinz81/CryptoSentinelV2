# Report - Liquidazione Perp in dettagli e grafici

## 1. COSA È STATO FATTO

- Aggiunto `liquidation_price` al dettaglio trade Perp.
- Aggiunto `liquidation_price` ai payload dei grafici live e degli snapshot salvati alla chiusura.
- Aggiornate dashboard web e tab mobile Agente per disegnare la linea di liquidazione e mostrare il valore nei dettagli.
- Aggiornata la documentazione operativa Perp e la struttura progetto.

## 2. COME È STATO FATTO

- Il backend riusa la stima già salvata su `PerpPosition`, derivata da entry, leva e direzione.
- Gli snapshot trade includono il valore solo per il mercato Perp.
- I client TypeScript hanno il nuovo campo opzionale su `TradeDetail` e `TradeChart`.
- I grafici includono il livello nella scala prezzi, così la linea resta visibile anche fuori dal range delle candele.

## 3. COSA È STATO VERIFICATO

- Verificata la presenza del campo nei punti backend e frontend modificati.
- `backend\.venv\Scripts\python.exe -m py_compile backend/app/api/routes/views.py backend/app/agent/service.py`
- `npm exec tsc -- -b --pretty false`
- `npx tsc -p dashboard/tsconfig.json --noEmit`
- `git diff --check`

## 4. SCOSTAMENTI DAL PIANO

- Nessuno scostamento funzionale: la liquidazione è stata trattata come dato informativo, non come nuovo trigger di uscita.

## 5. QUESTIONI APERTE

- La formula corrente è una stima semplificata e non include maintenance margin o regole specifiche della venue.
- Per il live trading reale andrà sostituita o affiancata dal liquidation price restituito dal provider/venue.

## 6. STATO DELIVERABLE

- Implementato.
- Verificato con controlli mirati di sintassi/tipi.
