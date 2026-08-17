# Report — Guard di liquidità attivato e TON rinominata GRAM (2026-08-17)

## COSA È STATO FATTO

Due interventi nati dalla stessa verifica, entrambi su presidi che sembravano funzionare e
non funzionavano.

1. **Il `liquidity_guard` ora ha un dato da valutare.** La soglia di 50.000 $ esisteva nel
   Risk Manager e nel setup, ma nessun segnale valorizzava `liquidity_usd`: restava sempre
   `None`, la condizione era sempre falsa e il guard non è mai scattato.
2. **`TON` è stata rinominata `GRAM`.** Toncoin è stata ribattezzata, e il ticker `TON`
   appartiene oggi a Tokamak Network — un'altra moneta.

## COME È STATO FATTO

### Liquidità

La profondità viene misurata **sull'hop che il router userebbe davvero**: `build_path` passa
sempre per WBNB, quindi una coppia diretta molto liquida che non tocchiamo mai non è
liquidità utilizzabile. Il caso reale che lo dimostra è GRAM: pool diretta con USDT da
25.800 $, ma solo **659 $** sulla coppia con WBNB, l'unica che il router attraversa.

Il valore è convertito in dollari con il prezzo di BNB **ricavato dalla pool quote/WBNB**,
quindi tutto on-chain e senza dipendere da un feed esterno.

Tre garanzie perché non diventi un fermo macchina: su rete di test ritorna `None` (gli
indirizzi curati sono di mainnet); una lettura fallita ritorna `None` e **non zero**, perché
zero bloccherebbe ogni trade; il valore resta in cache un'ora.

### Rinomina

Sotto il nome vecchio la coin risultava non quotata su Aster e riceveva **klines ferme**:
futures a volume zero, spot con l'ultima candela di quasi due mesi prima. Il motore
valutava segnali su dati morti. Come `GRAM` il mercato è vivo (`GRAMUSDT` su Aster e su
Binance) e la coin sta intorno alla **posizione 25** invece che alla 841.

L'indirizzo BSC non cambia — il token è lo stesso, `Wrapped TON Coin` — cambia solo la
chiave nella mappa. Il conteggio degli eligible resta **150**: un simbolo sostituito.

## COSA È STATO VERIFICATO

**Suite completa sulla VPS**: **292 passed, 2 failed, 2 skipped** (le due preesistenti).
**Golden test invariato.**

**Misure reali su mainnet**, coincidenti con quelle fatte a mano contratto per contratto:

```
CAKE 7.302.291 · BTC 1.293.139 · ETH 1.249.273 · TRX 151.570
1INCH 791 · GRAM 659 · ETC 41                    (dollari)
```

Con la soglia attuale passerebbero le prime quattro.

**Rinomina verificata in produzione**: `GRAM` risulta `available` sul perp, rank **#25**,
eligible sempre a 150, master a 66, watchlist perp a 26. Zero errori dopo il riavvio.

Il file `configs/eligible_tokens.yaml` in produzione **combacia ora per hash con il repo**:
conteneva CRLF da un vecchio deploy fatto con `git show`, incoerenza risanata da questo
rilascio.

## SCOSTAMENTI DAL PIANO

1. La rinomina non era prevista: è emersa verificando perché il rank di `TON` risultasse
   #838. Non era un difetto del ranking — il numero era corretto per quel ticker — ma il
   ticker non era più la nostra moneta.
2. `ETC` e `1INCH` sono state rimosse dalla watchlist spot prima di questo lavoro: pool da
   41 $ e 791 $ le rendono non tradabili.

## QUESTIONI APERTE

1. **Il guard non produce effetti finché si resta su testnet**: la misura è `None` e il
   guard resta silente esattamente come prima. Si attiva col passaggio a mainnet.
2. **Quattro coin in watchlist spot non hanno indirizzo in mappa** — `LDO`, `WLFI`, `U`,
   `LUNC` — quindi in live verrebbero saltate con `spot_token_not_mapped`.
3. **`GRAM` sullo spot resta poco liquida** (659 $ sul percorso del router): è in watchlist
   perp, non spot.
4. La disponibilità mostrata nel setup **non tiene ancora conto della soglia**: una coin con
   pool da 41 $ appare `available`. Ora che la misura esiste, agganciarla alla disponibilità
   è un passo breve.

## STATO DELIVERABLE

Rinomina: completa, deployata e verificata (commit `7db3bea`).
Guard di liquidità: **committato (`a9ca68d`) ma non ancora deployato**, in attesa di
approvazione esplicita perché tocca il percorso che porta all'apertura di una posizione.
