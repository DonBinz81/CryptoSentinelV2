# Report Step 6 - Agente AI Brain

Data: 2026-06-18

---

## COSA È STATO FATTO

### Brain e meta-controller

- Creato `backend/app/agent/brain/` con:
  - `models.py` - `BrainDecision` e azioni consentite: `approve`, `reduce`, `block`, `skip`.
  - `meta_controller.py` - client Claude via HTTP Anthropic con output JSON vincolato.
- Il meta-controller non può aumentare leva, invertire direzione o modificare parametri strategici.
- Se Claude non è configurato:
  - in `dry_run` usa fallback deterministico per test e simulazione;
  - fuori `dry_run` blocca fail-closed.

### Signal engine Spot V1

- Implementato `backend/app/agent/signals/common/indicators.py`:
  - `Candle`, sanitizzazione candele, EMA, VWAP, ATR, RSI, relative volume.
- Implementato `backend/app/agent/signals/spot/momentum.py`:
  - momentum + struttura;
  - VWAP primario;
  - EMA 20/50 di supporto;
  - ATR per stop e filtro estensione;
  - relative volume;
  - RSI come filtro;
  - scoring con pesi da `Settings`.

### Signal engine Perp V1

- Implementato `backend/app/agent/signals/perp/binance_klines.py`:
  - feed specializzato per signal engine;
  - Futures: `/fapi/v1/klines`;
  - Spot: `/api/v3/klines`;
  - non passa dal `MarketDataProvider` generico.
- Implementato `backend/app/agent/signals/perp/volume_profile.py`:
  - rolling Volume Profile 24h su candele 5m;
  - livelli POC, VAH, VAL;
  - Value Area da `perp_value_area_pct`;
  - filtro liquidità;
  - trigger mean reversion su rientro in value;
  - filtro trend via VWAP;
  - stop strutturale con ATR;
  - TP1/TP2/trailing e leva dinamica prudente.

### Risk management e kill switch

- Creato `backend/app/agent/risk/manager.py`:
  - universo eligible hard via `Settings.eligible_tokens`;
  - portfolio floor;
  - drawdown cap;
  - daily loss limit;
  - max open positions;
  - max exposure;
  - liquidity guard;
  - sizing nominale con cap rischio 1.5% a stop;
  - test scaling in live;
  - kill switch `running`, `soft_stop`, `hard_stop`, `degraded`.

### Agent service e dry-run

- Creato `backend/app/agent/service.py`:
  - orchestration tra signal engine, risk manager, brain e repository Step 5;
  - salvataggio `AgentDecision`;
  - dry-run con salvataggio `SpotTrade`/`PerpTrade` e posizione simulata;
  - live spot/perp fail-closed dove mancano dati necessari o venue configurata.
- L'agente usa i registry astratti già creati nello Step 4:
  - `ExecutionProviderRegistry` per spot;
  - `PerpExecutionRegistry` per perp.

### Loop e API

- Creato `backend/app/agent/loops/agent.py`:
  - loop veloce per gestione posizioni/heartbeat;
  - loop lento safe-by-default, senza trading implicito se non c'è scanner/watchlist configurata.
- Collegati i loop nel lifespan FastAPI.
- Creato `backend/app/api/routes/agent.py`:
  - `GET /api/v1/agent/status` read/admin;
  - `PUT /api/v1/agent/kill-switch` admin-only;
  - `POST /api/v1/agent/evaluate` admin-only per valutazioni esplicite dry-run/test.

---

## COME È STATO FATTO

### Fail-closed prima di tutto

L'agente non apre trade live se mancano:

- Claude operativo;
- asset eleggibile;
- stato portfolio valido;
- dati atomici per spot live;
- venue perp configurata.

Il dry-run invece consente simulazione e audit senza muovere fondi.

### Separazione Spot / Perp

Spot e Perp restano separati:

- Spot usa segnale momentum/struttura e provider spot astratto.
- Perp usa Volume Profile e provider perp astratto.
- Il feed Binance 5m è specializzato nel signal engine, come richiesto dal piano.

### Persistenza Step 5 riusata

Non sono state introdotte nuove tabelle:

- decisioni in `AgentDecision`;
- trade dry-run in `SpotTrade` / `PerpTrade`;
- posizioni simulate in `SpotPosition` / `PerpPosition`;
- stato portfolio letto da `PortfolioState`.

### Loop prudenziali

Il loop lento non inventa una watchlist e non scannerizza automaticamente asset reali senza configurazione esplicita. Questo evita trade impliciti non richiesti durante l'avvio del backend.

---

## COSA È STATO VERIFICATO

### Test mirati Step 6

Comando:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py
```

Esito:

- 4 passed.

Copertura:

- Spot momentum entra su momentum + volume spike.
- Volume Profile costruisce POC/VAH/VAL senza usare `MarketDataProvider`.
- Risk manager blocca asset fuori universo eligible.
- Agent service dry-run persiste decisione e trade.

### Lint mirato

Comando:

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend/app/agent backend/app/api/routes/agent.py backend/tests/unit/test_agent_step6.py
```

Esito:

- All checks passed.

### Import path

Comando:

```powershell
backend\.venv\Scripts\python.exe -c "import backend.app.agent.service; import backend.app.agent.loops; import backend.app.api.routes.agent; import backend.app.agent.signals.spot.momentum; import backend.app.agent.signals.perp.volume_profile; print('imports_ok')"
```

Esito:

- `imports_ok`.

### Suite backend

Comando:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests
```

Esito:

- 85 passed;
- 2 failed.

I due failed sono il debito HMAC TWAK preesistente indicato prima dello Step 6:

- `test_twak_hmac_matches_documented_wire_format`;
- `test_twak_hmac_supports_current_sdk_wire_format`.

Non sono stati modificati.

---

## SCOSTAMENTI DAL PIANO

| Punto piano | Stato | Motivazione |
|---|---|---|
| Claude meta-controller | Implementato con HTTP Anthropic diretto | Nessuna nuova dipendenza aggiunta; fail-closed se non configurato fuori dry-run. |
| Agente completo funzionante in dry-run | Raggiunto per valutazione esplicita segnale | Non è stata inventata una watchlist/scanner automatica non ancora definita lato UI/config; il loop lento resta safe-by-default. |
| Testabile in esecuzione reale via PancakeSwap | Predisposto ma fail-closed | Spot live richiede amount atomico e asset address espliciti; non viene derivato da USD per evitare errori. |
| Perp execution | Predisposta tramite provider astratto | Il provider BNB SDK resta boundary fail-closed finché non è configurata una venue perp concreta. |
| Modalità degradata | Implementata lato risk/service | Claude non disponibile fuori dry-run blocca nuove entrate; loop logga errori e non apre trade. |

---

## QUESTIONI APERTE

| Questione | Priorità | Note |
|---|---|---|
| Scanner watchlist/AI flag | Alta | Step 7 mobile aggiungerà flag AI e impostazioni agente; Step 6 espone valutazione esplicita ma non inventa UI/config. |
| Venue perp concreta | Alta | BNB SDK/EIP-712 è pronto come boundary, ma manca venue perp ufficiale/configurata. |
| Verifica live PancakeSwap | Alta | Richiede wallet, asset address, amount atomico e testnet/mainnet policy approvata. |
| Claude key reale | Media | Senza `ANTHROPIC_API_KEY`, dry-run usa fallback deterministico; live blocca fail-closed. |
| TWAK HMAC debt | Media | Restano i 2 failed preesistenti, non toccati. |
| Full strategy replay/export | Media | La base decisionale è persistita; replay/export dettagliato resta da rifinire per dashboard/demo. |

---

## VERIFICHE TECNICHE

| Verifica delegata | Esito |
|---|---|
| Feed Binance Volume Profile 5m specializzato | Implementato in `signals/perp/binance_klines.py`, fuori dal `MarketDataProvider`. |
| Signal engine modulare | Spot, Perp, common indicators e placeholder V2 restano separati. |
| Guardrail hard | Risk manager usa Settings validati e blocca portfolio floor, drawdown, daily loss, exposure e universo eligible. |
| Execution provider astratti | Agent service usa registry spot/perp Step 4; nessun riferimento diretto a TWAK/PancakeSwap nel brain. |
| Modalità dry-run/live/test scaling | Dry-run persiste simulazioni; live applica test scaling nel risk manager e richiede dati completi. |
| Kill switch | API admin e risk manager supportano soft/hard/degraded. |

---

## STATO DELIVERABLE

| Requisito Step 6 | Stato |
|---|---|
| Claude meta-controller con poteri limitati | Raggiunto |
| Strategia Spot V1 | Raggiunto |
| Strategia Perp V1 Volume Profile | Raggiunto |
| Feed Binance klines 5m specializzato | Raggiunto |
| Signal engine modulare + V2 placeholders preservati | Raggiunto |
| Risk management + guardrail | Raggiunto |
| Loop veloce/lento | Raggiunto, safe-by-default |
| Modalità degradata | Raggiunto |
| Kill switch | Raggiunto |
| Regole hardcoded qualificazione | Raggiunto tramite Settings + RiskManager |
| Modalità operative dry-run/live/test scaling | Parziale: dry-run funzionante, live fail-closed senza dati/venue completi |
| Esecuzione reale via PancakeSwap | Predisposta ma non verificata live |

**STATO FINALE: PARZIALE**

Step 6 è implementato nella base backend e verificato in dry-run. Restano verifiche live e configurazioni esterne (Claude key, venue perp, asset address/amount atomici, debito HMAC TWAK) prima di dichiararlo completo in produzione.
