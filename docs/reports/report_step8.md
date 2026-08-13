# Report Step 8 - Dashboard Web Unificata

## 1. COSA È STATO FATTO

- Creato un progetto Vite separato in `dashboard/`, desktop-first, con dev server su porta `5176` e build output in `dist-dashboard`.
- Implementata la dashboard unificata con viste essenziali per i giudici: Overview, Spot, Global, System Health e kill switch.
- Aggiunte viste importanti: log viewer, impostazioni agente, onboarding validation, monitor prezzi e export JSON dello stato dashboard.
- Aggiunto endpoint backend admin-only `/api/v1/observability/logs` per consultare log backend con limite righe e redazione di pattern sensibili.
- Aggiunta vista Data Coverage dentro System Health.
- Aggiunto endpoint read-only `/api/v1/agent/data-coverage` per mostrare copertura OHLCV cache del signal engine.
- Aggiunta scheda Wallet nella sidebar dashboard: wallet per provider, saldo BNB live, provider spot/perp attivi e diagnostica RPC.
- Aggiunto endpoint read-only `/api/v1/execution/wallets` con indirizzi pubblici, saldo BNB live e stato dei provider senza esposizione di chiavi private.
- Aggiunta gestione multi-wallet nella scheda Wallet: selezione wallet attivo e aggiunta di indirizzi pubblici runtime.
- Aggiunti endpoint admin-only `PUT /api/v1/execution/wallet` e `POST /api/v1/execution/wallets` per selezionare o aggiungere wallet pubblici.
- Aggiunto selettore admin BSC chain `testnet/mainnet` nella scheda Wallet.
- Aggiunto endpoint admin-only `/api/v1/execution/network` per salvare la chain BSC attiva in `RuntimeState`.
- Aggiunto endpoint admin-only `/api/v1/execution/rpc-endpoint` per forzare l'RPC BSC attivo tramite override persistito in `RuntimeState`.
- Aggiornati `package.json` con script `dashboard:dev`, `dashboard:build`, `dashboard:preview`.
- Aggiornato `docs/PROJECT_STRUCTURE.md`.

## 2. COME È STATO FATTO

- La dashboard usa un `envDir` dedicato sotto `dashboard/env`, così Vite non carica il `.env` root dell'app mobile.
- Read token e admin token possono essere salvati localmente nella dashboard per comodità operativa; le operazioni privilegiate restano protette dagli endpoint admin-only backend.
- Le viste Spot/Global riusano gli endpoint già esistenti `/api/v1/views/spot` e `/api/v1/views/global`.
- System Health aggrega live, ready, heartbeat ed execution status.
- Il kill switch usa l'endpoint admin-only esistente `/api/v1/agent/kill-switch`.
- Settings e Onboarding riusano i contratti mobile Step 7 per evitare una seconda fonte di configurazione.
- Il log viewer passa dal backend per applicare redazione e bound server-side invece di leggere file lato client.
- Data Coverage legge la cache in memoria del feed Binance klines usato dal signal engine e mostra stato `insufficient`, `warming_up` o `ready` per asset/mercato.
- La dashboard mostra, in System Health, asset, mercato, candele disponibili vs richieste, timestamp prima/ultima candela, età dato e sorgente.
- Il default Backend URL della dashboard è stato allineato a `http://127.0.0.1:8001`; un vecchio valore locale `http://127.0.0.1:8000` viene migrato automaticamente.
- La scheda Wallet riusa i selettori provider esistenti (`/execution/provider`, `/execution/perp-provider`) e aggiunge la vista `/execution/wallets`.
- Il wallet attivo è applicato come override runtime a `Settings.wallet_address`; la lista include il wallet configurato e gli indirizzi aggiunti in `RuntimeState`.
- La chain BSC selezionata è applicata come override runtime ai nuovi service/provider execution tramite `RuntimeState`; `Settings` resta la fonte della configurazione statica.
- L'override RPC non riscrive la configurazione: salva solo l'indice scelto in `RuntimeState` e riordina gli endpoint BSC configurati mettendo quello scelto in testa per i nuovi client RPC.
- Le etichette RPC esposte alla dashboard sono host/index, non URL completi, per ridurre il rischio di mostrare token/API key eventualmente presenti nell'URL.

## 3. COSA È STATO VERIFICATO

- `npm run dashboard:build` completato con successo.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_observability_logs.py -q` completato con `2 passed`.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py backend/tests/unit/test_agent_api_payload.py backend/tests/unit/test_config_eligible_tokens.py backend/tests/unit/test_observability_logs.py -q` completato con `18 passed`.
- Verificata la compilazione TypeScript della dashboard tramite lo script di build dedicato.
- Verificata la redazione di valori tipo `api_key` e `token` nei test unitari del log viewer.
- Verificata la Data Coverage con cache hit e cache miss nei test unitari Step 6.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_execution_wallets.py backend/tests/unit/test_execution_providers.py backend/tests/unit/test_mobile_agent_step7.py backend/tests/integration/test_execution_api.py -q` completato con `19 passed`.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_execution_wallets.py backend/tests/unit/test_execution_providers.py backend/tests/integration/test_execution_api.py -q` completato con `16 passed` dopo il selettore chain.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_execution_wallets.py backend/tests/unit/test_config_eligible_tokens.py -q` completato con `8 passed` dopo la gestione multi-wallet.
- Verificato che l'override RPC riordini gli endpoint configurati e che lo snapshot wallet esponga saldo BNB e stato RPC.

## 4. SCOSTAMENTI DAL PIANO

- Le viste Perp complete non sono state messe al centro della dashboard: coerente con priorità aggiornata, dove solo i trade Spot contano per il ranking PnL Track 1.
- Demo/Replay è predisposto come export JSON dello stato corrente, non come replay operativo completo.
- Le notifiche browser avanzate non sono state implementate in questa iterazione; la dashboard mostra stati e avvisi in-app.
- L'append richiedeva "CMC OHLCV (spot)"; l'implementazione mostra Binance klines 5m anche per Spot perché il provider CMC attuale supporta OHLCV hourly/daily e non 5m OHLCV completo. Questo è coerente con il warm-up Spot già implementato sul signal engine.
- La vista usa gli asset eligible configurati come watchlist attiva finché non esiste uno scanner/watchlist agent persistito.
- La scheda Wallet mostra il wallet BSC configurato per provider spot/perp; non legge o mostra wallet key material e non espone URL RPC completi.
- L'aggiunta wallet accetta solo indirizzi EVM pubblici validi e non richiede né espone chiavi private. L'esecuzione firmata reale richiede comunque che il provider selezionato possa firmare per il wallet attivo.
- Il cambio chain non crea una seconda lista RPC: usa gli endpoint BSC configurati e mostra `chain_mismatch` se l'RPC risponde con chain id diverso dalla chain selezionata.

## 5. QUESTIONI APERTE

- Verifica end-to-end con backend reale avviato, token operativi e dati reali di gara.
- Eventuale estensione Perp dedicata nella dashboard se diventa utile per la demo.
- Eventuale replay operativo completo se resta tempo dopo le priorità Step 9.
- Persistenza o warm-up proattivo della cache OHLCV se serve coverage pronta subito dopo startup senza attendere il primo signal/evaluate.
- Per Step 9 restano da aggiungere i test mancanti già annotati: daily loss risk engine, guardia `$1`, meta-controller timeout, kill switch, heartbeat.
- Nel prossimo report va chiarito se la regola "minimo 1 trade/giorno con retry 20:00-23:30 UTC" è implementata nel loop o solo predisposta.

## 6. VERIFICHE TECNICHE

| Verifica | Esito |
|---|---|
| Dashboard build | Passata |
| Log viewer unit tests | Passati |
| Data Coverage unit tests | Passati |
| Wallets & Execution unit/API tests | Passati |
| Full backend suite | Non rieseguita integralmente in questo passaggio; debito HMAC TWAK pre-esistente non toccato |
| Dev server 5176 | Non lasciato avviato automaticamente durante la modifica |

## 7. STATO DELIVERABLE

Step 8 implementato in forma additiva e pronto per revisione. Non procedere a Step 9 senza approvazione del revisore.
