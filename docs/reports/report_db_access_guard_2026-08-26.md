# Report - Impedire tecnicamente la quinta corruzione del database

Data: 2026-08-26
Branch: `chat-infra/db-access-guard`
Perimetro: D — infrastruttura e dati

---

## COSA È STATO FATTO

Il 26/08 il database di produzione si è corrotto per la quarta volta, sempre per la stessa
causa: qualcuno ha aperto `local.db` con `sqlite3` mentre il backend era in esecuzione. Le
prime tre volte la risposta era stata documentale (regola zero, note 29/54); il 26/08 la
regola era scritta in rosso in cima al prompt di ogni sessione ed è stata violata comunque —
non per negligenza, ma perché «è solo una SELECT» è un ragionamento plausibile per chi non
conosce il comportamento di SQLite in WAL mode.

Due strumenti, che lavorano in coppia:

1. **`csv2-db`** (`deploy/scripts/db_query.sh`) — interroga il database **senza aprirlo**:
   copia il file e i sidecar in `/tmp`, esegue la query sulla copia, pulisce. Rende la
   procedura corretta un comando solo.
2. **Il guard** (`deploy/scripts/sqlite3_guard.sh`, installato come `/usr/local/bin/sqlite3`)
   — rifiuta l'apertura del file di produzione mentre il servizio è attivo, spiegando perché
   e indicando `csv2-db`.

L'ordine conta: prima si rende facile la cosa giusta, poi si blocca quella sbagliata. Un
divieto senza alternativa comoda produce solo aggiramenti.

## COME È STATO FATTO

**`csv2-db`**: `sudo cp` del `.db` più `-wal` e `-shm` (senza il `-wal` la copia perde ogni
transazione non ancora consolidata), `chown` all'utente chiamante, query sulla copia,
rimozione. Opzioni: `--backup` interroga l'ultimo backup automatico (più veloce, impatto
nullo), `--keep` conserva la copia per più query, `--shell` apre una shell interattiva.
Chiama `sqlite3` per percorso assoluto `/usr/bin/sqlite3`, per non rimbalzare nel guard.

**Il guard**: risolve ogni argomento non-opzione con `readlink -f` e lo confronta col
percorso protetto (`.db`, `-wal`, `-shm`), così intercetta anche i percorsi relativi da
dentro la cartella del backend. Blocca **solo** se il servizio risulta `active`: a servizio
fermo la manutenzione resta possibile, com'è giusto.

Due scelte deliberate, entrambe nel senso della prudenza:

- **Fail-open**: qualunque imprevisto nel controllo lascia passare il comando. Un guard che
  blocca lavoro legittimo per un proprio difetto sarebbe peggio del problema che risolve;
  l'allarme del `db_watchdog` resta come rete.
- **Non è una barriera di sicurezza**: `/usr/bin/sqlite3` la aggira, di proposito. Ferma
  l'incidente, non l'operatore che sa quello che fa e ha deciso di farlo.

`secure_path` in `/etc/sudoers` elenca `/usr/local/bin` prima di `/usr/bin`, quindi anche
`sudo sqlite3` passa dal guard — verificato sulla macchina, non assunto.

## COSA È STATO VERIFICATO

| prova | atteso | esito |
|---|---|---|
| `sudo sqlite3 …/local.db "SELECT …"` (il comando del disastro) | rifiutato, exit 1 | ✅ |
| Percorso **relativo** da dentro `backend/` | rifiutato | ✅ |
| `local.db-wal` e `local.db-shm` | protetti anch'essi | ✅ |
| Un altro database qualsiasi | passa, stdout corretto, **stderr vuoto** | ✅ |
| File protetto **a servizio fermo** | passa (manutenzione legittima) | ✅ |
| `csv2-db "SELECT count(*) FROM perp_trades;"` | 390 | ✅ |
| `csv2-db --backup` | 155.357 decisioni, dall'ultimo backup | ✅ |
| **`backup_sqlite.sh` dopo l'installazione** | invariato | ✅ `status ok, integrity ok` |
| Backend | attivo, health 200, **0 errori dal riavvio** | ✅ |

La verifica su `backup_sqlite.sh` era la più importante: è l'unico consumatore legittimo di
`sqlite3` in produzione. Non è toccato perché lavora sulla **copia in staging**
(`$stage_dir/local.db`), mai su `$DB_PATH` — controllato nel sorgente prima di installare.

⚠️ Una prova è stata riletta: il caso "database non protetto" sembrava fallito, ma il
riquadro di rifiuto era il messaggio del test precedente arrivato in ritardo su `stderr`.
Rifatto isolando i flussi: stdout corretto, `stderr` vuoto, exit 0.

## SCOSTAMENTI DAL PIANO

Nessuno. Entrambi gli strumenti erano stati proposti a David, che ha scelto di applicarli
insieme.

## QUESTIONI APERTE

1. **Il guard non è distribuito automaticamente**: se la macchina viene ricreata, va
   reinstallato. Andrebbe aggiunto a `install_vps.sh`.
2. **`csv2-db` copia 68 MB** a ogni invocazione senza `--backup`: ~1 secondo e spazio
   temporaneo in `/tmp`. Accettabile, ma per query ripetute conviene `--keep`.
3. Restano da rimuovere i file `~/backups/CORRUZIONE4_*` (circa 143 MB) quando l'analisi
   dell'incidente è considerata chiusa.

## STATO DELIVERABLE

- `deploy/scripts/db_query.sh` — nuovo, installato come `/usr/local/bin/csv2-db`.
- `deploy/scripts/sqlite3_guard.sh` — nuovo, installato come `/usr/local/bin/sqlite3`.
- Entrambi provati in produzione con il servizio attivo.
- Incidente documentato in `NOTE/80_quarta_corruzione_db_causa_provata.md`.
