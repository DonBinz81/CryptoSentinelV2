# App: la cache del dettaglio trade smette di congelare i grafici live

Data: 24 agosto 2026 · Branch: `claude/trade-detail-live-freshness` · Commit: `ca52581`
Perimetro: C (app Android e UI) — verifica richiesta dalla chat B (NOTE/93)

## COSA

La chat B ha corretto lato backend il grafico Smart SL (NOTE/93: snapshot delle
vendite Smart SL, timeout realistico) e ha chiesto di verificare se bastasse da solo,
suggerendo come sospetto principale la loro ipotesi (a): un `chart: null` marcato
come "completo" nella cache dell'app.

## COME

**L'ipotesi (a) non regge**, verificato leggendo il codice: `hasBaseTradeChart`
richiede `candele.length > 1`— un `chart: null` (o vuoto) non soddisfa mai questo
requisito, quindi non può mai risultare "completo". Corretto riportarlo alla chat B
per evitare che inseguano una pista sbagliata.

**La causa vera è un gradino più in basso**, nella definizione stessa di "completo"
per un trade **live**. `needsPostCloseCandles` richiede esplicitamente `!chart.live`
— per un trade ancora aperto è sempre `false`. Quindi `hasCompleteTradeChart` per un
grafico live richiede solo `candele > 1` **e** `stop_reference` presente: niente
altro, e viene soddisfatto quasi al primo caricamento.

Il problema: **tutti e tre** i punti che decidono se rifare la richiesta di rete
trattavano quel "completo" come *definitivo*, esattamente come fanno correttamente
per un trade chiuso (una fotografia immutabile):

- il refresh periodico ogni 45s
- l'apertura della scheda dettaglio
- `loadActiveTradeDetail`, il choke point comune a tutti gli altri tre punti di
  chiamata

Nessuno controllava mai **da quanto tempo** quel dato fosse in cache. Risultato: un
grafico live che aveva soddisfatto "completo" una volta restava fermo lì
indefinitamente (fino al TTL di 10 minuti o all'espulsione LRU della cache) — quindi
un evento successivo (uno Smart SL scattato dopo quel primo caricamento) non arrivava
mai sullo schermo, **anche con il backend già corretto**.

### Il fix

Estratta la cache del dettaglio trade — prima 90 righe inline in `AgentTab.tsx` — in
un modulo dedicato, `src/services/tradeDetailCache.ts`. Aggiunta
`isTradeDetailFresh(detail, updatedAt, now)`: completo **e**, se il trade è live,
aggiornato negli ultimi 60 secondi (`TRADE_DETAIL_LIVE_REFRESH_MS`). Per un trade
chiuso il comportamento non cambia: resta "completo per sempre".

I tre punti sopra sono passati da `hasCompleteTradeChart` (solo struttura) a
`hasCompleteCachedTradeDetail` (struttura + età) — funzione già esistente, ora
davvero consapevole del tempo.

## VERIFICATO

Nel banco di anteprima, con le **funzioni reali** del modulo (non un mock), `now`
iniettato per non dover aspettare 60 secondi veri ogni volta: un grafico live
risulta fresco subito e a 30s, **non più fresco a 61s** (deve rifare la richiesta);
un grafico chiuso resta valido sia a 61s sia a 3 ore. Sei asserzioni, tutte verdi.

`npx tsc -b` (anche contro `main` già aggiornato dal fix backend, `5c4d354`) ed
ESLint puliti: stessi 5 avvisi preesistenti su `AgentTab.tsx`, nessuno nuovo.

## SCOSTAMENTI

- La soglia di 60s per un trade live è una scelta ragionevole ma arbitraria — abbina
  il refresh periodico dell'app (45s) con un margine. Se in pratica risultasse troppo
  o poco reattiva, va rivista.
- Non verificato contro il backend reale con un trade live vero che subisce uno
  Smart SL durante l'osservazione — verifica logica/temporale, non end-to-end.

## DELIVERABLE

- `src/services/tradeDetailCache.ts` — nuovo modulo, `isTradeDetailFresh()`
- `src/components/AgentTab.tsx` — import dal modulo, tre punti di chiamata aggiornati
- Branch `claude/trade-detail-live-freshness`, commit `ca52581`, da `main` `5c4d354`
