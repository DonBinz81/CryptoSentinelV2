# Report — Colonna `strategy` su perp_positions/perp_trades (Fase 0 perimetro E)

Data: 2026-08-22 · Branch: `chat-e/fase0-strategy-column` · Riferimenti: NOTE/85 (vincolo 1), NOTE/87

## COSA È STATO FATTO

Aggiunta la colonna `strategy` (VARCHAR(32) NOT NULL DEFAULT 'volume_profile_v1')
alle tabelle `perp_positions` e `perp_trades`, come prerequisito della seconda
strategia perp: ogni riga registra il motore che l'ha aperta, le gambe di
chiusura la ereditano dalla posizione. Nessuna logica la legge: zero effetto sul
comportamento di trading.

- `backend/app/persistence/database.py` — 2 voci nella lista di migrazioni ADD
  COLUMN idempotenti.
- `backend/app/persistence/models/positions.py` — campo `strategy` su
  `PerpPosition` + costante condivisa `DEFAULT_PERP_STRATEGY`.
- `backend/app/persistence/models/trades.py` — campo `strategy` su `PerpTrade`.
- `backend/app/agent/service.py` — valorizzazione all'apertura (PerpTrade open e
  PerpPosition in `_simulate_trade`); ereditata con `strategy=pos.strategy` sulle
  4 gambe: chiusura standard, vendita Smart SL, rebuy per livello, rebuy
  above-entry.
- `backend/tests/unit/test_strategy_column.py` — 4 test nuovi.
- `docs/PROJECT_STRUCTURE.md` aggiornato.

## COME È STATO FATTO

Il DEFAULT costante a livello di schema fa sì che SQLite applichi
`volume_profile_v1` anche alle righe precedenti la migrazione in lettura: lo
storico non è mai NULL, quindi l'instradamento del futuro doppio guardiano
(NOTE/85, verifica incrociata punto 3) non può saltare in silenzio. La costante
vive in `positions.py` ed è importata da `trades.py` e `service.py`: un solo
punto di verità per il valore di default.

## COSA È STATO VERIFICATO

Sulla VPS (unico ambiente di test, Windows ARM64 locale non esegue la suite),
pacchetto `backend + configs + pytest.ini` in `/tmp/chat_e_test`:

- Suite completa con le modifiche: **364 passed, 2 failed, 2 skipped**.
- Baseline `main` pulito nello stesso ambiente (via `git archive`): **360
  passed, 2 failed, 2 skipped** — gli stessi 2 failure
  (`test_support_ticket_thread_and_admin_status_flow`,
  `test_meta_controller_reduce`), quindi **preesistenti**; i +4 passed sono i
  test nuovi.
- Import backend con le modifiche: `from backend.app.main import app` OK.
- I 4 test nuovi coprono: default ORM mai NULL, valore esplicito conservato,
  migrazione su riga legacy (DROP COLUMN + reinserimento + doppia esecuzione
  della migrazione = idempotenza), ereditarietà apertura→chiusura attraverso il
  motore vero (`_check_sl_tp` con stop pieno).

## SCOSTAMENTI DAL PIANO

- Scoperto durante il run: il pacchetto di test storico senza `pytest.ini` alla
  radice fa fallire ~80 test per fixture async non risolte (asyncio strict
  mode). Con `pytest.ini` incluso la suite torna alla baseline. Annotato per le
  prossime sessioni di test su VPS.
- Nessun default YAML aggiunto: non è un parametro di configurazione ma una
  colonna dati (la regola AGENTS.md sui default YAML non si applica).

## QUESTIONI APERTE

- Il ramo live `_execute_perp` non scrive `PerpPosition`/`PerpTrade` (NOTE/68):
  quando il perimetro A implementerà il live, `strategy` andrà popolata anche lì.
- Il valore per la seconda strategia (`pullback_continuation_v1`) è proposto in
  NOTE/87 §10 e verrà usato solo dalla Fase 2, dopo verdetto positivo del
  backtest pre-registrato.

## STATO DELIVERABLE

Completo sul branch `chat-e/fase0-strategy-column`, testato su VPS, non ancora
committato/deployato (in attesa dell'ok esplicito per commit e deploy, regola
resume).
