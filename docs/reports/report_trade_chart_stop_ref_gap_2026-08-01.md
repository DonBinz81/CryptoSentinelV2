# Report trade chart stop reference gap - 2026-08-01

## 1. COSA E STATO FATTO

- Modificata la linea verticale viola tratteggiata `SL ref` nei grafici dettaglio operazione.
- La linea non attraversa piu' la candela usata come riferimento per lo stop loss.
- Il pallino viola sul prezzo stop loss resta visibile e invariato.

## 2. COME E STATO FATTO

- In `src/components/AgentTab.tsx` e `dashboard/src/App.tsx` il marker `SL ref` viene disegnato in due segmenti verticali.
- I segmenti partono dal bordo superiore/inferiore del grafico e si fermano prima del range high/low della candela di riferimento.
- E' stato aggiunto un piccolo gap di 3px sopra e sotto la candela per lasciare leggibile wick e corpo.

## 3. COSA E STATO VERIFICATO

- Typecheck app mobile/web con `npx tsc --noEmit -p tsconfig.app.json`.
- Typecheck dashboard con `npx tsc --noEmit -p dashboard/tsconfig.json`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno. La modifica e' solo visuale e non cambia dati, livelli, stop loss o calcoli backend.

## 5. QUESTIONI APERTE

- Nessuna.

## 6. STATO DELIVERABLE

- Deliverable completato.
