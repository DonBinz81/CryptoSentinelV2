# Report — Guardiano: reentry_hours nello snapshot per il countdown in app (NOTE/95)

Data: 2026-08-25 · Branch: `claude/guardian-reentry-hours` · Richiesta di David via chat C

## 1. COSA È STATO FATTO

Aggiunto il campo `reentry_hours` allo snapshot del guardiano perp
(`guardian.snapshot()`), così l'oggetto `guardian` restituito da
`/agent/status` — quello che il banner dell'app legge — contiene tutti e tre
gli ingredienti del conto alla rovescia per la riattivazione: i due timestamp
dell'anchor (`last_stop_at`, `changed_at`, già presenti) e il passo di
de-escalation (`reentry_hours`, il campo nuovo). Il countdown resta
aritmetica lato client; nessuna logica nuova nel backend.

## 2. COME È STATO FATTO

Una riga in `backend/app/agent/guardian.py` (`snapshot()` riceve già la
`GuardianConfig`, quindi `"reentry_hours": cfg.reentry_hours` e basta), più
un commento che fissa la semantica per chi legge: la de-escalation non è un
timer assoluto ma "reentry_hours ore pulite" contate da
max(last_stop_at, changed_at), un passo alla volta, e ogni nuovo stop pieno
sposta l'anchor in avanti — quindi qualunque countdown mostrato è una
proiezione che si azzera a ogni nuovo stop, non una promessa. (Chat C ha già
previsto l'avviso corrispondente nel testo dell'app.)

La spec arrivata da chat C è stata verificata riga per riga sul codice prima
di applicarla (punti citati: `guardian.py:139-152`, `service.py:330`,
`guardian.py:231-263`): tutta esatta.

## 3. COSA È STATO VERIFICATO

- 3 test nuovi (`test_guardian.py::TestSnapshotCountdownFields`): il campo
  esiste; segue la config e non una costante (provato con reentry_hours=2.5);
  convive nello stesso snapshot con i due timestamp dell'anchor che il client
  deve combinare.
- **Anti-tautologia dimostrata sul serio, non presunta**: gli stessi 3 test
  eseguiti contro il `guardian.py` attualmente in produzione (pre-modifica)
  falliscono tutti e tre; col file nuovo passano 26/26 nel modulo.
- Suite completa su VPS: **403 passed, 2 failed, 2 skipped** — i soliti 2
  pre-esistenti (ticket-flow support, meta-controller reduce), verificati
  identici su main pulito più volte in questa sessione.

## 4. SCOSTAMENTI DAL PIANO

Nessuno. Unica correzione in corsa: il riferimento di nota nel commento era
NOTE/94, ma la 94 nel frattempo era stata presa da chat C (proprio per la
verifica del grafico live richiesta ieri) — aggiornato a NOTE/95.

## 5. QUESTIONI APERTE

- Il countdown in app è a cura di chat C (che ha già il testo pronto).
- `reentry_hours` è modificabile dai mobile settings: se David lo cambia
  dall'app mentre un countdown è visibile, il valore nello snapshot si
  aggiorna al prossimo poll di `/agent/status` — nessuna azione necessaria,
  ma il client non deve cachare il valore oltre un ciclo di poll.

## 6. STATO DELIVERABLE

Completo lato backend. Deploy su VPS (solo `guardian.py`, nessun cambio di
schema) con backup del DB e del file precedente, hash verificati, servizio
riavviato senza errori. Merge in main e push eseguiti.
