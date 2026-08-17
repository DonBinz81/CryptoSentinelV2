# Report - Execution layer Step 1: schema minimale Position → Order → Execution

## COSA È STATO FATTO

- **Passo 0 — rete di regressione**: golden test del ciclo completo di una posizione perp
  (entry → TP1 → 3 scalini ratchet → uscita), LONG e SHORT, che congela il comportamento
  economico attuale. Committato da solo (`d377653`), senza alcuna modifica di produzione.
- **Schema minimale** (perimetro deciso con l'utente, nient'altro):
  - `perp_trades.position_id` — collegamento esplicito fra esecuzione e posizione;
  - **backfill idempotente** dello storico dal prefisso del `trade_id`;
  - nuova tabella **`perp_orders`** minimale;
  - i nuovi `PerpTrade` valorizzano `position_id`, incluso il trade di apertura.
- `perp_positions.venue`: **già presente e già valorizzato** (`venue="dry_run"`), nessuna
  modifica necessaria.
- Aperta nota tecnica separata sulla foreign key malformata `support_messages` →
  `support_tickets` (`NOTE/41`), esplicitamente fuori perimetro.

## COME È STATO FATTO

- `perp_trades.position_id`: colonna nullable indicizzata (nullable per lo storico e per
  eventuali esecuzioni senza posizione). Migrazione con il pattern idempotente già in uso
  (`ALTER TABLE … ADD COLUMN` in `try/except`, `database.py`).
- **Backfill** (`_backfill_perp_trade_position_id`): estrae il position id dal formato
  `<prefisso>_<position_id>_<hex8>` con `substr`, solo su righe con `position_id IS NULL`
  e solo per i prefissi `cls_`, `add_`, `ssl_`. I trade di apertura (`dry_`) non
  contengono il position id e restano `NULL`. Errori non bloccano l'avvio.
- **`perp_orders`**: `order_id`, `position_id`, `user_id`, `venue`, `purpose`, `status`,
  `requested_qty`, `filled_qty`, `venue_order_id` (nullable), `tx_hash` (nullable),
  `created_at`, `updated_at`. **Nessun campo di telemetria**: verrà modellata su quello che
  la venue reale restituisce, non su ipotesi.
- In `_simulate_trade` il `position_id` viene generato **prima**, così il trade di apertura
  e la posizione condividono lo stesso identificatore.

## COSA È STATO VERIFICATO

- **Controlli pre-migrazione sul DB di produzione** (a servizio fermo, poi riavviato):
  `integrity_check` **ok**, `quick_check` **ok**, `agent_decisions` leggibile (9.678 righe),
  `perp_positions` 11, `perp_trades` 36, `spot_trades` 9.
  Backup: `~/backups/pre_schema_20260817_112647.db` (4,4 MB; nessun `-wal`/`-shm` residuo).
  ⚠️ `foreign_key_check` segnala un difetto **preesistente e circoscritto** allo schema
  support: analizzato e documentato in `NOTE/41`, autorizzato a procedere.
- **Backfill provato su copia isolata del DB reale**, mai in produzione:
  | prefisso | trade | collegati |
  |---|---|---|
  | `cls_` | 23 | **23** |
  | `ssl_` | 2 | **2** |
  | `dry_` | 11 | 0 (atteso: nessun position id nell'identificatore) |

  Controllo incrociato: **25 collegamenti validi** verso `perp_positions`, **0 orfani**.
- **Golden test invariato**: PnL per tranche identici prima e dopo lo schema —
  `50,00` (TP1) · `18,75` · `21,25` · `29,25` (scalini) · `15,00` (profit lock);
  quantità chiuse `5 / 1,25 / 1,25 / 1,5 / 1` in entrambe le direzioni.
- **Suite completa sulla VPS**: **246 passed, 2 failed, 2 skipped**
  (baseline: 236 passed, 3 failed). Le 2 failure sono preesistenti
  (`test_meta_controller_reduce`, `test_support_ticket_thread_and_admin_status_flow`);
  la terza (`test_agent_service_dry_run_persists_perp_decision_and_trade`, flaky perché
  dipende dai dati di mercato reali) è verde in questa esecuzione.
- 9 test nuovi: 3 golden + 6 di schema (tabella, ciclo dell'ordine, persistenza del
  collegamento, backfill, idempotenza del backfill, presenza dell'indice).

## SCOSTAMENTI DAL PIANO

- **Regressione introdotta e corretta durante il lavoro**: la sostituzione automatica che
  aggiungeva `position_id` ai trade ha colpito anche due `SpotTrade`, che non hanno quel
  campo → 8 test spot rossi. Individuata dalla suite completa e rimossa: lo Step 1 riguarda
  solo il perp. È il motivo per cui la suite intera va eseguita a ogni passo.
- `perp_positions.venue` non è stato aggiunto perché **già esistente**: il perimetro si è
  ridotto rispetto al piano.
- Il trade di apertura ora porta il `position_id` (non era esplicitamente richiesto): senza,
  l'esecuzione più importante della posizione sarebbe rimasta scollegata.

## QUESTIONI APERTE

- **Nessun deploy eseguito**: la migrazione non è ancora stata applicata al database di
  produzione. Avverrà al primo riavvio del backend dopo il deploy, tramite il bootstrap.
- `perp_orders` **non è ancora usata da nessuno**: la scriverà il `DryRunPerpVenue` nello
  step successivo. Oggi è struttura, non comportamento.
- Foreign key malformata su support: `NOTE/41`, da affrontare separatamente.
- I trade di apertura storici (`dry_`, 11 righe) restano senza `position_id`: non è
  ricostruibile dall'identificatore. Solo i nuovi lo avranno.

## STATO DELIVERABLE

- Schema minimale completo e verificato, comportamento economico invariato.
- **Non committato e non deployato**: in attesa di approvazione, come richiesto.
- Prossimo passo (da autorizzare): `ExecutionResult`, `DryRunPerpVenue`, router minimo.
