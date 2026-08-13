# Riduzione consumo CoinMarketCap - 2026-07-15

## 1. COSA È STATO FATTO

- Impostato CoinGecko come provider predefinito per mercato/UI.
- Aggiunto `market_data.alert_provider`, con default CoinGecko, per il checker alert backend.
- Separato il registry alert dal selettore runtime UI/market: gli alert non tornano su CMC se il provider globale viene cambiato.
- Ridotto il budget CMC configurato a 15.000 crediti/mese e il rate limit CMC default a 30 richieste/minuto.
- Mantenuto CMC disponibile per i percorsi agent/resolver e MCP.
- Aggiornati README, backend README, template `configs/instance.example.yaml`, schema API e test.

## 2. COME È STATO FATTO

- `Settings` ora espone `market_data_provider=coingecko`, `market_data_alert_provider=coingecko`, `cmc_monthly_credit_limit=15000` e `cmc_requests_per_minute=30`.
- `MarketDataRegistry` accetta un `active_override` usato da `get_alert_market_data_registry()`.
- `price_checker.py` usa `get_alert_market_data_registry()` quando non riceve un registry iniettato nei test.
- Il selettore `/api/v1/market-data/provider` resta per UI/market e continua a non fare fallback automatici.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_config_eligible_tokens.py backend/tests/unit/test_device_alert_separation.py backend/tests/integration/test_market_data_api.py backend/tests/integration/test_market_data_providers.py -q`
- Esito: `36 passed in 16.99s`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno scostamento funzionale: la modifica segue la strategia proposta di usare CoinGecko per alert/mercato e conservare CMC per agente/resolver.
- Non è stato introdotto fallback automatico tra provider, coerentemente con l'architettura esistente.

## 5. QUESTIONI APERTE

- Se nel database locale/prod esiste già un RuntimeState `market_data_provider=cmc`, il selettore UI/market può restare su CMC finché non viene cambiato via impostazioni admin. Gli alert sono comunque protetti dal nuovo `market_data.alert_provider`.
- La dashboard/app potrebbero mostrare una nota più esplicita sul fatto che il provider UI è separato dal provider alert.

## 6. STATO DELIVERABLE

- Deliverable completato: alert e default mercato sono dirottati su CoinGecko; CMC resta disponibile ma con budget Basic e rate limit più conservativi.
