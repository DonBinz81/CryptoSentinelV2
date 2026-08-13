# Report Dashboard Trade History Page Size - 2026-08-02

## 1. COSA È STATO FATTO

Aggiunto nella dashboard un filtro a tendina nelle history Spot e Perp per mostrare 20, 50, 100 trade oppure tutti i trade in una pagina.

## 2. COME È STATO FATTO

La modifica e' stata applicata al componente condiviso `TradeHistoryTable`, quindi vale per entrambe le viste senza duplicare logica. Il filtro viene applicato dopo ricerca, lato, direzione, stato e motivo chiusura.

## 3. COSA È STATO VERIFICATO

Verificata la compilazione TypeScript della dashboard. Nessun endpoint backend e' stato modificato.

## 4. SCOSTAMENTI DAL PIANO

Nessuno.

## 5. QUESTIONI APERTE

Nessuna.

## 6. STATO DELIVERABLE

Deliverable completato lato dashboard.
