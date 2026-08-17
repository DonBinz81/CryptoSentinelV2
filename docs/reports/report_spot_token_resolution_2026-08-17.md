# Report — Indirizzi token spot: via la risoluzione per ticker (2026-08-17)

## COSA È STATO FATTO

L'indirizzo BSC del token, per l'esecuzione spot in live, viene ora **solo** dalla mappa
curata `SPOT_TOKEN_MAP`. La risoluzione per ticker attraverso il provider market data, che
era il ripiego quando un simbolo non risultava mappato, è stata **rimossa**.

Un simbolo non mappato non risolve alcun indirizzo e l'operazione viene saltata con
`spot_token_not_mapped` — un percorso che esisteva già e non è stato aggiunto per l'occasione.

## COME È STATO FATTO

Il difetto era in `_resolve_token_address` (`agent/service.py`): mappa curata, e in mancanza
di essa `CMCProvider.resolve_contract_address`, che interroga il provider **per simbolo** e
prende il primo contratto BEP20 trovato.

Interrogato davvero con la nostra chiave, il simbolo `BTC` restituisce **13 monete** e il
primo match è **«Bitcoin AI»** (`0xf22aac87…0854`), non BTCB.

**La difesa ovvia non funziona.** Verificato leggendo i contratti on-chain:

```
Bitcoin AI (l'impostore)   symbol() = 'BTC'
BTCB (quello vero)         symbol() = 'BTCB'
```

Un controllo del tipo «leggi `symbol()` e confronta col ticker» avrebbe **tenuto l'impostore
e scartato la moneta giusta**. Per questo la risoluzione per ticker non è stata messa in
sicurezza ma eliminata: non è un difetto di implementazione, è il concetto a non reggere.

Rimossi anche il resolver CMC (`_token_resolver`) e il parametro `token_resolver` del
costruttore, rimasti senza alcun uso.

### File

| file | natura |
|---|---|
| `backend/app/agent/service.py` | `_resolve_token_address` legge solo la mappa; via resolver, parametro, import e sentinella |
| `backend/tests/unit/test_agent_step6.py` | il test sulla risoluzione via CMC sostituito da due: rifiuto dei non mappati e uso della mappa |

## COSA È STATO VERIFICATO

**Suite completa sulla VPS**: **288 passed, 2 failed, 2 skipped** — le due failure sono le
preesistenti note. **Golden test invariato**: nessun valore economico toccato.

**Nessun effetto sul dry-run**, verificato nel codice e in produzione. Il percorso modificato
vive solo nel ramo live (`agent/service.py`: `if execution_mode == "dry_run"` porta a
`_simulate_trade`, e `_build_spot_swap_params` sta nel ramo successivo). Dopo il deploy lo
spot continua a decidere regolarmente (ZIL, 1INCH, SFP alle 21:47), 1 posizione aperta,
6 trade nella giornata.

Deploy verificato per hash prima e dopo, backup in
`/opt/cryptosentinelv2/backups/predeploy_20260817_214724`, servizio `active`, zero errori.

## SCOSTAMENTI DAL PIANO

Nessuno. Il lavoro era stato descritto e approvato in questi termini; la verifica su
`symbol()` ha confermato la scelta di rimuovere invece di validare.

## SEGUITO — i quattro indirizzi mancanti, risolti

Delle cinque coin senza indirizzo ne sono state risolte **quattro**, tutte verificate
on-chain; `LDO` no, e non è stata inventata. Mappa in produzione: **da 49 a 53 indirizzi**.

| simbolo | indirizzo | identità dal contratto | pool via WBNB |
|---|---|---|---|
| TRX | `0x85EAC5…4D5B` | `TRON` / `TRX` / 18 dec | 250 BNB |
| TON | `0x76A797…220f` | `Wrapped TON Coin` / `TONCOIN` / 9 dec | 1,09 BNB |
| 1INCH | `0x111111…C302` | `1INCH Token` / `1INCH` / 18 dec | 1,31 BNB |
| ETC | `0x3d6545…3c25E` | `Ethereum Classic` / `ETC` / 18 dec | 0,067 BNB |

**Il caso TRX** merita di essere registrato: nella tokenlist della venue esistono **due**
contratti che dichiarano entrambi `name = "TRON"` e `symbol = "TRX"`, con **decimali
diversi** (18 e 6). Nessun controllo di identità li distingue. Il criterio è stato quale
pool userebbe il router: `build_path` passa sempre da WBNB e mai per la coppia diretta,
quindi conta la profondità contro WBNB — 250 BNB contro 0,09. Sbagliare contratto qui
avrebbe significato anche sbagliare la size di un fattore un milione.

**Metodo**: risoluzione per **slug** e mai per ticker, poi verifica on-chain di `name()`,
`symbol()`, `decimals()` e profondità delle pool. La liquidità è ciò che separa la moneta
vera da un omonimo: il simbolo si copia, la profondità di un mercato no.

Simulazione su mainnet con le Settings reali di produzione: la watchlist spot passa da
**27 disponibili su 33** a **31 su 32**.

## QUESTIONI APERTE

1. **`LDO` resta senza indirizzo**: nessuna fonte curata lo elenca su BSC e il contratto
   candidato non risponde (`name()`, `symbol()`, `decimals()` vuoti, nessuna pool). In live
   non sarà eseguibile sullo spot.
2. **`ETC` e `1INCH` risultano `available` ma con pool irrisorie** (0,067 e 1,31 BNB sulla
   coppia usata dal router). Lo stato è formalmente corretto — la pool esiste — ma a
   fermarli sarebbe il `liquidity_guard` (soglia 50.000 $). È il caso più chiaro a favore
   della **soglia di liquidità nella disponibilità**, finora rimandata.
3. La mappa in produzione contiene **53 indirizzi**, tutti verificati on-chain per
   `symbol()`, `decimals()` e presenza di pool.
4. Lo stesso principio non è ancora applicato al **perp**, che non usa indirizzi on-chain:
   lì l'identificazione passa dal simbolo di mercato Aster, che è univoco per venue.

## STATO DELIVERABLE

Completo, deployato e verificato. Commit `1d58803` (pushato). La mappa a 53 indirizzi e'
applicata in produzione: e' configurazione, non codice, quindi non compare nei commit.
