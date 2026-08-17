# Report - Allarme salute motore, filtro inversione per mercato, universo a 150

## COSA È STATO FATTO

- Aggiunto un **watchdog sulla salute del motore**: quando il ciclo di scansione fallisce,
  il backend manda una notifica push critica invece di fermarsi in silenzio.
- **Diviso il filtro inversione di mercato** in due interruttori indipendenti, uno per lo
  Spot e uno per il Perp, esposti entrambi nell'app.
- **Universo eligible portato a 150**: reintegrati ATOM e INJ per poter replicare la
  watchlist perp della V1 e confrontare le aperture.
- Regola corrispondente aggiornata in `AGENTS.md`, dichiarando la divergenza dall'upstream.

## COME È STATO FATTO

- **Watchdog** (`agent/service.py`): il loop dello scanner in `slow_tick` raccoglie gli
  errori per ciclo e li passa a `_maybe_alert_engine_health()`, che invoca
  `notify_agent_critical()` — funzione già presente nel codice ma **mai chiamata**, né da
  noi né nell'upstream. Due inneschi: un singolo errore di storage/sessione (`malformed`,
  `rolled back`, `disk I/O error`, `database is locked`, `no such table`), perché avvelena
  l'intero ciclo, oppure una quota di asset falliti oltre `agent_health_alert_error_ratio`.
  Throttle configurabile, default 30 minuti.
- **Filtro inversione**: nuovi `spot_market_reversal_filter_enabled` (default `true`) e
  `perp_market_reversal_filter_enabled` (default `false`), con default funzionali nei YAML
  dei rispettivi mercati. Il flag globale storico resta come fallback per i `.env`
  esistenti. I tre punti d'uso in `service.py` leggono ora il flag del proprio mercato;
  la funzione di calcolo gira solo se almeno un mercato lo richiede.
  Motivazione: è un filtro **trend-following**, coerente con lo Spot (momentum) e
  controproducente sul Perp (mean-reversion), dove blocca i long proprio quando il prezzo
  rientra nel value area.
- **Universo**: `configs/eligible_tokens.yaml` da 148 a 150 voci, con il razionale nel
  commento di testa.

## COSA È STATO VERIFICATO

- Suite completa sulla VPS in copia isolata (`/tmp`), interprete di produzione:
  **236 passed, 3 failed, 2 skipped**.
  Le 3 failure sono **preesistenti**, dimostrate eseguendo lo stesso comando sul baseline
  `HEAD` senza le modifiche: `test_meta_controller_reduce`,
  `test_agent_service_dry_run_persists_perp_decision_and_trade` (dipende dai dati di
  mercato reali) e `test_support_ticket_thread_and_admin_status_flow`.
- **6 test nuovi**: indipendenza dei due flag, corto circuito con entrambi spenti,
  allarme su errore di storage, throttle dell'allarme, riarmo dopo la finestra, nessun
  allarme per un singolo asset senza klines, allarme su fallimento di massa.
- `npx tsc --noEmit` pulito. Nessuna build frontend eseguita (regola `AGENTS.md` e
  richiesta dell'utente: build APK in corso su altra sessione).
- Il valore `149` non è cablato in alcun guardrail di produzione: compare solo come dato
  fittizio nei test e nella regola di `AGENTS.md`, ora aggiornata.
- Nomi dei file in staging controllati: nessun `.env`, segreto o `instance.yaml`.

## SCOSTAMENTI DAL PIANO

- `AGENTS.md` è il documento di regole dell'upstream: modificarne una è una divergenza.
  È stata **autorizzata esplicitamente dal proprietario del repository** il 17/08/2026 e
  la riga aggiornata dichiara la divergenza e il motivo.
- I due interruttori nuovi sono stati collocati nella sezione "Filtri globali" esistente,
  con etichette "— Spot" e "— Perp", invece di essere spostati nelle rispettive schede:
  scelta a rischio minimo, per non alterare la struttura verificata con lo snapshot
  meccanico del refactor precedente.

## QUESTIONI APERTE

- Dopo il deploy il filtro inversione **si riattiva sullo Spot** (era stato spento
  dall'utente tramite il vecchio flag unico) e resta **spento sul Perp**.
- I due interruttori compariranno nell'app solo con il prossimo APK; fino ad allora
  valgono i default del backend.
- La watchlist perp va allineata a mano dall'app: restano 16 coin da togliere.
- L'allarme non è ancora stato provato su un guasto reale: la logica è coperta dai test,
  ma il primo riscontro sul campo arriverà al prossimo incidente.

## STATO DELIVERABLE

- Deliverable completo e testato. Commit e deploy sulla VPS eseguiti dopo il controllo
  finale approvato dall'utente.
