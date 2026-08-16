# Report - Corruzione del database SQLite e ripristino

Data: 2026-08-16

---

## COSA È STATO FATTO

Diagnosticata e riparata una corruzione del database di produzione
(`backend/local.db`): la tabella `agent_decisions` era illeggibile e ogni ciclo
dello scanner falliva con rollback della sessione, impedendo all'agente di
registrare le decisioni.

Emersa mentre si verificava, su richiesta dell'utente, se le chiavi CMC e
Anthropic avessero causato malfunzionamenti: **entrambe risultate sane**.

## COME È STATO FATTO

Diagnosi per esclusione, su evidenze dai log (regola: prima i log, poi il codice):

| ipotesi | verifica | esito |
|---|---|---|
| Doppio engine SQLAlchemy async+sync | `agent_decisions` e' scritta solo dall'engine async (`service.py:2242`) | scartata |
| Concorrenza fra processi | `lsof` + `ps`: un solo processo backend | scartata |
| Disco pieno | `df`: 43% usato | scartata |
| Guasto disco/filesystem | `dmesg` pulito; `tune2fs`: *Filesystem state: clean* | scartata |
| Crash / OOM | uptime 32 giorni, nessun OOM-kill | scartata |
| CMC / Anthropic | entrambe HTTP 200 con risposta valida | scartata |

**Causa accertata**: il reset del DB delle 11:10 e' stato eseguito **a servizio
attivo** (1135 righe di log fra 11:08 e 11:14 mentre il file veniva spostato).
In WAL mode i file `-wal` e `-shm` del vecchio database sopravvivono e vengono
riapplicati a quello nuovo. Conteggio errori a supporto:

```
09:00-11:10 (DB vecchio): 1068   ← gia' corrotto, per questo fu resettato
11:10-20:00 (DB nuovo):     10   ← un DB appena creato non ne produce nessuno
20:00-21:00:               176
```

Ripristino tramite script con guardie: `wal_checkpoint(TRUNCATE)` →`.dump` delle
sole tabelle leggibili → import in DB nuovo → sostituzione solo se
`integrity_check` = `ok` e `runtime_state` non vuota.

## COSA È STATO VERIFICATO

- `PRAGMA integrity_check`: **ok** (prima: centinaia di pagine corrotte).
- Zero errori `malformed` attribuiti al processo nuovo; i 62 residui appartengono
  al PID precedente (ultimo alle 21:00:33, riavvio alle 21:02:49).
- Watchlist invariate (16/16/11), trade e impostazioni preservati.
- **Due posizioni aperte recuperate** che il DB corrotto non mostrava: COMP perp e
  una seconda ETH spot. Causa: `count(*)` usa gli indici danneggiati, `.dump`
  legge i dati reali.
- Dimensione DB: 1,9 MB → 155 KB (pagine corrotte eliminate).
- Backup: `~/backups/pre_recover_20260816_205530.db` (+ `-wal`, `-shm`),
  `settings_20260816_205530.json`, `/tmp/dbfix_*/before.db`.

## SCOSTAMENTI DAL PIANO

- **Il primo comando proposto era pericoloso.** Usava `sqlite3 ".recover"`, che
  ignora il WAL: provato sulla copia di backup produceva un file da **0 byte**.
  Avrebbe sostituito la produzione con un DB vuoto. Non e' stato eseguito per un
  errore di quoting di PowerShell; la procedura e' stata riprogettata e provata
  su copia prima di applicarla.
- **La procedura di reset documentata era la causa del guasto**: cancellava solo
  `local.db` lasciando `-wal` e `-shm`. Corretta.
- Due record di trade di apertura (COMP, ETH) erano andati persi nel rollback:
  ricostruiti dai dati delle posizioni con fee derivate dal nozionale e marcati in
  `notes` come `RICOSTRUITO`.

## QUESTIONI APERTE

- Lo storico di `agent_decisions` anteriore al ripristino e' **perso**: la tabella
  era illeggibile e non recuperabile.
- La catena causale e' **inferita da prove convergenti**, non da una riproduzione
  diretta del guasto.
- I 10 errori fra 11:10 e 20:00 non sono stati analizzati uno per uno: usati come
  indizio quantitativo, non come prova del meccanismo.

## STATO DELIVERABLE

**Completato.** Database ripristinato e verificato, backend attivo, procedura di
reset corretta e documentata. Nessuna modifica al codice applicativo.
