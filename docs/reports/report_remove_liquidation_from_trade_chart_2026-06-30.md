# Report - Rimozione liquidazione dai grafici trade

## 1. COSA È STATO FATTO

- Rimossa la linea del liquidation price dai grafici trade Perp in dashboard web.
- Rimossa la linea del liquidation price dai grafici trade Perp nella tab mobile Agente.
- Mantenuto il liquidation price nei dettagli/risk levels del trade.

## 2. COME È STATO FATTO

- Escluso `liquidation_price` dai livelli usati per calcolare la scala Y del grafico.
- Rimosso il rendering della linea orizzontale `Liq` e la relativa legenda.
- Non sono stati modificati contratti API, backend o salvataggio degli snapshot.

## 3. COSA È STATO VERIFICATO

- `npm exec tsc -- -b --pretty false`
- `npx tsc -p dashboard/tsconfig.json --noEmit`
- `rg` mirato conferma che nei grafici restano solo Entry, Exit, SL e TP come livelli di scala/linee.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Nessuna.

## 6. STATO DELIVERABLE

- Implementato e verificato.
