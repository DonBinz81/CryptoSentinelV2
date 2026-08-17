# Report — Visibilità dei pair per venue nel setup (2026-08-17)

## COSA È STATO FATTO

Il setup mostra ora, per ogni coin della master watchlist, se è realmente eseguibile sulla
venue del mercato: **Spot → PancakeSwap**, **Perp → Aster**. Una coin non quotata non è più
selezionabile e il motivo è visibile.

Tre stati, esposti dal backend e mai calcolati nella UI:

| stato | significato | effetto in UI |
|---|---|---|
| `available` | la venue pubblica quel mercato | selezionabile |
| `unavailable` | la venue ha risposto e non lo elenca | non selezionabile, barrato, col motivo |
| `unknown` | non siamo riusciti a verificarlo | badge "Non verificato", selezione consentita |

`unknown` non blocca: si produce quando il limite è **nostro** (RPC irraggiungibile, indirizzo
non verificato), non della venue. Bloccare su `unknown` avrebbe reso la watchlist non
configurabile durante un disservizio di rete.

Nessuna lista di pair è codificata: se domani Aster quota COMP, compare senza toccare il
codice e senza una nuova APK.

## COME È STATO FATTO

**Perp — `exchangeInfo` di Aster.** Una sola richiesta pubblica e non firmata copre tutti i
simboli; si filtrano i mercati `PERPETUAL` in stato `TRADING` e si tiene l'insieme dei
`baseAsset`. Riusato il client esistente (`venues/aster/client.py`), zero righe nuove: le
credenziali restano vuote, perché quell'endpoint non le richiede.

**Spot — `getPair` sulla Factory PancakeSwap, non `getAmountsOut`.** Scelta tecnica dirimente:
il router **reverte** quando la pool non esiste, e `MultiRpcClient` conserva solo il *tipo*
dell'eccezione dopo aver ritentato su ogni endpoint (`rpc.py:74`) — "pool assente" e "rete
giù" sarebbero risultati indistinguibili, cioè `unavailable` e `unknown` confusi tra loro.
La Factory risponde invece con l'indirizzo zero, senza revert. Il path verificato è quello
che il motore userebbe davvero (`build_path`), hop per hop.

**Spot — solo indirizzi curati.** La disponibilità spot si calcola **esclusivamente** per i
simboli presenti in `SPOT_TOKEN_MAP`. La risoluzione per ticker via CMC non è usata qui:
vedi QUESTIONI APERTE.

**Cache**: riusata `TTLCache` esistente (`data/market_data/cache.py`), nessuna astrazione
nuova. Un'ora sui successi, 60 secondi sui fallimenti, così un disservizio non congela ogni
simbolo su `unknown` per un'ora intera.

**API**: nessun endpoint nuovo. Campo `availability` aggiunto alle GET già chiamate dall'app
(`/watchlist/spot`, `/watchlist/perp`). L'helper non solleva mai: se il servizio fallisce la
watchlist resta leggibile e il client ricade su `unknown`.

### File

| file | natura |
|---|---|
| `backend/app/execution/venue_availability.py` | **nuovo** — servizio, tre stati, cache |
| `backend/app/execution/providers/pancakeswap_provider.py` | `factory_address`, `encode_get_pair`, `decode_address`, `pair_address` |
| `backend/app/core/config.py` | due indirizzi Factory V2 (mainnet/testnet), con default |
| `backend/app/api/routes/agent.py` | campo `availability` sulle due GET watchlist |
| `src/services/agentApi.ts` | tipi `VenueAvailability`, `WatchlistAvailability` |
| `src/components/AgentTab.tsx` | `TokenToggle` con stato venue; blocco selezione |
| `backend/tests/unit/test_venue_availability.py` | **nuovo** — 11 test |
| `backend/tests/unit/test_execution_providers.py` | 2 test sulla lettura della Factory |

## COSA È STATO VERIFICATO

**Suite completa sulla VPS** in copia isolata sotto `/tmp`: **275 passed, 2 failed, 2 skipped**.
Le due failure sono le preesistenti note (`test_meta_controller_reduce`,
`test_support_ticket_thread_and_admin_status_flow`). Baseline 260 → +15 (13 di questo lavoro,
2 del blocco "Aster wallet" non committato già presente nel working tree).

**Golden test invariato**: `test_position_lifecycle_golden.py` non è stato toccato e passa.
Nessun file di strategia, ratchet, Smart SL, risk manager o `service.py` è stato modificato.

**Indirizzi Factory verificati on-chain**, non presi da memoria: `router.factory()` restituisce
`0xcA143Ce…0c73` su mainnet e `0x6725F30…7a17` su testnet, esattamente i default inseriti.

**`getPair` verificato sul contratto vero**: pool esistente → indirizzo non nullo; pool
inesistente → indirizzo zero **senza revert**, che è la premessa dell'intero design.

**Prova end-to-end contro venue reali** (Aster pubblico + BSC mainnet):

```
BTC    spot=available                                                 perp=available
CAKE   spot=available                                                 perp=available
FAKE   spot=unavailable  nessuna pool PancakeSwap per questo pair     perp=unavailable
COMP   spot=unknown      indirizzo BSC non verificato per questo simbolo perp=unavailable
TON    spot=unknown                                                   perp=unavailable
BABYDOGE spot=unknown                                                 perp=unavailable
```

Tutti e tre gli stati sono stati prodotti da venue reali, non simulati.

**Riconciliato uno scarto nei conteggi**: il servizio registra 532 dove le note riportavano
537. Non è un errore: Aster pubblica 537 mercati perpetui attivi ma **532 asset distinti**
(BTC ha 3 mercati con quote diverse, ETH 3, SOL 2). Il log ora riporta entrambi i numeri con
nomi espliciti.

**TypeScript**: `npx tsc --noEmit` pulito. Nessuna build frontend eseguita in locale.

## CORREZIONE POST-DEPLOY — rete di test (stesso giorno)

Provando in produzione una `SPOT_TOKEN_MAP` popolata con 49 indirizzi verificati, **tutti**
risultavano `unavailable`, BTC e CAKE compresi, che hanno pool accertate a mano.

Causa: la produzione ha `bsc_network=testnet`, quindi la sonda interrogava la Factory di
testnet (`0x6725F30…7a17`), dove i token mainnet non esistono. Non è una risposta neutra:
`unavailable` **blocca la selezione in UI**, quindi popolare la mappa avrebbe sbarrato 49
coin perfettamente operabili.

Corretto: quando la rete configurata è di test, lo spot risponde `unknown` con motivo
esplicito — mai `unavailable`. Gli indirizzi curati sono di mainnet e confrontarli con una
factory di testnet non produce un'informazione valida. Aggiunto
`test_spot_on_testnet_is_unknown_not_unavailable`.

Suite dopo la correzione: **276 passed, 2 failed preesistenti, 2 skipped**.

È lo stesso principio già applicato altrove nel modulo: un limite di configurazione nostro
non deve mai assomigliare a un mercato assente sulla venue.

## SEGUITO — il router consulta la disponibilità (stesso giorno, commit `b1d0fce`)

Il punto lasciato aperto è stato chiuso: `resolve_entry_venue` consulta ora il servizio di
disponibilità e rifiuta i pair che la venue non quota. La disponibilità mostrata nell'app e
quella applicata a runtime sono finalmente **la stessa cosa**.

Il controllo vale **anche in dry-run**, di proposito: una simulazione che apre posizioni che
la venue reale rifiuterebbe non è la prova generale di nulla.

Tre garanzie perché non diventi un fermo macchina:

- solo `unavailable` blocca — `unknown` è il nostro punto cieco, non un mercato assente;
- se il controllo stesso fallisce, l'apertura procede: un check rotto non deve fermare il
  trading;
- riguarda solo il perp; lo spot ha un percorso diverso ed è rimasto intatto.

`resolve_entry_venue` è diventato `async` (unico chiamante, già in contesto asincrono).

**Impatto misurato sulla watchlist reale prima del deploy**: 22 coin su 22 continuano ad
aprire, nessuna bloccata; `COMP`, non quotata su Aster, viene rifiutata con
`venue_unavailable`. Suite **287 passed**, 2 failed preesistenti, golden test invariato.
Dopo il deploy: servizio `active`, zero errori, zero `venue_unavailable` inattesi.

## SCOSTAMENTI DAL PIANO

1. **Sonda spot cambiata**: previsto `getAmountsOut`, usato `getPair` sulla Factory. Motivo
   nella sezione COME. Ha richiesto due indirizzi in `Settings`, verificati on-chain.
2. **Spot limitato agli indirizzi curati**: il piano iniziale prevedeva la risoluzione
   automatica. Scartata dopo la verifica descritta sotto.
3. **`unknown` non blocca**, contrariamente alla prima formulazione della richiesta:
   decisione presa esplicitamente per non rendere il setup inutilizzabile durante un
   disservizio.
4. **Le coin già selezionate ma non disponibili restano cliccabili**: disabilitarle le
   avrebbe rese non rimuovibili dall'app, bloccando 1INCH, COMP, TON e BABYDOGE nella
   watchlist perp per sempre. Sono barrate e segnalate, ma si possono togliere.
5. **PUT non irrigidite**: rifiutare lato server i pair non disponibili avrebbe fatto fallire
   *ogni* salvataggio perp finché quelle quattro coin restano selezionate.
6. **Dashboard non toccata**: espone le funzioni watchlist (`dashboard/src/api.ts:346-361`)
   ma nessun componente le usa — non esiste lì una UI di selezione coin.

## QUESTIONI APERTE

1. **🔴 Risoluzione indirizzo per ticker inaffidabile — fuori da questo step, ma sul percorso
   live.** `CMCProvider.resolve_contract_address` interroga CMC per simbolo e prende il primo
   contratto BEP20 trovato. Per `BTC` CMC restituisce **13 monete** e il primo match è
   **"Bitcoin AI"** (`0xf22aac87…0854`), non BTCB. La stessa funzione alimenta
   `_build_spot_swap_params` (`agent/service.py:2579`): in spot live, con `SPOT_TOKEN_MAP`
   vuota, si comprerebbe il token sbagliato. Oggi non morde perché siamo in dry-run.
   Va aperto un blocco dedicato prima del live.
2. **Copertura spot dipendente da `SPOT_TOKEN_MAP`**: i simboli non mappati restano `unknown`.
   È una scelta, non un difetto: meglio "non so" che un ✓ su un contratto sbagliato.
3. **Il router non consulta ancora il servizio**: `resolve_entry_venue` guarda solo
   `execution_mode`. La UI resta quindi informativa e `venue_unavailable` non viene ancora
   emesso per un pair non quotato. È il prossimo passo naturale e tocca il percorso di
   apertura: deliberatamente rinviato.
4. **Nessuna copertura automatica sulla regola UI**: il progetto non ha un runner di test
   frontend (né vitest né jest in `package.json`). Il blocco della selezione è verificato per
   ispezione e via `tsc`. Introdurre un framework di test era fuori perimetro.

## STATO DELIVERABLE

Completo per la parte richiesta: dato affidabile, esposto, selezione impedita in UI.
Non deployato e non pushato. Nessun ordine, firma, testnet o `AsterPerpVenue` implementato:
il blocco resta interamente read-only.
