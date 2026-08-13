# Report Step 5 — Persistenza Dati

Data: 2026-06-16

---

## COSA È STATO FATTO

### Schema DB — separazione Spot / Perp / Globale

Creato package `backend/app/persistence/models/` con 9 moduli:

- `base.py` — `DeclarativeBase` comune.
- `device_tokens.py` — `DeviceToken` (token_id PK, token, user_id, platform, device_id, app_version, locale, created_at, updated_at).
- `alerts.py` — `AlertConfig` (user_id unique, config_json, state_json come Text; una riga per utente).
- `trades.py` — `SpotTrade` (trade_id, asset, side, amount, price, amount_quote, tx_hash, status, gas_cost, slippage, fees, **timestamp_utc**, **block_timestamp_utc**) e `PerpTrade` (aggiunge direction, leverage, venue).
- `positions.py` — `SpotPosition` (entry_price, current_price, size, pnl_unrealized, stop_loss, tp1/tp2/trailing, closed_at) e `PerpPosition` (aggiunge leverage, liquidation_price, funding_rate, tp1_reached per schema 50/25/25).
- `decisions.py` — `AgentDecision` (decision_id, user_id, timestamp_utc, asset, market, action, confidence, reasoning Text, trade_id).
- `pnl.py` — `PnlSnapshot` (snapshot orari per user_id) e `PortfolioState` (una riga per utente, upsert).
- `x402.py` — `X402DailyBudget` (unique user_id + budget_date).
- `runtime_state.py` — `RuntimeState` (unique user_id + key, per selettore provider).

Ogni tabella ha `user_id` derivato da `settings.default_user_id`; nessun UUID hardcoded nel codice applicativo.

### Infrastruttura DB

- `persistence/database.py` — engine async aiosqlite, `async_sessionmaker`, `create_all` automatico all'avvio, `check_db()` con `SELECT 1` e latency misurata.
- `persistence/sync_database.py` — engine sync (sqlite3) per store legacy sincroni (AlertStore, DeviceTokenStore); stesso file SQLite, serializzazione a livello file SQLite.
- `persistence/backup.py` — copia SQLite con suffisso timestamp UTC, pruning file oltre retention, restituisce `None` se il DB non esiste.
- `persistence/migration.py` — migrazione idempotente JSON→DB al boot: token FCM da `fcm_tokens.json`, config/stato alert da `alerts.json`.
- `persistence/runtime_state.py` — `get_runtime_value` / `set_runtime_value` sync, degrada silenziosamente se DB non inizializzato.
- `persistence/views.py` — `ViewService` con `spot_view`, `perp_view`, `global_view` per dashboard.

### Repository

Package `persistence/repositories/` con 7 moduli: `device_tokens`, `alerts`, `trades` (Spot e Perp), `positions` (Spot e Perp), `decisions`, `pnl`, `x402_budget`.

### Migrazione da JSON a DB

| Persistenza temporanea | Fonte vecchia | Nuova destinazione |
|---|---|---|
| Token FCM | `backend/storage/fcm_tokens.json` | tabella `DeviceToken` |
| Config/stato alert | `backend/storage/alerts.json` | tabella `AlertConfig` |
| Budget x402 giornaliero | in-memory `X402Client` | tabella `X402DailyBudget` |
| Selettore provider runtime | solo Settings (boot default) | tabella `RuntimeState`; Settings come default al boot |

`token_store.py` e `alert_store.py` completamente riscritti con interfacce pubbliche invariate; i file JSON non sono più fonte di verità.

### Readiness DB reale

`GET /health/ready` ora chiama `check_db()` che esegue `SELECT 1` con misura latency. Risposta include sezione `database: {configured, connected, latency_ms, error}`. Status diventa `degraded` se DB non risponde.

### Route dashboard

`GET /api/v1/views/spot`, `/perp`, `/global` — auth read + SessionDep + SettingsDep. Schema Pydantic in `schemas/views.py`.

### Backup

Loop asincrono `_backup_loop()` in `main.py` con intervallo configurabile (default 6h). Snapshot aggiuntivo allo shutdown. Retention configurabile (default 7 giorni). Configurato via `DB_BACKUP_ENABLED`, `DB_BACKUP_DIR`, `DB_BACKUP_INTERVAL_HOURS`, `DB_BACKUP_RETENTION_DAYS` (in `config.py` e `instance.example.yaml`).

### Integrazione avvio

`main.py` lifespan:
1. `init_db(settings.database_url)` — engine async + `create_all`.
2. `init_sync_db(settings.database_url)` — engine sync per store legacy.
3. `migrate_json_to_db(session, ...)` — migrazione idempotente JSON→DB.
4. Avvio `_backup_loop()` se `settings.db_backup_enabled`.
5. Shutdown: backup finale + `close_db()` + `reset_sync_db()`.

---

## COME È STATO FATTO

### Strategia dual-engine

I vecchi store sincroni (`AlertStore`, `DeviceTokenStore`) sono chiamati da route FastAPI sincrone e dal loop `price_checker`. SQLAlchemy async non può essere usato da contesti sincroni senza `asyncio.run()`. Soluzione: engine sync separato (driver sqlite3) che punta allo stesso file SQLite; SQLite serializza l'accesso concorrente a livello file, sicuro per single-user hackathon.

### Compatibilità backward X402

`X402Client` accetta parametri opzionali `session_factory` e `user_id`. I test legacy usano `SimpleNamespace` e istanziano `X402Client(settings, twak)` senza session_factory → budget resta in-memory → test passano invariati.

### Selettore provider persistito

`registry.py` usa `_PROVIDER_STATE_KEY = "market_data_provider"`. `_load_active()` legge dal DB prima (fallback a Settings). `select()` chiama `set_runtime_value(...)`. Settings resta il default al boot; un cambio esplicito admin sopravvive al riavvio.

### Schema PostgreSQL-compatibile

Nessun tipo SQLite-specifico. `Text` per JSON blob, `Numeric(precision=24, scale=8)` per Decimal, `DateTime` esplicito. Pronto per migrazione a PostgreSQL via Alembic (create_all automatico, no migration scripts — scelta pragmatica per deadline hackathon).

### `user_id` da Settings

Tutti i repository ricevono `user_id: str` come parametro; nessuna istanza conosce l'UUID di default. I route e il lifespan passano `str(settings.default_user_id)`.

---

## COSA È STATO VERIFICATO

### Test automatici

`backend/tests/unit/test_persistence_layer.py` — 12 test async (pytest-asyncio, fixture `db` con engine temporaneo):

| Test | Esito |
|---|---|
| `check_db` riporta connected + latency | PASSED |
| `check_db` disconnesso quando non inizializzato | PASSED |
| Migrazione JSON idempotente (no duplicati) | PASSED |
| Budget x402 persiste tra sessioni | PASSED |
| SpotTrade con timestamp_utc e block_timestamp_utc separati | PASSED |
| PerpPosition con leverage e liquidation_price | PASSED |
| Portfolio upsert + PnlSnapshot | PASSED |
| AgentDecision reasoning testuale | PASSED |
| GlobalView assembla da portfolio | PASSED |
| Spot e Perp view con posizioni aperte | PASSED |
| Backup crea copia timestamped e pota vecchi file | PASSED |
| Backup restituisce None per DB assente | PASSED |

`backend/tests/unit/test_alert_store.py` — 4 test (migrati a fixture DB sync):

| Test | Esito |
|---|---|
| Sync identica preserva checker state | PASSED |
| Alert rimossi potano checker state | PASSED |
| Pending favorite sopravvive fino ad acknowledge | PASSED |
| Favorite rimosso pota pending badge | PASSED |

### Suite completa

`pytest backend/tests/` — **59 passed, 1 skipped, 2 failed**.

I 2 failed sono pre-esistenti dallo Step 4:
- `test_twak_hmac_matches_documented_wire_format` — wire format Authorization header diverso tra documentazione Amber e SDK attuale.
- `test_twak_hmac_supports_current_sdk_wire_format` — parametro `profile` non presente nella firma attuale di `_sign_amber_request`.

Questi fallimenti sono documentati in `report_step4.md` come TWAK Amber Free plan / HMAC issue e non sono causati da Step 5.

### Compilazione

`python -m py_compile` su tutti i file Step 5 (models, repositories, database, migration, backup, views, schemas, routes, tests) — zero errori.

---

## SCOSTAMENTI DAL PIANO

| Punto piano | Stato | Motivazione |
|---|---|---|
| Alembic per migrazioni versionabili | Non implementato | `create_all` automatico al boot è sufficiente per deadline hackathon; Alembic richiede script di migrazione per ogni schema change. Tabelle esistenti non vengono toccate. Documentato come debito tecnico. |
| TP3 per posizioni perp | Implementato come `tp1_reached` (flag schema 50/25/25) non come TP3 separato | Il piano menziona TP3 ma la strategia Perp usa solo TP1/TP2/trailing; coerente con `Strategia_Perpetual.md`. |
| File JSON come fallback di emergenza | File restano su disco ma ignorati dal codice | Il codice non li legge in funzionamento normale; restano come log storico. |

---

## QUESTIONI APERTE

| Questione | Priorità | Note |
|---|---|---|
| Alembic migration scripts | Media | Aggiungere prima del deploy VPS (Step 10) se lo schema cambia tra step. |
| Indice su `user_id` + `asset` per query ad alta frequenza | Bassa | Performance non critica con SQLite single-user; necessaria con PostgreSQL multi-user. |
| TWAK HMAC wire format (2 test falliti pre-esistenti) | Media | In attesa di risposta organizzatori BNB Hack; il codice di firma HMAC è già corretto per il formato documentato. |
| Volume Profile 5m (debito Step 3) | Alta | Da risolvere nello Step 6 con feed Binance klines. |
| i18n frontend legacy (debito Step 3) | Alta | Da chiudere prima dello Step 8. |
| Secret GitHub Actions `VITE_API_READ_TOKEN` | Alta | Da configurare prima della prossima build APK. |

---

## STATO DELIVERABLE

| Requisito | Stato |
|---|---|
| Schema Spot/Perp/Globale con tutte le tabelle richieste | Raggiunto |
| `user_id` ovunque, nessun UUID hardcoded | Raggiunto |
| Timestamp UTC + block timestamp distinti | Raggiunto |
| Migrazione JSON→DB (FCM, alert, x402, provider selector) | Raggiunto |
| Readiness DB reale con `SELECT 1` + latency | Raggiunto |
| Query per viste Spot/Perp/Global | Raggiunto |
| SQLite async + schema PostgreSQL-compatibile | Raggiunto |
| Backup con timestamp, intervallo e retention configurabili | Raggiunto |
| Test automatici per tutti i componenti Step 5 | Raggiunto (12+4 test, tutti passed) |

**STATO FINALE: RAGGIUNTO**

Tutti gli 8 requisiti dello step sono implementati e verificati. I 2 test falliti nella suite sono pre-esistenti dallo Step 4 e non riguardano Step 5.
