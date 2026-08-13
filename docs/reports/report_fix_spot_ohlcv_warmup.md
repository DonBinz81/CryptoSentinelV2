# Report fix Spot OHLCV warm-up

## 1. COSA È STATO FATTO

- Verificato che `SpotMomentumSignal` richiede almeno 50 candele OHLCV valide.
- Verificato che il loop lento attuale non scarica né accumula OHLCV per gli asset eligible all'avvio: è ancora un placeholder con `no_watchlist_scanner_configured`.
- Aggiunto warm-up esplicito nello Spot signal: quando il payload non contiene almeno 50 candele, prova a scaricare 100 klines 5m da Binance spot per il singolo asset valutato.
- Aggiunti log `spot_ohlcv_warmup_loaded`, `spot_ohlcv_warmup_failed` e `spot_ohlcv_warmup_skipped`.
- L'errore `insufficient_ohlcv_history` ora include `candle_count` e `required_candles`.

## 2. COME È STATO FATTO

- Il warm-up usa il feed Binance klines già specializzato nel signal engine, con `market="spot"` e simbolo default `{asset}USDT`.
- La chiamata può essere personalizzata passando `symbol`, `binance_symbol` o `quote_asset` nel payload.
- Non è stato introdotto uno scan all'avvio di tutti i token eligible, perché sarebbe lento e fragile; il warm-up è lazy per il singolo asset valutato.

## 3. COSA È STATO VERIFICATO

- Test unitari mirati su signal, API payload e eligible config.

## 4. SCOSTAMENTI DAL PIANO

- Il loop lento resta predisposto e non implementa ancora uno scanner completo dei 100-200 token eligible.
- Il warm-up è per primo segnale/asset, non globale all'avvio.

## 5. QUESTIONI APERTE

- Step successivo: implementare scanner/watchlist del loop lento se serve generare segnali autonomi senza payload manuale.
- Alcuni token eligible potrebbero non avere coppia Binance spot `{asset}USDT`; in quel caso va passato `symbol` esplicito o aggiunto mapping.

## 6. STATO DELIVERABLE

Fix implementato e pronto per verifica dopo riavvio backend.
