# Report Dashboard Analytics

## 1. COSA È STATO FATTO

- Archiviati i dati dry-run simulati esistenti in `ArchivedRun` tramite `backend/scripts/archive_dry_run.py`, con label `pre_500_reset_2026_06_20`.
- Eseguito un secondo run `pre_500_reset_2026_06_20_portfolio_reset` dopo aver esteso lo script per resettare anche `PortfolioState` live a 500 USD.
- Aggiunto sizing dry-run realistico: capitale default 500 USD e blocco trade sotto 7 USD con motivo `below_minimum_trade_size`.
- Estesi gli endpoint read-only per analytics: equity curve, asset breakdown, trade detail, operational stats, decision log e archived runs.
- Estese dashboard e app mobile con metriche PnL, drawdown, equity curve, decisioni, breakdown asset e dettaglio trade.
- Corretto il blocco startup che causava `Failed to fetch` in dashboard: il warm-up OHLCV ora parte in background e non impedisce al backend di aprire la porta API.
- Aggiornati `configs/risk.yaml`, `docs/PROJECT_STRUCTURE.md` e test di regressione.

## 2. COME È STATO FATTO

- `Settings` ora espone `dry_run_capital_usd` e `min_trade_size_usd`, caricati dal loader centrale e dai default funzionali in `configs/risk.yaml`.
- Il risk engine resta autorità sul sizing: se il size calcolato è sotto 7 USD, il trade viene bloccato invece di essere forzato al minimo.
- Il daily heartbeat usa lo stesso minimo operativo da 7 USD.
- I dati simulati storici sono copiati in una riga JSON `ArchivedRun` e rimossi dalle tabelle live; lo stato portfolio viene salvato nell'archivio e riportato al capitale dry-run configurato.
- La dashboard usa una nuova tab `Analytics`; la mobile app mostra solo una sintesi compatta nella tab Global e una schermata dettaglio trade.
- Polling scelto: 45 secondi per dashboard e app mobile, dentro il vincolo 30-60s.
- Il warm-up OHLCV resta automatico ma viene schedulato come task asincrono dopo l'inizializzazione DB, così Uvicorn può completare lo startup e servire health/dashboard.

## 3. COSA È STATO VERIFICATO

- Archiviazione locale eseguita: creati i run `arch_20260620T232457_1f54aabc69` e `arch_20260621T080708_536ff5aea2`.
- Test mirati agent/persistence: `36 passed`.
- Suite backend completa: `127 passed`.
- Build mobile: `npm run build` riuscito.
- Build dashboard: `npm run dashboard:build` riuscito.
- `py_compile` sui moduli backend modificati riuscito.
- Verificato `GET /health/live` su `127.0.0.1:8001`: risposta `status=ok`.
- Verificato `GET /api/v1/views/equity-curve` senza token: risposta HTTP 401, quindi rete/backend raggiungibili.

## 4. SCOSTAMENTI DAL PIANO

- `configs/instance.yaml` non è stato modificato perché è local-only/gitignored e le regole repository vietano di trattare configurazioni locali sensibili come artefatti da ispezionare/committare. I default equivalenti sono stati aggiunti in `configs/risk.yaml`.
- Le statistiche operative sono esposte in forma iniziale read-only; uptime/degraded sono predisposti e non ancora alimentati da metriche storiche persistenti.

## 5. QUESTIONI APERTE

- Verificare su backend reale avviato che la dashboard mostri i nuovi dati live dopo il reset dry-run.
- Valutare una persistenza più ricca per degraded mode, kill switch history e uptime reale.
- Il dettaglio eventi posizione usa i dati disponibili oggi; sequenze avanzate TP1/breakeven/TP2/trailing saranno più complete quando il loop posizioni persisterà ogni evento.

## 6. STATO DELIVERABLE

- Deliverable implementato e verificato localmente.
- Nessuno step successivo avviato.
