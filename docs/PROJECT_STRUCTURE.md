# PROJECT STRUCTURE

Ultimo aggiornamento: 2026-08-09

Documento di riferimento per revisione esterna. Viene aggiornato al termine di ogni step operativo.

## 1. STRUTTURA CARTELLE

```text
CryptoSentinelHackathon/ - repository CryptoSentinel + backend agente BNB Hack Track 1.
|-- AGENTS.md - regole operative permanenti per agenti AI sul repository, incluso path Windows corretto per verifiche backend con `backend\.venv\Scripts\python.exe`.
|-- .github/ - automazioni CI/CD GitHub.
|   `-- workflows/build-apk.yml - workflow GitHub Actions per build APK debug con JDK 21, restore sicuro google-services da secret, artifact prima delle release e deploy Pages su gh-pages solo da main.
|-- android/ - progetto Android Capacitor esistente.
|   |-- app/ - modulo Android principale.
|   |   |-- src/main/AndroidManifest.xml - dichiarazioni activity, provider, permessi e FCM.
|   |   |-- src/main/java/com/cryptosentinelai/app/ - codice nativo Java.
|   |   |   |-- MainActivity.java - entrypoint Android e registrazione plugin custom.
|   |   |   `-- AppSettingsPlugin.java - bridge Capacitor per impostazioni e download APK.
|   |   |-- src/main/res/ - risorse Android: icone, splash, layout, stringhe, stili e XML provider.
|   |   |-- src/test/ - test JVM Android di esempio.
|   |   |-- src/androidTest/ - test strumentali Android di esempio.
|   |   |-- build.gradle - build modulo Android, signing debug e versione da buildNumber.
|   |   |-- capacitor.build.gradle - dipendenze plugin Capacitor, incluso push notifications.
|   |   |-- debug.keystore - keystore debug Android.
|   |   `-- proguard-rules.pro - regole ProGuard/R8.
|   |-- capacitor.settings.gradle - include moduli Capacitor.
|   |-- gradle/wrapper/ - Gradle wrapper.
|   |-- build.gradle - build root Android e Google Services plugin.
|   |-- gradle.properties - proprietà Gradle.
|   |-- gradlew / gradlew.bat - wrapper Gradle Unix/Windows.
|   |-- settings.gradle - configurazione moduli Gradle.
|   `-- variables.gradle - versioni SDK/librerie Android.
|-- backend/ - backend FastAPI/Python per agente autonomo.
|   |-- __init__.py - namespace backend.
|   |-- README.md - runbook backend, endpoint, auth, configurazione e FCM.
|   |-- requirements.txt - dipendenze Python backend, incluso PyYAML per config centralizzata.
|   |-- app/ - package applicativo backend.
|   |   |-- main.py - entrypoint FastAPI, lifespan non bloccante, warm-up OHLCV watchlist in background, heartbeat loop, CORS con origin dashboard locale/Tailscale su porta 5176, proxy headers, logging richieste.
|   |   |-- api/ - router FastAPI e dipendenze API.
|   |   |   |-- dependencies.py - dipendenze read/admin/device token e Settings.
|   |   |   `-- routes/ - route FastAPI.
|   |   |       |-- __init__.py - aggrega router health/status/admin/notifications/alerts/market data/execution/views/mobile agent/observability.
|   |   |       |-- alerts.py - sincronizzazione configurazione alert e pending badge preferiti con acknowledgement; persistenza sync spostata fuori dall'event loop per evitare freeze API durante lock SQLite.
|   |   |       |-- admin.py - endpoint admin manual heartbeat.
|   |   |       |-- health.py - liveness/readiness/heartbeat con check reale DB (SELECT 1 + latency) da Step 5.
|   |   |       |-- notifications.py - registrazione token device (DB-backed da Step 5), status FCM e invio admin push.
|   |   |       |-- support.py - ticket in-app: profilo device/display name, apertura ticket utente, thread messaggi visibili per user_id anche se cambia device_id, gestione admin con risposta/risoluzione/chiusura/archiviazione, badge messaggi non letti separato user/admin e mark-read singolo/globale.
|   |   |       |-- market_data.py - endpoint normalizzati markets/prices/search/OHLCV e selettore globale UI/market admin-only persistito.
|   |   |       |-- execution.py - readiness esecuzione, selettori provider spot/perp, wallet execution read-only, override wallet/BSC chain/RPC admin-only e verifica registrazione competizione on-chain.
|   |   |       |-- agent.py - status agente, eligible tokens, watchlist operativa AI read/admin, decision log paginato, data coverage OHLCV read-only, kill switch admin-only e valutazione esplicita segnali Spot/Perp per dry-run/test Step 6.
|   |   |       |-- mobile_agent.py - endpoint Step 7 per settings agente mobile, inclusa applicazione live dei toggle stop loss ATR/Min-Max 20 con buffer percentuale e margine fisso Perp opzionale, onboarding validation con lock 10 minuti e wallet multi-network senza esposizione segreti.
|   |   |       |-- observability.py - endpoint admin-only Step 8 per log viewer dashboard con tail bounded e redazione valori sensibili.
|   |   |       |-- views.py - viste dashboard/app: spot, perp, global, equity-curve, asset-breakdown, trade-detail rapido con exposure Perp mostrata come nozionale reale, margine separato, prezzi micro-token a 18 decimali e fallback entry spot da notional/size, prezzo minimo/massimo della candela riferimento SL, grafico opzionale best-effort bounded, marker candela riferimento SL con prezzo stop effettivo, valore stop iniziale preservato rispetto a breakeven/trailing, dettaglio Smart SL Perp con entry originale separata dall'entry corrente ricalcolata, Bot Day condiviso Spot/Perp dal primo ordine registrato, fallback legacy che ricostruisce il contesto pre-apertura per grafici senza stop_reference persistito e riuso cache klines recente per ridurre timeout su candele trade, operational-stats e archived-runs.
|   |   |       `-- status.py - status backend autenticato.
|   |   |-- agent/ - agent autonomous trading.
|   |   |   |-- heartbeat.py - heartbeat interno in memoria.
|   |   |   |-- service.py - orchestratore Step 6/9: segnali, risk, meta-controller, watchlist scanner Spot/Perp, filtro inversione mercato BTC 15m per nuove aperture, slow tick con watchlist combinata, dry-run DB, daily Spot heartbeat 20:00-23:30 UTC, chiusure ATR/breakeven/trailing con breakeven Spot/Perp configurabile e trailing etichettato separatamente dal breakeven, alert drawdown configurabile, snapshot grafici trade con finestra completa delle 20 candele strutturali SL, stop iniziale separato dallo stop dinamico, runtime settings con margine fisso Perp opzionale e provider execution astratti.
|   |   |   |-- watchlist.py - helper RuntimeState per watchlist operativa AI selezionata dall'utente e validata contro `Settings.eligible_tokens`.
|   |   |   |-- ohlcv_warmup.py - warm-up storico delle klines 5m Binance per watchlist AI, con lock/cadenza anti-burst e popolamento cache Data Coverage/signal engine.
|   |   |   |-- brain/ - Claude meta-controller con poteri limitati; fallback dry-run deterministico e fail-closed fuori dry-run.
|   |   |   |-- loops/ - loop veloce gestione posizioni e loop lento scansione/decisione safe-by-default.
|   |   |   |-- risk/ - risk manager fail-closed con kill switch, universo eligible, sizing dry-run realistico, override margine fisso Perp opzionale, soglia minima trade e guardrail portfolio/drawdown/daily loss.
|   |   |   `-- signals/ - signal engine modulare Spot/Perp/V2.
|   |   |       |-- base.py - primitive base signal engine.
|   |   |       |-- common/indicators.py - primitive Candle, EMA, VWAP, ATR, RSI e relative volume.
|   |   |       |-- spot/momentum.py - Spot V1 momentum + struttura: warm-up OHLCV 5m Binance spot per asset singolo, VWAP, EMA 20/50, ATR, RSI filtro, relative volume e metadata candela riferimento SL strutturale.
|   |   |       |-- spot/relative_strength_v2.py - placeholder relative strength V2.
|   |   |       |-- perp/binance_klines.py - feed Binance klines specializzato per signal engine (`/fapi/v1/klines` o `/api/v3/klines`) con cache in memoria per Data Coverage.
|   |   |       |-- perp/cex_fallback.py - fallback best-effort Bitget/KuCoin per candele e prezzi quando Binance non copre il token.
|   |   |       |-- perp/volume_profile.py - Volume Profile Perp V1 rolling 24h con POC/VAH/VAL, VWAP trend filter, stop ATR/Min-Max configurabile e metadata candela riferimento SL strutturale.
|   |   |       `-- perp/orderflow_delta_v2.py - placeholder order-flow delta V2.
|   |   |-- core/ - configurazione, logging e sicurezza.
|   |   |   |-- config.py - unico loader Settings: fonde .env + configs/*.yaml, valida guardrail hard.
|   |   |   |-- logging.py - structlog JSON/console con file giornaliero rotante e retention configurabile.
|   |   |   `-- security/ - sicurezza API/custody.
|   |   |       |-- auth.py - autenticazione token read/device/admin fail-closed.
|   |   |       |-- headers.py - security headers e HSTS condizionale.
|   |   |       `-- wallet_custody.py - provider keystore Web3 cifrato con policy typed-data fail-closed.
|   |   |-- data/ - integrazioni dati mercato.
|   |   |   |-- market_data/ - astrazione multi-provider Step 3.
|   |   |   |   |-- base.py - interfaccia MarketDataProvider, identità asset e modelli normalizzati.
|   |   |   |   |-- aliases.py - mapping ID storico app/CoinGecko verso slug CMC.
|   |   |   |   |-- registry.py - selettore globale UI/market, factory dedicata per alert su provider configurato separatamente, riconciliazione ID storici resiliente, cache in memoria delle identità risolte e popolamento dalle liste ranked per ridurre refresh lenti.
|   |   |   |   |-- cmc.py - adapter CMC REST con liste a blocchi da 200, ricerca progressiva e risoluzione preferiti per simbolo/ID.
|   |   |   |   |-- coingecko.py - adapter CoinGecko secondario e catalogo identità degli ID storici con cache giornaliera.
|   |   |   |   |-- http.py - client condiviso con cache, rate limiting e contatore crediti.
|   |   |   |   |-- cache.py / rate_limit.py / credits.py - primitive TTL, throttling e budget CMC.
|   |   |   |-- ohlcv_sources.py - sorgente OHLCV pubblica separata dal provider latest: Binance klines spot con fallback CEX, conversione display USD/EUR/BTC best-effort.
|   |   |   `-- mcp/cmc.py - metadata connessione MCP ufficiale CMC senza esposizione chiavi.
|   |   |-- domain/ - modelli dominio separati: common, spot, perp, global_state.
|   |   |-- execution/ - layer esecuzione Step 4 (esteso: spot E perp astratti multi-provider, registry separati).
|   |   |   |-- base.py - interfaccia astratta ExecutionProvider (spot) + modelli (ExecutionQuote, ExecutionProviderStatus); get_position/close_position default fail-closed per spot atomico.
|   |   |   |-- registry.py - ExecutionProviderRegistry: selettore globale spot twak/pancakeswap, default da Settings, override persistito in RuntimeState, cambio admin-only.
|   |   |   |-- providers/twak_provider.py - TWAKProvider: avvolge TwakClient nell'interfaccia (refactor di adattamento, nessuna riscrittura HMAC/Amber/CLI).
|   |   |   |-- providers/pancakeswap_provider.py - PancakeSwapProvider: esecuzione DEX diretta via web3.py (getAmountsOut, approval esatta, swapExactTokensForTokens/swapExactETHForTokens, conferma on-chain); riusa i guardrail comuni; submission mainnet gated.
|   |   |   |-- perp_base.py - interfaccia astratta PerpExecutionProvider (perp) + modelli (PerpOrder, PerpPositionView, PerpProviderStatus); open/close/get_position default fail-closed finché non c'è venue.
|   |   |   |-- perp_registry.py - PerpExecutionRegistry: selettore globale perp (bnb_sdk + futuri DEX perp), stesso pattern dello spot, persistito in RuntimeState.
|   |   |   |-- perp_providers/bnb_sdk_provider.py - BnbSdkPerpProvider: avvolge BnbAgentSdkBridge (EIP-712 sign/submit), status; alto livello predisposto.
|   |   |   |-- rpc.py - JSON-RPC BSC con failover tra endpoint.
|   |   |   |-- network_selection.py - override RuntimeState per selezionare BSC testnet/mainnet nell'esecuzione.
|   |   |   |-- rpc_selection.py - override RuntimeState per forzare l'RPC BSC preferito riordinando gli endpoint configurati.
|   |   |   |-- wallet_selection.py - lista e selezione runtime di wallet pubblici via RuntimeState, senza materiale privato.
|   |   |   |-- gas.py / approvals.py - riserva gas hard e approvals esatte/whitelist (riusati da entrambi i provider).
|   |   |   |-- coordinator.py / reconciliation.py - retry limitato e verifica on-chain.
|   |   |   |-- service.py - stato execution (provider spot+perp attivi + statuses dai registry) e verifica contratto competizione.
|   |   |   |-- spot_fees.py - stima costi dry-run spot PancakeSwap V3: swap fee e slippage applicabile/escludibile.
|   |   |   |-- perp_fees.py - fetch fee/funding PancakeSwap Perpetuals v2 con fallback costanti, funding accrual e confronto taker/maker.
|   |   |   |-- spot_twak/client.py - bridge TWAK per spot, x402 e registrazione.
|   |   |   |-- perp_bnb_sdk/client.py - bridge BNB SDK ed EIP-712 (avvolto da BnbSdkPerpProvider).
|   |   |   `-- x402/client.py - pagamenti BSC con budget e fallback provider.
|   |   |-- i18n/locales/ - traduzioni backend en.json e it.json, incluse chiavi market data Step 3.
|   |   |-- notifications/ - sistema notifiche server-side.
|   |   |   |-- alert_store.py - persistenza DB configurazione, stato checker e badge preferiti pendenti (DB-backed da Step 5; interfaccia pubblica invariata).
|   |   |   |-- price_checker.py - controllo prezzi ogni 60s usando `market_data.alert_provider` (CoinGecko di default, indipendente dal selettore UI); raggruppa i token per device_id e invia a ogni device solo i suoi alert; supporta soglie one-shot e crossing con riarmo percentuale.
|   |   |   |-- alert_store.py - store per-device (DeviceAlertConfig per device_id; AlertConfig legacy come fallback). get_alert_store(device_id) con cache per device.
|   |   |   |-- agent_notifier.py - AgentNotifier: notifiche push tipizzate per trade spot/perp (idempotenti via set trade_id in RuntimeState), allarmi rischio (anti-spam, stesso alert_type+detail non re-notifica), riepilogo giornaliero e eventi critici agente; singleton get_agent_notifier(); legge/scrive preferenze utente in RuntimeState.
|   |   |   |-- service.py - orchestration registry + FCM client.
|   |   |   `-- fcm/ - integrazione Firebase Cloud Messaging.
|   |   |       |-- client.py - wrapper Firebase Admin SDK, delivery e skipped se non configurato.
|   |   |       `-- token_store.py - registro token FCM DB-backed (DeviceToken); tokens_with_device() per invio mirato per device.
|   |   |-- observability/ - namespace metriche, health, replay/export futuri.
|   |   |-- persistence/ - layer persistenza dati Step 5.
|   |   |   |-- __init__.py - esporta init_db, close_db, get_session, get_session_factory, check_db.
|   |   |   |-- database.py - engine async aiosqlite, async_sessionmaker, create_all, check_db con SELECT 1 e latency.
|   |   |   |-- sync_database.py - engine sync sqlite3 per store legacy sincroni; stesso file SQLite, WAL e busy timeout allineato a 5s.
|   |   |   |-- backup.py - copia SQLite con timestamp UTC, pruning retention, restituisce None se DB assente.
|   |   |   |-- migration.py - migrazione idempotente JSON→DB al boot e upgrade colonne SQLite per fee, ATR, trailing, funding e reference stop loss con precisione prezzo micro-token.
|   |   |   |-- runtime_state.py - get/set_runtime_value sync per selettore provider; degrada silenziosamente.
|   |   |   |-- archive.py - archiviazione dry-run in ArchivedRun, pulizia tabelle live e reset PortfolioState per reset analytics.
|   |   |   |-- views.py - ViewService: spot_view, perp_view, global_view con PnL firmato, history Spot/Perp allineata ai trade chiusi con PnL, conteggio trade giornaliero invariato per mercato, Bot Day condiviso dal primo ordine Spot/Perp registrato, esposizione a margine, fee aggregate, position_id nella history Perp inclusi eventi Smart SL `ssl_`, entry storica Perp coerente per chiusure parziali, risk-off spot e Sharpe ratio guarded.
|   |   |   |-- models/ - ORM SQLAlchemy 2.0.
|   |   |   |   |-- base.py - DeclarativeBase comune.
|   |   |   |   |-- device_tokens.py - DeviceToken.
|   |   |   |   |-- device_profiles.py - DeviceProfile per associare device_id a display name utente senza usare il device token come identita'.
|   |   |   |   |-- support.py - SupportTicket e SupportMessage per ticket utente/admin con stato open/in_progress/waiting_user/resolved/closed/archived.
|   |   |   |   |-- alerts.py - AlertConfig (legacy, una riga per utente, config_json + state_json).
|   |   |   |   |-- device_alert_configs.py - DeviceAlertConfig (una riga per (user_id, device_id): alert separati per device).
|   |   |   |   |-- trades.py - SpotTrade e PerpTrade con timestamp_utc/block_timestamp_utc separati, prezzi a 18 decimali, PnL, fee, slippage e funding snapshot.
|   |   |   |   |-- positions.py - SpotPosition e PerpPosition con prezzi/livelli a 18 decimali, livelli SL/TP/trailing, ATR entry, candela riferimento stop loss, fee/slippage/funding, margin e stato TP1.
|   |   |   |   |-- decisions.py - AgentDecision (action, confidence, reasoning Text, trade_id).
|   |   |   |   |-- pnl.py - PnlSnapshot (orari) e PortfolioState (una riga per utente, upsert).
|   |   |   |   |-- archives.py - ArchivedRun: snapshot JSON dei dati dry-run simulati esclusi dalle viste live.
|   |   |   |   |-- equity_adjustments.py - versamenti/prelievi manuali separati dal PnL per non rebaselinare la performance storica.
|   |   |   |   |-- api_usage.py - tracking chiamate Claude: input/output token e costo stimato.
|   |   |   |   |-- trade_charts.py - snapshot JSON di candele e livelli congelati alla chiusura trade per il dettaglio dashboard.
|   |   |   |   |-- x402.py - X402DailyBudget (unique user_id + budget_date).
|   |   |   |   |-- runtime_state.py - RuntimeState (unique user_id + key).
|   |   |   |   `-- __init__.py - esporta tutti i modelli, registra tabelle con Base.
|   |   |   `-- repositories/ - repository ORM per ogni aggregato.
|   |   |       |-- __init__.py - esporta tutti i repository.
|   |   |       |-- device_tokens.py - DeviceTokenRepository (upsert, remove, tokens_for_user, count).
|   |   |       |-- device_profiles.py - repository profili device/display name per supporto e registrazione FCM.
|   |   |       |-- support.py - repository ticket supporto con creazione, lista per user_id, thread messaggi, cambio stato e filtro archivio.
|   |   |       |-- alerts.py - AlertConfigRepository (save, load → tuple[config|None, state]).
|   |   |       |-- trades.py - SpotTradeRepository e PerpTradeRepository (save, get, list, win_rate, primo timestamp ordine per Bot Day).
|   |   |       |-- positions.py - SpotPositionRepository e PerpPositionRepository (save, open_for_user, history).
|   |   |       |-- decisions.py - AgentDecisionRepository (save, get, recent_for_user con filtro market).
|   |   |       |-- pnl.py - PnlRepository (save_snapshot, recent_for_user, upsert_portfolio, get_portfolio, adjust_equity, list_equity_adjustments).
|   |   |       |-- api_usage.py - ApiUsageRepository per riepilogo costo/token Claude.
|   |   |       |-- trade_charts.py - TradeChartRepository per snapshot o fallback posizione.
|   |   |       `-- x402_budget.py - X402BudgetRepository (load_today, save).
|   |   |-- schemas/ - schemi API.
|   |   |   |-- alerts.py - payload sincronizzazione soglie, range e preferiti, incluse opzioni crossing/riarmo per alert prezzo.
|   |   |   |-- notifications.py - device token, notification request/response e status.
|   |   |   |-- support.py - schemi profilo device, ticket, messaggi, risposte admin e cambio stato.
|   |   |   |-- notification_prefs.py - NotificationPreferences (5 toggle spot/perp/risk/summary/critical) e NotificationPreferencesResponse con campo source (default/persisted).
|   |   |   |-- market_data.py - response API normalizzate e selezione provider.
|   |   |   |-- execution.py - request/response selezione provider esecuzione spot/perp, wallet execution e diagnostica RPC.
|   |   |   |-- mobile_agent.py - schemi Step 7 per mobile settings inclusi filtro inversione mercato, modalita' stop loss Spot/Perp con lookback/buffer strutturale, margine fisso Perp opzionale, credential checks e wallet summary con balance asset non-zero.
|   |   |   |-- observability.py - schemi Step 8 per log viewer dashboard.
|   |   |   `-- views.py - SpotView, PerpView, GlobalView, ClaudeUsageView, PnlPoint e campi analytics PnL/Sharpe/fee/margine per dashboard/app.
|   |   |-- services/ - namespace application services.
|   |   `-- tasks/ - namespace scheduled/background tasks.
|   |-- scripts/ - script di avvio backend.
|   |   |-- encrypt_wallet.py - creazione interattiva keystore Web3 cifrato senza input CLI.
|   |   |-- archive_dry_run.py - helper manuale per archiviare dati dry-run simulati e pulire le tabelle live.
|   |   |-- register_competition.py - helper manuale esplicito per `twak compete register --json`, con password TWAK via prompt nascosto.
|   |   |-- select_twak_wallet.py - helper admin locale per aggiungere/selezionare il nuovo wallet TWAK pubblico in RuntimeState.
|   |   |-- migrate_perp_leverage_size.py - migrazione one-shot con backup per correggere size/PnL perp storici salvati senza moltiplicatore leva.
|   |   |-- test_spot_swap.py - smoke test TWAK testnet con gas guard e verifica ricevuta.
|   |   |-- twak_rpc_route_probe.py - diagnostica quote-only TWAK REST ruotando manualmente le RPC BSC configurate; dominio smartchain/smartchain-testnet derivato dalla rete.
|   |   |-- pancakeswap_smoke_test.py - smoke test PancakeSwap diretto (quote-only di default; --execute swap reale, mainnet solo con --allow-mainnet).
|   |   |-- run_backend.ps1 - avvio Windows PowerShell (dev/prod, legge host:port da Settings).
|   |   `-- run_backend.sh  - avvio Linux/bash per VPS (dev/prod, stesso comportamento).
|   `-- tests/ - test backend.
|       |-- unit/test_alert_store.py - regressione stato alert tra sincronizzazioni (DB-backed da Step 5).
|       |-- unit/test_auth_scopes.py - separazione scope device, alerts e admin.
|       |-- unit/test_market_data_rate_limit.py - accodamento richieste oltre soglia.
|       |-- unit/test_dashboard_cors.py - regressione CORS dashboard: origin localhost/Tailscale su porta 5176 consentiti senza wildcard.
|       |-- integration/test_support_api.py - flusso ticket utente/admin: profilo device, creazione, reply, risoluzione e chiusura.
|       |-- unit/test_execution_layer.py - gate gas, approval, RPC, EIP-712, TWAK, retry e x402.
|       |-- unit/test_execution_providers.py - interfaccia ExecutionProvider, selettore twak/pancakeswap, quote getAmountsOut, costruzione swap tx, guardrail (slippage/gas/gate mainnet), normalizzazione TWAK.
|       |-- unit/test_perp_providers.py - interfaccia PerpExecutionProvider, BnbSdkPerpProvider (status, sign/submit delega al bridge, open/close/get_position gated), selettore perp.
|       |-- unit/test_execution_wallets.py - regressioni Step 8 per snapshot wallet execution, saldo BNB live e override RPC persistito.
|       |-- unit/test_encrypt_wallet_script.py - verifica output cifrato e azzeramento buffer chiave.
|       |-- unit/test_device_alert_separation.py - regressione isolamento per-device e alert crossing con riarmo percentuale.
|       |-- unit/test_agent_step6.py - regressioni Step 6/9 per segnali Spot/Perp, risk guardrail, meta-controller, kill switch, daily heartbeat, watchlist scanner e dry-run agent service con persistenza decisione/trade.
|       |-- unit/test_mobile_agent_step7.py - regressioni Step 7 per settings mobile persistiti/applicati live, onboarding validation e wallet multi-network.
|       |-- unit/test_signal_stop_loss_modes.py - regressioni signal engine per stop loss Spot/Perp in modalita' ATR e Min/Max 20 candele con buffer.
|       |-- integration/test_market_data_providers.py - regressioni provider market-data, inclusa cache identità su refresh ripetuti dei prezzi.
|       |-- unit/test_persistence_layer.py - test async: check_db, migrazione idempotente, x402 budget, SpotTrade dual timestamp, PerpPosition leverage/liquidation, portfolio upsert, decision reasoning, GlobalView, SpotView/PerpView, archiviazione dry-run e backup.
|       `-- integration/ - gate Step 3 e API execution Step 4.
|-- configs/ - configurazione versionata e template installazione.
|   |-- README.md - categorie config, precedenza e guardrail hard.
|   |-- instance.example.yaml - template installazione non segreta; include sezione backup DB da Step 5 e nota CORS per origin dashboard Tailscale; copiare in instance.yaml locale gitignored.
|   |-- risk.yaml - default funzionali risk management, incluso dry_run_capital_usd 500 e min_trade_size_usd 7.
|   |-- strategy_spot.yaml - default strategia Spot.
|   |-- strategy_perp.yaml - default strategia Perpetual.
|   `-- eligible_tokens.yaml - universo 148 token eligible unici dopo rimozione del duplicato SLX.
|-- deploy/ - artefatti Step 10 per VPS Linux 24/7.
|   |-- nginx/cryptosentinel.conf - template nginx per dashboard statica e proxy `/api/` verso backend locale.
|   |-- scripts/ - script installazione, backup SQLite/TWAK encrypted state e healthcheck liveness.
|   |   |-- install_vps.sh - bootstrap Ubuntu/Debian da eseguire da `/opt/cryptosentinel/app`, senza segreti nel repo.
|   |   |-- backup_sqlite.sh - backup DB SQLite, config versionate non segrete e stato TWAK cifrato.
|   |   `-- healthcheck.sh - curl fail-fast su `/health/live`.
|   `-- systemd/ - unit e timer systemd.
|       |-- cryptosentinel-backend.service - backend Uvicorn con restart automatico e hardening base.
|       |-- cryptosentinel-backup.service / cryptosentinel-backup.timer - backup periodico ogni 6 ore.
|       `-- cryptosentinel-healthcheck.service / cryptosentinel-healthcheck.timer - liveness periodica ogni 60 secondi.
|-- docs/ - documentazione progetto e review.
|   |-- CURRENT_STRUCTURE.md - baseline pre-integrazione backend.
|   |-- PROJECT_STRUCTURE.md - questo documento aggiornato a ogni step.
|   |-- RUNBOOK_DEPLOY_VPS.md - runbook Step 10 per installazione VPS, segreti fuori repo, nginx/TLS, TWAK headless, backup e ripristino.
|   |-- Strategia_Spot.md - strategia Spot V4 allineata al codice corrente.
|   |-- Strategia_Perpetual.md - strategia Perpetual V4 allineata al codice corrente.
|   |-- Uscite_Spot.md - regole operative aggiornate per chiusure spot ATR, breakeven, trailing, TP e time stop opzionale.
|   |-- Uscite_Perpetual.md - regole operative aggiornate per chiusure perp ATR, breakeven, trailing dinamico, TP, time stop opzionale, funding e liquidazione stimata.
|   |-- index.html - pagina documentale/statica.
|   `-- reports/ - report step.
|       |-- report_step0.md - report Step 0.
|       |-- report_step1.md - report Step 1.
|       |-- report_step2.md - report Step 2.
|       |-- report_step2_final.md - chiusura finale Step 2 dopo test reali e revisione commit.
|       |-- report_step3.md - report implementazione astrazione multi-provider e test-gate.
|       |-- report_step4.md - report layer esecuzione Step 4.
|       |-- report_step5.md - report persistenza dati Step 5.
|       |-- report_step6.md - report agente AI Brain Step 6.
|       |-- report_step7.md - report estensione app mobile Step 7.
|       |-- report_step8.md - report dashboard web unificata Step 8.
|       |-- report_step9.md - report testing e vincoli qualificazione Step 9.
|       |-- report_step10.md - report artefatti deploy VPS Step 10.
|       |-- report_twak_wallet_migration.md - report migrazione nuovo wallet TWAK, fix mainnet/domain e workaround password Windows.
|       |-- report_dashboard_analytics.md - report archiviazione dry-run, sizing realistico e analytics dashboard/mobile.
|       |-- report_dashboard_data_coverage_filters.md - report filtri Data Coverage dashboard.
|       |-- report_dashboard_scripts.md - report script avvio/riavvio dashboard.
|       |-- report_docs_code_reconciliation_2026-06-26.md - report ricognizione codice e riallineamento documentazione.
|       |-- report_fix_market_regression.md - report regressione prezzi preferiti e lentezza market-data.
|       |-- report_support_tickets_2026-07-15.md - report ticket supporto in-app e dashboard.
|       |-- report_stop_loss_mode_toggle_2026-07-18.md - report fix toggle stop loss ATR/Min-Max 14.
|       |-- report_config_refactor.md - report task intermedio ambiente/config.
|       |-- report_spot_micro_price_detail_2026-08-01.md - report fix prezzi micro-token nel dettaglio spot BABYDOGE.
|       |-- report_trade_chart_stop_ref_gap_2026-08-01.md - report linea riferimento SL che lascia visibile la candela nel grafico trade.
|       |-- report_strategy_docs_v4_2026-08-02.md - report aggiornamento documenti strategia Spot/Perp alla V4.
|       |-- report_time_stop_toggle_2026-08-02.md - report toggle time stop app/dashboard e backend.
|       |-- report_dashboard_trade_history_page_size_2026-08-02.md - report filtro 20/50/100/Tutti history Spot/Perp dashboard.
|       |-- report_trade_history_count_alignment_2026-08-02.md - report fix allineamento conteggi/history Spot/Perp.
|       |-- report_bot_active_days_metric_2026-08-02.md - report nuova metrica Bot Day condivisa Spot/Perp.
|       |-- report_dashboard_tailscale_host_2026-08-04.md - report accesso dashboard dev tramite Tailscale.
|       `-- report_perp_fixed_margin_toggle_2026-07-27.md - report toggle margine fisso Perp app/dashboard.
|-- dashboard/ - progetto Vite separato Step 8 per dashboard web desktop-first su porta 5176.
|   |-- index.html - entrypoint HTML dashboard.
|   |-- vite.config.ts - config Vite autonoma con `envDir` dedicato, dev/preview su `0.0.0.0:5176` e output `dist-dashboard`.
|   |-- tsconfig.json - configurazione TypeScript isolata per dashboard.
|   `-- src/ - applicazione React dashboard.
|       |-- main.tsx - entrypoint React dashboard.
|       |-- App.tsx - viste Overview, Spot, Global, Health con Data Coverage filtrabile, Wallet, Logs, Settings, Onboarding, Markets, Support con archivio, Export, metriche Trade Day e Bot Day in Spot/Perp, backend URL normalizzato nel form per non usare la porta dashboard come API, formatter micro-prezzi con soglia full-decimal sotto 0.000001 e dettaglio trade con grafico/fee/margine/riferimento SL Perp; nei grafici trade le candele fuori dalla finestra di posizione sono attenuate, il marker SL ref cade sul prezzo SL effettivo e la linea ref evita la candela; le history Spot/Perp hanno filtri e selettore 20/50/100/Tutti per pagina, mentre il Settings espone i buffer Min/Max20 Spot/Perp, il toggle margine fisso Perp e i toggle Time Stop Spot/Perp con durata in ore.
|       |-- api.ts - client API dashboard verso backend con token read/admin separati, normalizzazione host Tailscale/localhost dalla porta dashboard 5176 alla porta backend 8001, inclusa gestione ticket supporto admin.
|       |-- types.ts - tipi TypeScript dei contratti backend usati dalla dashboard, incluse analytics, fee, margine, liquidazione Perp, trade detail e support ticket.
|       `-- styles.css - layout desktop-first, stati UI e controlli history/paginazione.
|-- plans/ - piani operativi.
|   `-- Plan_forHackathon.md - piano completo BNB Hack Track 1.
|-- public/ - asset statici frontend/PWA.
|-- scripts/ - script frontend/tooling.
|   |-- start_dashboard.ps1 - avvio dashboard Vite su porta 5176 in finestra PowerShell visibile, bind su tutte le interfacce e stampa URL locale/Tailscale.
|   |-- restart_dashboard.ps1 - riavvio dashboard: chiude il listener esistente su 5176 e poi avvia Vite su tutte le interfacce mostrando URL locale/Tailscale.
|   |-- twak-password-file.cjs - wrapper Node per leggere password TWAK da file UTF-8 ed evitare problemi encoding PowerShell/keychain.
|   `-- gen-icons.mjs - generazione icone.
|-- src/ - frontend React/TypeScript esistente.
|   |-- components/ - componenti UI CryptoSentinel.
|   |   |-- AgentTab.tsx - tab mobile agente con viste Spot/Perp/Global, metriche Trade Day e Bot Day in Spot/Perp, analytics sintetica, formatter micro-prezzi con soglia full-decimal sotto 0.000001, dettaglio trade rapido con cache che distingue grafico base e candele post-chiusura, deduplica delle richieste dettaglio in corso, refresh single-flight, preload base della prima pagina Spot/Perp e delle posizioni aperte, enrichment grafico solo dopo apertura dettaglio, risk levels con prezzo candela riferimento SL Perp, grafici trade con candele pre-entry/post-close attenuate, marker SL ref sul prezzo stop effettivo e linea ref che evita la candela, setup con stop loss ATR o Min/Max 20 con buffer per Spot/Perp, filtro inversione mercato, toggle margine fisso Perp, toggle Time Stop Spot/Perp con durata in ore, toggle breakeven Spot/Perp e allarme drawdown configurabili, onboarding, kill switch, admin token persistito localmente, wallet caricati solo nella vista dedicata ed empty state dedicati.
|   |   `-- SettingsTab.tsx - impostazioni app, nome utente locale per supporto, apertura/lettura ticket con mark-read, reply utente, modalita' admin opzionale per risposta/chiusura e uso dello stesso admin token persistito dell'AgentTab.
|   |-- hooks/ - hook dati, alert, preferiti, valuta, search e refresh.
|   |-- services/marketData.ts - client unico verso API backend con request ID e diagnostica non sensibile.
|   |-- services/agentApi.ts - client Step 7 per viste agente, settings mobile, onboarding, wallet e kill switch.
|   |-- services/supportApi.ts - client supporto in-app con diagnostica whitelisted e API utente/admin.
|   |-- utils/ - notifiche, update, haptics, audio, energy saving.
|   |   |-- alertSync.ts - sincronizzazione alert attivi verso il backend.
|   |   |-- marketDataDiagnostics.ts - buffer locale degli ultimi eventi market-data senza token.
|   |   `-- notifications.ts - registrazione token FCM con build number/display name e rendering locale push in foreground.
|   |-- App.tsx - root app mobile/web; sincronizza sempre l'intero insieme dei preferiti salvati, monta la tab agente additiva Step 7 e mostra in Home a sinistra il badge flottante dei messaggi supporto non letti user/admin.
|   |-- hooks/useFavoriteCoinsData.ts - recupero preferiti con fetch dedicato di tutti gli ID salvati, retry rapido e righe temporanee per tutti gli ID salvati.
|   |-- hooks/useSearch.ts - ricerca debounced tramite endpoint backend e provider globale selezionato.
|   |-- index.css - CSS globale/Tailwind.
|   |-- main.tsx - entrypoint React.
|   |-- types.ts - tipi frontend.
|   `-- vite-env.d.ts - tipi Vite.
|-- .env.example - template solo segreti/sensitive paths, valori vuoti.
|-- .gitignore - esclusioni frontend, backend, segreti, instance config e storage locale.
|-- capacitor.config.ts - configurazione Capacitor.
|-- package.json - script e dipendenze frontend/mobile/dashboard, incluso `dashboard:dev` su porta 5176 con host `0.0.0.0`.
|-- package-lock.json - lockfile npm.
|-- README.md - documentazione app mobile esistente.
|-- requirements.txt - delega install Python a backend/requirements.txt.
`-- vite/ts/eslint/tailwind/postcss config files - configurazione frontend/tooling.
```

## 2. STACK TECNOLOGICO

### Frontend/mobile esistente

| Tecnologia | Versione | Scopo |
|---|---:|---|
| React | ^19.2.6 | UI frontend/mobile. |
| React DOM | ^19.2.6 | Rendering DOM. |
| TypeScript | ~6.0.2 | Tipizzazione frontend. |
| Vite | ^8.0.12 | Build e dev server frontend. Dashboard futura: porta richiesta 5176. |
| Tailwind CSS | ^3.4.19 | Styling UI. |
| Capacitor Core/Android/CLI | ^8.3.4 | Bridge e target Android. |
| Capacitor Haptics | ^8.0.2 | Feedback aptico. |
| Capacitor Local Notifications | ^8.2.0 | Notifiche locali Android mantenute come fallback. |
| Capacitor Push Notifications | ^8.1.1 | Registrazione token FCM lato mobile. |
| lightweight-charts | ^5.2.0 | Grafici prezzo. |
| qrcode | ^1.5.4 | Generazione QR code. |

### Backend Python

| Dipendenza | Versione | Scopo |
|---|---:|---|
| fastapi | 0.115.6 | Framework API backend. |
| uvicorn[standard] | 0.34.0 | ASGI server. |
| pydantic | 2.10.4 | Modelli e validazione dati. |
| pydantic-settings | 2.7.1 | Settings da ambiente con precedenza controllata. |
| python-dotenv | 1.0.1 | Caricamento .env locale a runtime. |
| PyYAML | 6.0.3 | Parsing YAML per configs/*.yaml. |
| sqlalchemy | 2.0.36 | ORM/persistenza futura. |
| alembic | 1.14.0 | Migrazioni database future. |
| aiosqlite | 0.20.0 | Driver SQLite async iniziale. |
| psycopg[binary] | 3.2.3 | Driver PostgreSQL per VPS. |
| httpx | 0.28.1 | Client HTTP async per adapter CMC/CoinGecko e integrazioni esterne. |
| web3 | 7.6.1 | Interazioni BSC/on-chain future. |
| cryptography | 44.0.0 | Cifratura key material e sicurezza. |
| firebase-admin | 7.4.0 | Invio notifiche FCM server-side. |
| structlog | 24.4.0 | Logging strutturato. |
| python-json-logger | 3.2.1 | Log JSON. |
| pytest | 8.3.4 | Test backend. |
| pytest-asyncio | 0.25.0 | Test async. |
| ruff | 0.8.4 | Lint/format Python. |

### Android/CI

| Componente | Versione/config | Scopo |
|---|---:|---|
| minSdkVersion | 24 | Android minimo. |
| compileSdkVersion | 36 | SDK compilazione. |
| targetSdkVersion | 36 | Target Android. |
| Android Gradle Plugin | 8.13.0 | Build Android. |
| GitHub Actions JDK | 21 Temurin | Build APK CI; accettato perché superiore al minimo Java 17 richiesto da toolchain moderna. |
| peaceiris/actions-gh-pages | v4 | Pubblica `docs/index.html` e APK su branch `gh-pages` dopo build su `main`. |
| androidx.work:work-runtime | 2.9.0 | Worker background alert locale. |
| Google Services Gradle Plugin | 4.4.4 | Firebase/FCM quando google-services.json è presente. |

## 3. VARIABILI D'AMBIENTE

`.env.example` è ora limitato ai soli segreti e path sensibili. Tutti i valori restano vuoti.

| Variabile | Spiegazione |
|---|---|
| API_READ_TOKEN | Token read-only per dashboard/mobile status. Admin può soddisfare read, mai il contrario. |
| VITE_API_READ_TOKEN | Copia build-time frontend/mobile del token read-only per market data e status. |
| API_ADMIN_TOKEN | Token admin per operazioni privilegiate, future config changes ed execution. |
| API_DEVICE_TOKEN | Token limitato per registrare/rimuovere token push device. |
| VITE_API_DEVICE_TOKEN | Copia build-time frontend/mobile del token device limitato. |
| API_ALERTS_TOKEN | Token limitato alla sincronizzazione della configurazione alert. |
| VITE_API_ALERTS_TOKEN | Copia build-time frontend/mobile del token alert limitato. |
| TOKEN_HASH_PEPPER | Pepper segreto per hash token/credenziali locali future. |
| DATABASE_URL | URL database solo quando contiene credenziali o punta a DB gestito sensibile. |
| CMC_API_KEY | Chiave API CoinMarketCap. |
| ANTHROPIC_API_KEY | Chiave API Anthropic/Claude. |
| TWAK_ACCESS_ID | Access ID Trust Wallet Agent Kit. |
| TWAK_HMAC_SECRET | Segreto HMAC Trust Wallet Agent Kit. |
| TWAK_WALLET_PASSWORD | Password wallet TWAK per ambienti headless; su Windows con caratteri non-ASCII preferire `scripts/twak-password-file.cjs`. |
| WALLET_ENCRYPTED_PRIVATE_KEY_PATH | Path a materiale wallet cifrato; trattato come sensibile. |
| WALLET_KEY_PASSPHRASE_ENV | Nome variabile/segreto che fornisce la passphrase wallet. |
| FCM_CREDENTIALS_PATH | Path service account Firebase; trattato come sensibile. |

Configurazioni non segrete ma specifiche dell'installazione sono in `configs/instance.example.yaml` e nel locale gitignored `configs/instance.yaml`.

Configurazioni funzionali versionate sono in `configs/risk.yaml`, `configs/strategy_spot.yaml`, `configs/strategy_perp.yaml`, `configs/eligible_tokens.yaml`.

Ordine di precedenza runtime: variabili ambiente e `.env` > `configs/instance.yaml` > YAML funzionali versionati > default Pydantic in `Settings`.

## 4. STATO STEP

| Step | Stato | Note |
|---|---|---|
| Step 0 - Setup & Architettura | Completato | Scaffold backend, env, gitignore, requirements, i18n, signal engine modulare, report e documentazione. |
| Step 1 - Backend FastAPI fondamenta | Completato | Server FastAPI avviabile, token auth read/admin, logging strutturato, health/readiness, heartbeat interno. |
| Step 2 - Migrazione Notifiche a Backend FCM | Completato | Checker backend 60s, sync alert, persistenza temporanea, FCM con app aperta/background/chiusa verificato dall'utente; boundary auth e regressione stato notifiche verificati. |
| Task intermedio - Ambiente + config refactor | Parziale | Config refactor completato e verificato; build APK riuscita in CI, deploy Pages corretto per usare branch `gh-pages` solo da `main`. |
| Task istruzioni agenti | Completato | Creato `AGENTS.md` con regole permanenti operative, sicurezza, documentazione, config, CI e step boundary. |
| Task Android package rename | Completato | Package Android/appId rinominato da `com.cryptosentinel.app` a `com.cryptosentinelai.app` per evitare conflitto con il fork/app esistente. |
| Task CI FCM Android config | Completato | Workflow aggiorna `android/app/google-services.json` da GitHub Secret base64 prima della build APK. |
| Task CI APK artifact robustness | Completato | Artifact APK caricato prima delle release GitHub; release non bloccanti per non impedire download APK/Pages. |
| Task regressione market-data frontend | Completato | Ripristinato il flusso frontend pre-regressione per selettore mercato e preferiti; rimossa la logica di seed/cache/chunking introdotta nei fix intermedi. |
| Step 3 - Astrazione Dati Multi-Provider | Parziale | Adapter CMC/CoinGecko, selettore globale, checker/frontend astratti e gate completati; smoke CMC e CoinGecko reali superati. Restano i18n frontend legacy e limite Volume Profile 5m. |
| Step 4 - Layer di Esecuzione | Parziale | TWAK spot, BNB SDK/EIP-712 perp, RPC fallback, gas/approval guardrail, x402 e verifica competizione implementati e testati; mancano transazioni reali testnet e venue perp ufficiale configurata. |
| Step 5 - Persistenza Dati | Completato | Schema Spot/Perp/Globale su SQLite/aiosqlite; migrazione JSON→DB (FCM, alert, x402, provider selector); readiness DB reale SELECT 1; viste dashboard; backup periodico configurabile; 16 test tutti passed. |
| Step 6 - Agente AI Brain | Parziale | Brain/meta-controller, Spot V1, Perp Volume Profile V1, feed Binance klines dedicato con fallback CEX, risk manager, kill switch, loop fast/slow, fee/funding dry-run, breakeven/trailing ATR e snapshot grafici implementati; live execution resta fail-closed dove mancano venue/amount atomici e verifica reale. |
| Step 7 - Estensione App Mobile | Parziale | Nuova tab Agente additiva con viste Spot/Perp/Global, setup agente, onboarding validation, kill switch, wallet multi-network e icone AI opzionali sulle coin card; verifiche locali passate, resta test su dispositivo reale/APK. |
| Step 8 - Dashboard Web Unificata | Parziale | Progetto Vite separato su porta 5176 con Overview giudici, Spot/Global/Perp, dettaglio trade con grafico e margine, System Health, Data Coverage, Wallet con selezione wallet/chain/provider/RPC, kill switch, log viewer admin-only, settings agente, onboarding, monitor prezzi ed export JSON; build locale e test mirati passati, resta verifica end-to-end con backend reale e token operativi. |
| Step 9 - Testing | Parziale | Debiti test Step 6/7/8 coperti, daily Spot heartbeat 20:00-23:30 UTC implementato nel loop lento, script registrazione competizione predisposto, watchlist AI operativa, warm-up OHLCV, migrazione nuovo wallet TWAK, fix leverage perp storico e analytics dry-run consolidati; ultima suite documentata: 127 passed. |
| Step 10 - Deploy VPS | Parziale | Aggiunti template systemd, nginx, script install/backup/healthcheck e runbook VPS; deploy reale, DNS/TLS, segreti runtime e verifica 24/7 restano da eseguire sul server. |

## 5. DECISIONI ARCHITETTURALI

| Decisione | Motivazione |
|---|---|
| Unico loader in `backend/app/core/config.py` | Il resto del backend legge solo `Settings`; nel multi-user cambierà la sorgente dati, non i consumer. |
| `.env.example` solo segreti | Riduce rischio di versionare materiale operativo e separa ownership da strategia/config installazione. |
| `configs/instance.yaml` locale gitignored | Valori specifici dell'installazione non segreti ma non condivisibili restano fuori repo. |
| YAML funzionali versionati | Risk/strategie diventano esportabili per giudici e futuri default di sistema overridabili per utente. |
| Guardrail hard fail-closed | Portfolio floor > 1 USD, minimo 1 trade/day, drawdown cap prudenziale e lista eligible tra 100 e 200 token unici non sono disattivabili da config. |
| Errori Pydantic senza input | Evita che un errore di validazione stampi valori di configurazione potenzialmente sensibili. |
| FCM credentials path in `.env.example` | Anche i path a service account/segreti sono trattati come sensibili, quindi non stanno in `instance.yaml`. |
| Java locale non installato | La build Android passa da GitHub Actions, usando JDK 21 già presente nel workflow; evita SDK/JDK sulla macchina locale. |
| Deploy Pages via `gh-pages` branch | Replica il comportamento storico del progetto: ogni build su `main` aggiorna il branch `gh-pages` senza usare l'ambiente protetto `github-pages`. |
| Package Android dedicato | Il fork hackathon usa `com.cryptosentinelai.app` per non collidere con l'app CryptoSentinel esistente sul device e su Firebase/Play metadata. |
| `google-services.json` solo da secret CI | Il file Android Firebase resta gitignored e viene ricostruito in CI da `GOOGLE_SERVICES_JSON` base64 senza stampare il contenuto. |
| Artifact APK prima delle release | Il download dell'APK non deve dipendere dal successo degli step `gh release`, che sono accessori e possono fallire per collisioni/rate limit. |
| Gate segreti build APK | La CI interrompe la build prima di Vite se URL backend o token client obbligatori sono assenti, evitando APK parzialmente funzionanti. |
| FCM come unico percorso background | Rimossi WorkManager e BootReceiver: il backend controlla gli alert ogni 60 secondi e FCM consegna anche ad app chiusa. |
| Backend unica fonte notifiche | Gli hook frontend non fanno scattare notifiche, beep o popup autonomi; in foreground viene mostrato localmente solo il push FCM ricevuto. |
| Alert crossing con riarmo | Gli alert prezzo possono scattare solo su attraversamento soglia, registrare up/down e restare attivi con riarmo percentuale; default one-shot preserva il comportamento prudente. |
| Stato UI derivato dal push | Il payload FCM dei preferiti ripristina evidenziazione arancione e popup; il tap sulla notifica apre la tab Preferiti senza rieseguire controlli prezzo locali. |
| Badge preferiti persistente backend | Un push consegnato crea uno stato pending per coin. L'app lo recupera all'avvio/rientro in foreground e lo rimuove solo dopo “Ho capito”, coprendo app chiusa, avvio manuale e mancato tap sulla notifica. |
| Scope client separati | Il token device registra/rimuove solo device; il token alerts sincronizza solo alert; stato FCM richiede read e invio manuale richiede admin. |
| Stato checker autorevole lato backend | Sincronizzazioni identiche non riarmano alert già notificati e non sovrascrivono i riferimenti preferiti aggiornati mentre l'app era chiusa. |
| Adapter multi-provider, non migrazione | CoinGecko è il default per mercato/UI/alert; CMC rimane selezionabile e disponibile per agent/resolver/MCP; consumer, checker e frontend dipendono solo dal contratto normalizzato. |
| Selettore UI/market senza fallback | Il provider UI/market richiede admin e viene persistito in RuntimeState. Gli alert usano `market_data.alert_provider` separato per non consumare CMC accidentalmente. |
| ID applicativo stabile | L'app conserva gli ID storici usati prima dello Step 3 (`bitcoin`, `binancecoin`, ecc.); gli adapter mantengono separati slug e ID nativi dei provider. |
| Compatibilità preferiti pre-Step 3 | Gli ID CoinGecko persistiti dalle release precedenti restano l'identità dell'app; l'adapter CMC traduce alias come `binancecoin/bnb`, `ripple/xrp` e `avalanche-2/avalanche` in entrambe le direzioni. |
| Preferiti indipendenti dal mercato | L'app richiede sempre tutti gli ID preferiti e conserva gli ultimi dati validi; il selettore 50/100/200/400/600 riguarda soltanto la lista mercato. |
| Selettore mercato diretto | Il frontend passa direttamente `perPage` e `page` a `/api/v1/market-data/markets`; non compone pagine artificiali e non sostituisce 100/200/400/600 con fallback da 50. |
| Ordinamento Preferiti indipendente | Mercati e Preferiti mantengono separatamente criterio, direzione e periodo visualizzato per Rank, 24h, 7g, Volume e Prezzo. |
| Logger moduli inizializzati lazy | Provider market-data e checker notifiche acquisiscono la configurazione structlog definitiva applicata durante l'avvio backend. |
| Catalogo CMC paginato | `/v1/cryptocurrency/map` viene letto in pagine da 5.000 elementi fino a esaurimento; i preferiti meno capitalizzati non spariscono perché fuori dalla prima pagina CMC. |
| Cache prima del conteggio crediti | Una cache hit non incrementa richieste o crediti CMC; il budget osservato espone livelli ok/warning/critical/exhausted sul limite Basic da 15.000 crediti/mese. |
| Single-flight provider | Richieste concorrenti con la stessa chiave condividono una sola chiamata esterna; le altre attendono il risultato in cache senza consumare rate limit o crediti. |
| Cache identita' provider | Le identita' app/provider gia' risolte restano in memoria nel `MarketDataRegistry`; le liste ranked popolano la stessa cache, cosi' refresh prezzo e preferiti ripetuti non rieseguono la mappa CMC completa. |
| MCP CMC separato da REST | Lo stato espone endpoint/header ufficiali senza chiavi; REST serve i flussi applicativi, MCP resta disponibile per futuri client agente. |
| OHLCV pubblico separato da CMC | `/api/v1/market-data/ohlcv` usa `ExternalOHLCVService` con Binance klines spot e fallback CEX, così CMC può restare sul piano Basic per latest pricing/catalogo senza endpoint OHLCV paid. |
| OHLCV CMC legacy | L'adapter CMC conserva `get_ohlcv` per compatibilità interna/test, ma la route pubblica dei grafici non lo invoca più. |
| CoinGecko valido per monitoring | CoinGecko resta pienamente utilizzabile per prezzi, liste, ricerca, alert e grafici; il volume delle sue candele OHLC non è fornito e il Volume Profile 5m richiede una fonte adeguata. |
| Feed Volume Profile Step 6 | Binance klines spot/futures sarà un feed specializzato del signal engine e non passerà dal `MarketDataProvider` generico. |
| Brain con poteri limitati | Claude può solo approve/reduce/block/skip; non aumenta leva, non inverte direzione e non cambia parametri. Senza Claude, dry-run usa fallback deterministico; live blocca fail-closed. |
| Loop safe-by-default | Il loop lento valuta solo la watchlist AI selezionata dall'utente; con watchlist vuota resta idle. Il loop veloce gestisce heartbeat e stato posizioni. L'esecuzione live richiede provider astratti, dati completi e guardrail risk/brain favorevoli. |
| Watchlist AI operativa | `eligible_tokens` definisce solo il perimetro consentito; `agent_watchlist_symbols` in RuntimeState definisce gli asset effettivamente scansionati dall'agente. Le modifiche sono admin-only e la mobile app mostra separatamente token tradabili e token attivi. |
| Warm-up OHLCV watchlist | Il backend scalda la cache klines 5m in background all'avvio e sui token appena aggiunti alla watchlist. Data Coverage e signal engine leggono la stessa cache, quindi gli asset passano a `ready` appena lo storico richiesto è scaricato senza bloccare il bind API. |
| Fallback CEX best-effort | Binance resta il feed primario del signal engine; Bitget e KuCoin intervengono solo quando Binance non copre un token e degradano a vuoto/None senza rompere il percorso principale. |
| Archivio dry-run live reset | I dati simulati storici possono essere copiati in `ArchivedRun`, rimossi dalle tabelle live e il `PortfolioState` riportato al capitale dry-run; dashboard/app leggono per default solo lo stato live pulito. |
| Dry-run sizing realistico | Il capitale dry-run default è 500 USD e il risk engine blocca i trade sotto 7 USD con `below_minimum_trade_size`, senza forzare size fuori dai parametri. |
| Costi dry-run espliciti | Spot e perp salvano fee/slippage/funding in posizione e trade; la dashboard mostra costi applicati e confronti taker/maker senza confonderli con PnL lordo. |
| Analytics read-only condivisa | Dashboard e mobile usano endpoint `/views/*` read-only per equity curve, breakdown asset, trade detail, grafici trade e operational stats; i numeri display sono normalizzati a due decimali. |
| Liquidazione Perp informativa | Le posizioni Perp salvano una stima di liquidazione derivata da entry/leva/side; il dettaglio trade la mostra come livello informativo, senza usarla nei grafici o come trigger di uscita. |
| Equity adjustment separato dal PnL | Versamenti e prelievi aggiornano capitale iniziale/equity e restano tracciati in tabella dedicata, evitando che un deposito storico appaia come profitto o perdita. |
| Dettaglio trade riproducibile | Alla chiusura viene salvato uno snapshot JSON di candele e livelli, inclusa la liquidazione Perp quando presente; le posizioni aperte usano un grafico live best-effort dallo stesso feed. |
| Grafici trade chiusi allineati | Il dettaglio trade normalizza le candele per timestamp, taglia lo snapshot alla candela che contiene `closed_at` e recupera le post-close con fetch storico `startTime` escluso dalla cache latest; app e dashboard disegnano la linea di chiusura dopo la candela reale di uscita. |
| Polling analytics 45s | Dashboard e tab mobile Agente aggiornano automaticamente i dati completi ogni 45 secondi; la tab mobile usa anche un refresh leggero single-flight ogni 15 secondi per Spot/Perp/Global, senza ricaricare wallet o dettagli trade quando un ciclo precedente è ancora in corso. |
| Step 7 solo additivo | La mobile app esistente resta intatta: le nuove funzioni agente vivono in `AgentTab`, il client API e' separato e `CoinCard` riceve solo prop opzionali per lo stato AI. |
| Priorita' UI Spot | Dopo conferma organizzatori del 18 giugno, solo i trade Spot contano per il ranking PnL Track 1; le viste Perp restano implementate per completezza architetturale ma non dominano la UI. |
| Mobile settings runtime | Le impostazioni agente salvate dalla mobile app sono persistite in `RuntimeState` e confermate dal backend; l'applicazione live completa ai loop va validata end-to-end prima della gara. |
| Dashboard separata | La dashboard Step 8 vive sotto `dashboard/`, usa porta 5176, `envDir` isolato dal root `.env` e token inseriti nel browser; read token e admin token possono persistere localmente per operatività. |
| Log viewer admin-only | I log backend sono esposti solo tramite endpoint admin con limite righe e redazione pattern sensibili; la dashboard non legge file locali e non espone path reali. |
| Data Coverage da cache signal engine | `/api/v1/agent/data-coverage` espone la copertura OHLCV in memoria per Spot/Perp senza scaricare dati a ogni refresh dashboard; lo Spot usa Binance klines 5m perché CMC non fornisce OHLCV 5m completo nel provider attuale. |
| Wallet dashboard | `/api/v1/execution/wallets` espone solo indirizzi pubblici, saldo BNB live e stato provider/RPC; le modifiche wallet/chain/provider/RPC restano admin-only e gli override vivono in `RuntimeState`. |
| Daily trade heartbeat | Il loop lento dell'agente verifica solo trade Spot del giorno UTC; se alle 20:00 UTC non esiste almeno un trade, tenta un heartbeat trade minimo e ritenta a ogni slow tick fino alle 23:30 UTC. |
| Diagnosi ordini 2026-07-18 | Backend e scanner agent risultano attivi; gli ingressi naturali sono bloccati dal drawdown cap operativo (`drawdown_pct` sopra la soglia prudente) e i segnali recenti non validi restano `skip/block`. |
| Guardrail visibili UI | `/api/v1/views/global` espone `risk_guardrail` con blocco/motivo/soglie; app mobile e dashboard mostrano un banner quando drawdown cap, daily loss o portfolio floor sospendono le nuove entrate. |
| Reset DB sblocca drawdown | Il reset admin `/api/v1/agent/dev/reset-db` ricrea subito `PortfolioState` al capitale dry-run con drawdown, max drawdown, daily loss, esposizione e contatori azzerati, evitando che un blocco risk rimanga dopo l'azzeramento dati. |
| Equity base se portfolio assente | La vista globale usa il capitale dry-run da `Settings` come equity iniziale quando `PortfolioState` non esiste ancora, evitando display a 0 USD dopo reset o prima del primo tick agente. |
| Portfolio base a startup | All'avvio backend viene creato un `PortfolioState` dry-run base se manca, così risk, sizing e UI non restano senza equity dopo reset manuali o DB vuoti. |
| Stop backend Windows corretto | `backend/scripts/stop_backend.ps1` termina il processo su porta 8001 senza usare la variabile PowerShell riservata `$PID`. |
| Run backend anti-doppio avvio | `backend/scripts/run_backend.ps1` controlla la porta configurata prima dell'avvio, termina eventuali listener esistenti e attende che la porta sia libera per evitare `Errno 10048`. |
| SQLite alert lock hardening | Il motore SQLite sincrono usa timeout/WAL/busy timeout e `AlertStore` serializza le scritture con retry su `database is locked`, riducendo gli errori durante sync alert concorrenti. |
| i18n legacy prima dello Step 8 | I testi frontend hardcoded saranno convertiti a EN default/IT conservato senza riscrivere la logica dei componenti. |
| Dual engine SQLAlchemy (Step 5) | Engine async aiosqlite per nuovo codice; engine sync sqlite3 per store legacy sincroni (`AlertStore`, `DeviceTokenStore`). Stesso file SQLite; serializzazione a livello file. Sicuro per single-user hackathon. |
| create_all senza Alembic (Step 5) | Schema creato automaticamente al boot; nessuno script di migrazione per deadline hackathon. Alembic resta in requirements per Step 10 (VPS). |
| user_id da Settings, mai hardcoded (Step 5) | Ogni repository riceve `user_id` come parametro. `settings.default_user_id` è l'unica fonte. Predisposizione multi-user senza refactor. |
| Timestamp UTC + block timestamp distinti (Step 5) | `timestamp_utc` = momento backend; `block_timestamp_utc` = orario blocco on-chain. Campi separati, semantica distinta. |
| Selettore provider persistito in RuntimeState (Step 5) | Un cambio admin sopravvive al riavvio; Settings è il default al boot. Nessun file JSON intermedio. |
| X402 budget compatibilità backward (Step 5) | `X402Client` accetta `session_factory` opzionale; test legacy usano SimpleNamespace senza DB → budget in-memory → test invariati. |
| Dashboard web su porta 5176 | `configs/instance.example.yaml` include `dashboard.port: 5176`; Step 8 usa Vite separato con dev server dedicato. |
| Deploy VPS senza segreti nel repo | Step 10 usa `/etc/cryptosentinel/backend.env` per variabili sensibili, `configs/instance.yaml` per installazione locale non segreta e `/home/cryptosentinel/.twak` per stato TWAK headless cifrato. |
| Dashboard statica dietro nginx | In produzione la dashboard viene compilata in `dist-dashboard`; nginx serve gli asset statici e proxya solo `/api/` e `/health/live` al backend locale. |
| Systemd come supervisor | Il backend gira come utente `cryptosentinel`, con restart automatico, hardening base e timer separati per backup e liveness. |
| Backup VPS conservativo | Il backup versionato copia SQLite, config YAML non segrete e stato TWAK cifrato se presente; non esporta `.env`, `configs/instance.yaml` o service account. |
| Questioni Telegram non bloccanti | Si procede con default prudenziali del piano e si aggiornano quando arrivano risposte. |
| Spot e Perp separati | TWAK gestisce spot; BNB Agent SDK/EIP-712 gestisce perp. Non condividono adapter o flusso di firma. |
| Execution testnet-only | Ogni firma/trade Step 4 è vincolato a BSC testnet; la mainnet è usata soltanto per la registrazione competizione. |
| Riserva gas hard | Il 15% del saldo BNB e un floor positivo restano non tradabili; il trade viene saltato se il gas non è inferiore al profitto atteso. |
| Retry dopo hash vietato | Ottenuto un transaction hash, non si reinvia: si riconcilia on-chain e lo stato incerto resta `unknown`. |
| Approvals esatte | Gli spender devono essere in whitelist e l'importo coincide con la necessità immediata; Permit2 auto-approval x402 non viene abilitato. |
| BNB SDK sostanziale | Il bridge espone policy firma, identità ERC-8004 e commerce ERC-8183; il pacchetto pubblico non espone un modulo memory dedicato. |
| RPC Tatum opzionale | `TATUM_RPC_API_KEY` viene inviato come `x-api-key` esclusivamente agli host Tatum; gli endpoint pubblici restano senza credenziali. |
| `AGENTS.md` come fonte regole | Centralizza le istruzioni ricorrenti per evitare di ripeterle a ogni sessione. |

## 6. NOTE PER IL REVISORE

| Area | Verifica richiesta |
|---|---|
| Security policy | Confermare che nessun `.env`, `secrets/`, service account JSON o chiave privata è stato letto o stampato. |
| Config precedence | Verificare `Settings`: env/.env > instance.yaml > YAML funzionali > default Pydantic. |
| Guardrail startup | Confermare fail-closed per `min_portfolio_value_usd <= 1`, `minimum_trades_per_day < 1`, drawdown cap oltre -15%, token count fuori range 100-200. |
| Multi-user readiness | Valutare se i file funzionali sono una buona base per default di sistema overridabili per utente. |
| GitHub Actions APK/Pages | Verificare che il job `build` produca `CryptoSentinel-debug.apk` e che `deploy-pages` aggiorni `gh-pages` solo su push a `main`. |
| GitHub Releases | Gli step release sono non bloccanti; se falliscono, controllare il job ma scaricare comunque l'APK dagli artifact CI. |
| Firebase Android app | Creare/scaricare un nuovo `google-services.json` per package `com.cryptosentinelai.app`, salvarlo come GitHub Secret `GOOGLE_SERVICES_JSON` in base64 e non committarlo. |
| Step 5 | Completato: readiness DB con SELECT 1 + latency; migrazione JSON→DB (FCM, alert, x402, provider selector); schema ORM completo; 16 test passed. |
| Step 7 | Nuova tab mobile agente additiva; verificare su APK/dispositivo reale layout, admin token persistito localmente, onboarding validation e kill switch contro backend avviato. |
| Documentazione uscite | Aggiornata al comportamento corrente: livelli ATR, breakeven con costi+buffer, trailing ATR/dinamico, TP1 parziale e time stop ATR-aware/orario. |
| Step 3 CMC reale | Verificato dall'utente con chiave esportata nel processo: `1 passed, 9 deselected in 3.71s`, senza leggere `.env`. |
| Step 3 i18n | Le chiavi backend Step 3 sono EN/IT; la conversione completa dei testi legacy frontend resta da chiudere prima di dichiarare lo Step 3 completamente raggiunto. |
| Execution safety | Mantenere admin come confine netto per endpoint che muovono fondi o modificano configurazione. |
| Config locale Step 4 | Aggiornare `configs/instance.yaml` con il contratto competizione ufficiale e x402 su BSC; i valori pericolosi sono bloccati. |
| Step boundary | Step 10 preparato a livello di artefatti e runbook; nessuno step successivo avviato. |
| Step 10 | Artefatti deploy preparati; completamento effettivo richiede accesso al VPS, DNS/TLS, compilazione sul server, segreti fuori repo e verifica runtime. |
| Ricognizione 2026-06-26 | Git working tree inizialmente pulito; aggiornati solo documenti e report per riflettere codice già presente, senza leggere file sensibili. |
| Agent onboarding | I futuri agenti devono leggere `AGENTS.md` prima di lavorare sul repository. |
