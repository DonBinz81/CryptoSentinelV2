# Report Allineamento Conteggi History Trade - 2026-08-02

## 1. COSA È STATO FATTO

Risolto il disallineamento tra contatore trade mostrato in app e history trade mostrata in dashboard per Spot e Perp.

## 2. COME È STATO FATTO

La causa era nella view backend: `spot_view` e `perp_view` caricavano gli ultimi 100 record grezzi e poi filtravano `prepared/pending`, mentre `trade_count` contava tutti i trade chiusi con `pnl_usd`. Sono stati aggiunti metodi repository dedicati per leggere direttamente tutti i trade chiusi con PnL e la view ora usa lo stesso criterio del contatore.

E' stata anche normalizzata la precisione Decimal dell'entry Perp letta dalle posizioni storiche per evitare artefatti SQLite nella history.

## 3. COSA È STATO VERIFICATO

Verificato sul DB locale che Spot ora restituisce `trade_count=28` e `history=28`, Perp `trade_count=105` e `history=105`. Eseguiti test backend persistence e typecheck dashboard.

## 4. SCOSTAMENTI DAL PIANO

Nessuno.

## 5. QUESTIONI APERTE

Nessuna.

## 6. STATO DELIVERABLE

Deliverable completato: app e dashboard ricevono history e contatori coerenti per mercato.
