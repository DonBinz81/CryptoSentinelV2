# Report - Agent tab request pressure fix

## 1. COSA È STATO FATTO

- Ridotta la pressione della tab mobile Agente sugli endpoint backend lenti.
- Aggiunta deduplica in memoria delle richieste `trade-detail` già in corso.
- Impediti refresh completi e refresh leggeri sovrapposti.
- Spostato il caricamento `/api/v1/execution/wallets` fuori dal refresh generale: ora viene richiesto solo nella vista Wallet e ogni 5 minuti.
- Portato il refresh leggero da 5 a 15 secondi.

## 2. COME È STATO FATTO

- In `src/components/AgentTab.tsx` è stato aggiunto `tradeDetailInflight`, una mappa `tradeId:mode -> Promise`, così click, prefetch e refresh riusano la stessa richiesta invece di aprirne più copie.
- `loadActiveTradeDetail` usa la cache anche per i dettagli base senza grafico completo, evitando nuove chiamate quando il dettaglio testuale è già disponibile.
- `refreshInFlightRef` e `fastRefreshInFlightRef` bloccano cicli concorrenti.
- Il refresh veloce aggiorna solo Spot, Perp e Global; non ricarica più dettagli trade.
- Il wallet viene aggiornato con un effetto dedicato legato al pane `wallet`.

## 3. COSA È STATO VERIFICATO

- Eseguito `npm run build` con esito positivo.
- Verificato il diff per confermare che la modifica è confinata al frontend mobile agente e alla documentazione.
- La diagnosi iniziale è stata basata su `logs/backend.log`, dove le route `/api/v1/views/*`, `/api/v1/views/trade-detail/*` e `/api/v1/execution/wallets` risultavano spesso completate dopo 80-120 secondi e ripetute in parallelo.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno scostamento strategico: non sono state modificate logiche trading, risk management, execution provider o backend configuration.
- È stata ridotta la frequenza del refresh leggero per stabilità operativa dell'app.

## 5. QUESTIONI APERTE

- Va verificato su dispositivo reale/APK che la ruota dei dettagli non resti più bloccata durante rallentamenti RPC/CEX.
- Se i log mostrassero ancora endpoint `trade-detail` oltre timeout, il passo successivo sarebbe cache server-side o risposta immediata del backend senza enrichment esterno.

## 6. STATO DELIVERABLE

- Deliverable completato a livello codice e build.
- Verifica runtime su app reale ancora consigliata.
