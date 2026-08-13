# Report - Sostituzione OHLCV pubblico CMC

## 1. COSA È STATO FATTO

- Separata la route pubblica `/api/v1/market-data/ohlcv` dal provider CMC/CoinGecko.
- Aggiunto `ExternalOHLCVService` con Binance klines spot come sorgente primaria e fallback CEX già presenti nel feed.
- Mantenuto CMC per latest pricing, market list, search e identity resolution.
- Lasciato `CMCProvider.get_ohlcv` come compatibilità interna/test, ma non più usato dalla route pubblica.

## 2. COME È STATO FATTO

- La route `/ohlcv` risolve l'identità asset tramite `MarketDataRegistry`, poi scarica candele da exchange tramite `ExternalOHLCVService`.
- Il servizio normalizza le candele in `OHLCVBar`, supporta intervalli `5m`, `15m`, `1h`, `4h`, `1d` e mantiene default hourly/daily coerenti con la UI.
- Il contratto risposta OHLCV accetta una sorgente stringa (`binance_klines`) invece del solo enum CMC/CoinGecko.
- Il frontend conserva lo stesso endpoint e cambia solo il tipo del campo `provider` OHLCV a stringa.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m py_compile backend/app/data/ohlcv_sources.py backend/app/api/routes/market_data.py backend/app/data/market_data/base.py backend/app/data/market_data/registry.py backend/app/schemas/market_data.py backend/tests/integration/test_market_data_api.py`
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_market_data_api.py backend/tests/integration/test_market_data_providers.py -q` → 25 passed.
- `npm exec tsc -- -b --pretty false`

## 4. SCOSTAMENTI DAL PIANO

- Nessuno rispetto alla richiesta: CMC resta per i dati Basic, OHLCV paid viene sostituito.

## 5. QUESTIONI APERTE

- Alcuni token potrebbero non avere pair CEX disponibili; in quel caso la route torna lista vuota finché non viene aggiunto un provider/fallback ulteriore.
- Conversione EUR/BTC sui grafici OHLCV è best-effort con cambio latest, non storico per candela.

## 6. STATO DELIVERABLE

- Implementato e verificato.
