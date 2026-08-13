# Report Step 9 - Testing

## 1. COSA È STATO FATTO

- Aggiunti test mancanti per risk engine: daily loss limit, max positions, guardia portfolio sopra 1 USD e cap size via rischio massimo.
- Aggiunti test mancanti per meta-controller: fallback dry-run su timeout Claude e decisione `reduce`.
- Aggiunti test kill switch soft/hard.
- Aggiunto test di ciclo completo dry-run Perp, oltre al ciclo Spot già presente.
- Implementata nel loop lento la regola hardcoded "minimo 1 trade/giorno": check alle 20:00 UTC e retry fino alle 23:30 UTC.
- Aggiunto test `test_heartbeat_triggers_at_20utc`.
- Aggiunto conteggio trade Spot giornalieri in `SpotTradeRepository.count_since`.
- Predisposto script manuale `backend/scripts/register_competition.py` per chiamare `twak compete register --json` tramite il client TWAK esistente.
- Consolidamento post-review: aggiunta watchlist operativa AI selezionabile da mobile app. La lista eligible resta solo il perimetro consentito; l'agente lavora solo sui token selezionati dall'utente.
- Aggiornato `docs/PROJECT_STRUCTURE.md`.

## 2. COME È STATO FATTO

- Il daily heartbeat è dentro `AgentService.slow_tick`, quindi non è più solo predisposto o documentato.
- Il conteggio qualificazione considera solo `SpotTrade`, coerente con la conferma organizzatori del 18 giugno: solo Spot conta per il ranking Track 1.
- La finestra è hardcoded: se non esiste almeno un trade Spot nel giorno UTC, dalle 20:00 UTC il loop tenta un heartbeat trade e ritenta a ogni slow tick fino alle 23:30 UTC.
- In `dry_run`, il heartbeat crea un trade Spot preparato da 1 USD, verificabile in DB.
- Fuori da `dry_run`, il loop non inventa route/token address: se `heartbeat_trade_from_asset`, `heartbeat_trade_to_asset` e `heartbeat_trade_amount_in_atomic` non sono configurati, blocca con `heartbeat_trade_live_route_not_configured` e continua a ritentare nella finestra.
- Lo script registrazione competizione è esplicito e manuale: richiede `--confirm`, chiede password TWAK con input nascosto e non viene mai eseguito automaticamente.
- La watchlist AI è persistita in `RuntimeState` tramite `backend/app/agent/watchlist.py`, validata contro `Settings.eligible_tokens` e modificabile solo via endpoint admin-only.
- `GET /api/v1/agent/watchlist` espone eligible universe e token selezionati; `PUT /api/v1/agent/watchlist` aggiorna la selezione operativa senza esporre segreti.
- La tab mobile Agente include la nuova vista `Coins` con token tradabili, token selezionati e ricerca. Il toggle AI sulle card usa la stessa watchlist backend: arancione significa token effettivamente passato all'agente.
- `AgentService.slow_tick` usa la watchlist selezionata per costruire payload `ASSETUSDT` Spot/Perp e valutare i signal engine; con watchlist vuota resta idle/fail-closed.
- Aggiunto warm-up OHLCV storico per la watchlist AI: all'avvio backend e quando vengono aggiunti token, il backend scarica subito klines 5m storiche Binance Spot/Futures e popola la cache letta da Data Coverage e signal engine. Le richieste sono serializzate con lock e cadenza minima per evitare burst sul rate limit.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py backend/tests/unit/test_perp_providers.py backend/tests/unit/test_execution_wallets.py -q` completato con `28 passed`.
- `backend\.venv\Scripts\python.exe -m py_compile backend/app/agent/service.py backend/scripts/register_competition.py backend/app/persistence/repositories/trades.py backend/tests/unit/test_agent_step6.py` completato con successo.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests -q` completato con `119 passed, 2 failed`.
- I 2 failed sono esattamente il debito HMAC TWAK pre-esistente in `backend/tests/unit/test_execution_layer.py`:
  - `test_twak_hmac_matches_documented_wire_format`
  - `test_twak_hmac_supports_current_sdk_wire_format`
- Dopo la migrazione nuovo wallet TWAK, i test HMAC sono stati aggiornati al formato SDK attuale e la suite backend completa passa con `124 passed`.
- Dopo il consolidamento watchlist AI:
  - `python -m py_compile backend/app/agent/watchlist.py backend/app/agent/service.py backend/app/api/routes/agent.py` completato con successo.
  - `npm run build` completato con successo.
- Dopo il warm-up storico:
  - `python -m py_compile backend/app/agent/ohlcv_warmup.py backend/app/api/routes/agent.py backend/app/main.py backend/tests/unit/test_agent_step6.py` completato con successo.
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py -q` completato con `21 passed`.

## 4. SCOSTAMENTI DAL PIANO

- La registrazione competizione non è stata eseguita automaticamente, come richiesto. È stato predisposto uno script manuale esplicito.
- Il heartbeat live non esegue un trade se non è configurata una route Spot esplicita; questa scelta evita trade ambigui o fuori universo eligible.
- La suite completa ora riporta `119 passed, 2 failed`; il numero passato è maggiore rispetto al valore iniziale perché sono stati aggiunti test Step 9.
- La selezione mobile AI è stata resa operativa oltre il piano iniziale: non abilita tutti gli eligible, ma solo la watchlist scelta dall'utente. Questo riduce rischio e rende chiaro quali asset vengono scansionati.

## 5. QUESTIONI APERTE

- Configurare una route heartbeat live Spot concreta prima della trading window se si vuole che il retry 20:00-23:30 UTC possa produrre un trade reale fuori dry-run.
- Eseguire manualmente la registrazione competizione quando wallet, gas e timing gara sono confermati.
- Il blocco TWAK 403 è stato risolto dopo Step 9 con migrazione a nuova API key + nuovo wallet TWAK + reinit; vedere `docs/reports/report_twak_wallet_migration.md`.
- Eseguire un test end-to-end con backend riavviato: inserire admin token in app, selezionare token dalla scheda Agente > Coins, verificare persistenza dopo restart e osservare `slow_tick` su watchlist non vuota.

## 6. VERIFICHE TECNICHE

| Verifica | Esito |
|---|---|
| Risk engine daily loss, max positions, $1 guard, size cap | Passata |
| Meta-controller timeout/reduce | Passata |
| Kill switch soft/hard | Passata |
| Daily heartbeat 20:00 UTC | Passata |
| Dry-run Spot/Perp cycle | Passata |
| Competition registration helper | Predisposto, non eseguito |
| Watchlist AI operativa mobile/backend | Py compile + frontend build passati; E2E runtime da verificare |
| Warm-up OHLCV watchlist | Test unitario passato; popola cache Data Coverage con 288 candele 5m |
| Full backend suite | 124 passed dopo migrazione nuovo wallet TWAK |

## 7. STATO DELIVERABLE

Step 9 implementato in forma parziale-operativa e consolidato con watchlist AI operativa. Non procedere a Step 10 senza approvazione del revisore.
