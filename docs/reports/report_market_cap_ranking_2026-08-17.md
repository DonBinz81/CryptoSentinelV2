# Report — Coin ordinate per capitalizzazione nel setup (2026-08-17)

## COSA È STATO FATTO

Le tre schede del setup (master, spot, perp) mostrano le coin **ordinate per
capitalizzazione di mercato**, con accanto la **posizione globale** in classifica (`#1` per
BTC). Il dato si aggiorna una volta al giorno.

Le coin fuori dalla copertura non ricevono un numero: finiscono in fondo, in ordine
alfabetico, senza un rank inventato.

## COME È STATO FATTO

**Solo visualizzazione, e non è un dettaglio.** Il motore scansiona le watchlist in
sequenza (`agent/service.py:2259` e `:2267`) e, con un tetto di posizioni aperte, la prima
coin valutata è quella che si prende lo slot. Riordinare le liste **persistite** avrebbe
cambiato quali coin vengono tradate, non solo come sono elencate: le grandi sarebbero
passate sistematicamente davanti alle piccole. L'ordinamento vive quindi nel client; il
backend espone il dato e le liste salvate restano nell'ordine di prima.

**La classifica si legge dall'alto, non simbolo per simbolo.** Il primo tentativo
interrogava il provider con `asset_ids=["BTC","ETH",...]`, ma quel parametro accetta
**identificativi del provider, non ticker**: il risultato erano rank appartenenti ad altre
monete — `UNI #6552`, `DOT #2403`, e BTC ed ETH addirittura senza rank. È la stessa trappola
del bug «Bitcoin AI», in versione silenziosa. Leggendo invece la classifica globale in
ordine di capitalizzazione, un ticker ripetuto si risolve **sempre** sulla moneta più
capitalizzata che lo porta: un omonimo minore non può vincere, per costruzione.

**Robustezza**: se il provider non risponde si continua a servire l'ultima classifica buona
— altrimenti la lista del setup si rimescolerebbe a ogni disservizio — e si riprova dopo 15
minuti invece che dopo un giorno.

**Nessun endpoint nuovo**: il campo `ranking` è stato aggiunto alle GET watchlist esistenti,
come già fatto per `availability`.

### File

| file | natura |
|---|---|
| `backend/app/data/market_data/ranking.py` | **nuovo** — servizio, cache 24 h, fallback |
| `backend/app/api/routes/agent.py` | campo `ranking` sulle tre GET watchlist |
| `src/services/agentApi.ts` | tipi `SymbolRanking`, `WatchlistRanking` |
| `src/components/AgentTab.tsx` | ordinamento nelle tre schede e badge `#rank` |
| `backend/tests/unit/test_market_ranking.py` | **nuovo** — 7 test |

## COSA È STATO VERIFICATO

**Suite completa sulla VPS**: **284 passed, 2 failed, 2 skipped**. Le due failure sono le
preesistenti note. Golden test invariato; nessun file di strategia toccato.

**Dati reali in produzione**, dopo il deploy:

```
perp: 22 coin, tutte con rank
#1 BTC · #2 ETH · #4 BNB · #6 XRP · #7 SOL · #8 TRX · #11 DOGE · #14 ZEC
```

Sulle 66 della master: **64 risolte**, fuori copertura solo `IP` e `WFI`.

**Il difetto della prima versione è stato colto proprio da questa verifica**: senza il
controllo sui dati veri, `UNI #6552` sarebbe finito in produzione con un ordinamento
plausibile all'apparenza.

`npx tsc --noEmit` pulito. Servizio `active`, zero errori nei log.

## SCOSTAMENTI DAL PIANO

1. **Strategia di lettura cambiata in corsa**: previsto un fetch per simboli, sostituito
   dalla lettura della classifica globale, per il motivo descritto sopra. Ha anche
   semplificato il codice: una richiesta invece di N batch.
2. **Provider**: la richiesta parlava del rank di CoinMarketCap, ma il provider attivo in
   produzione è **CoinGecko**. Si usa il provider configurato — il numero è la stessa
   posizione globale per capitalizzazione, e resta coerente col resto dell'app se un domani
   si cambia provider.
3. **Profondità 1000**: scelta che copre 64 delle nostre 66 coin. Andare più a fondo costa
   richieste per nomi che non tradiamo.

## QUESTIONI APERTE

1. **Rate limit del provider**: la classifica richiede 4 pagine da 250. Con un solo
   aggiornamento al giorno non è un problema, ma durante i test ravvicinati CoinGecko ha
   restituito `429` e un test d'integrazione è fallito temporaneamente — poi rientrato senza
   modifiche. Se in futuro l'aggiornamento diventasse più frequente, andrà rivisto.
2. **`IP` e `WFI` senza rank**: fuori dalla top 1000. Compaiono in fondo alla lista.
3. L'ordinamento non tocca la sequenza di scansione del motore: se un domani si volesse che
   anche le aperture seguano la capitalizzazione, è una decisione sulla strategia, da
   verificare col golden test.

## STATO DELIVERABLE

Completo, deployato e verificato in produzione. Commit `a85d6f0`. Nessun push effettuato.
