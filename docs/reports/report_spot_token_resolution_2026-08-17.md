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

## QUESTIONI APERTE

1. **Coin non mappate non eseguibili sullo spot in live**: `TRX`, `ETC`, `LDO`, `TON`,
   `1INCH`. Vanno risolte a mano e verificate on-chain, mai per ticker. È il prezzo
   consapevole di questa scelta: aggiungere una coin allo spot ora richiede un indirizzo
   curato.
2. La mappa in produzione contiene **49 indirizzi**, tutti verificati on-chain per
   `symbol()`, `decimals()` e presenza di pool.
3. Lo stesso principio non è ancora applicato al **perp**, che non usa indirizzi on-chain:
   lì l'identificazione passa dal simbolo di mercato Aster, che è univoco per venue.

## STATO DELIVERABLE

Completo, deployato e verificato. Commit `1d58803`. Non pushato.
