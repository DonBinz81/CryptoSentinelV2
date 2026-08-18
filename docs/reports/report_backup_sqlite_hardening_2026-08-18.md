# Report - Backup SQLite: niente fallimenti silenziosi, e la configurazione runtime finisce nel backup

Data: 2026-08-18

---

## COSA È STATO FATTO

Corretto `deploy/scripts/backup_sqlite.sh`, che il 18/08 alle 10:44 UTC è
fallito lasciando a terra una cartella datata con dentro un `local.db` da **0
byte** — indistinguibile da un backup riuscito a un `ls` — senza alcun segnale
di errore. Il fallimento è emerso solo durante la ricognizione manuale che ha
poi scoperto la corruzione del database (`NOTE/54`).

Tre difetti chiusi:

1. **Lo script apriva il database di produzione** (`sqlite3 .backup`). È il gesto
   che ha corrotto il DB quella stessa mattina quando lo ha fatto un'altra
   sessione, ed è la ragione tecnica del fallimento: senza il file `-shm`, e con
   `ReadOnlyPaths` sulla cartella dell'app, SQLite non poteva aprire il file.
2. **L'artefatto veniva creato prima del backup**, quindi un fallimento lasciava
   una directory che sembrava un backup valido.
3. **Nessuna verifica** del backup prodotto: la copia applicativa delle 10:50 era
   già corrotta e nessuno lo ha saputo.

Aggiunto inoltre l'**export della configurazione runtime** a ogni backup. La
configurazione effettiva vive solo dentro `runtime_state` nel database, non negli
YAML: non è versionata, non è consultabile senza token, e nessun backup la
conservava in forma leggibile. Questa lacuna ha già prodotto un errore reale —
un'analisi condotta per due giorni sul valore sbagliato di `perp_sl_mode`, letto
dallo YAML (`atr`) invece che dal runtime (`lowest`).

## COME È STATO FATTO

| aspetto | prima | dopo |
|---|---|---|
| Accesso al DB | `sqlite3 .backup` apre il database di produzione | `cp` dei file; ogni comando `sqlite3` gira sulla **copia** |
| Artefatto | creato prima, resta anche se il backup fallisce | costruito in `.staging_<ts>`, pubblicato solo a successo |
| Verifica | assente | `PRAGMA integrity_check` sulla copia, con una riprova |
| Esito | invisibile | `last_result.json`: `ok` \| `integrity_failed` \| `failed` |
| Configurazione runtime | non salvata | `agent_settings.json` + `runtime_state.tsv` |

Scelte di progetto, con il loro compromesso:

- **Copia invece di apertura.** Il database di produzione non viene mai aperto da
  questo script: `cp` legge un file, non apre un database. Il prezzo è che una
  copia a caldo può risultare incoerente se un checkpoint gira nel frattempo, per
  questo c'è **una riprova dopo 5 secondi** prima di dichiarare il backup
  inutilizzabile.
- **Un backup illeggibile viene pubblicato lo stesso**, marcato con un file
  `INTEGRITY_FAILED`, e lo script esce con codice diverso da zero. Se il database
  di produzione è corrotto, quella copia può essere l'unico materiale rimasto:
  scartarla sarebbe il danno peggiore.
- **L'unit systemd non è stata toccata.** Passando alla copia, lo script non ha
  più bisogno di scrivere nella cartella dell'applicazione: `ProtectSystem=strict`
  e `ReadOnlyPaths` restano invariati, nessun permesso allargato.

L'export della configurazione è possibile **solo** perché lo script ora lavora su
una copia: leggere le impostazioni dal database vivo sarebbe stato di nuovo il
gesto sbagliato.

Verificato che l'export non contenga dati sensibili: 99 chiavi di configurazione
dell'agente, nessun token, nessuna chiave API. I file restano a 0600.

## COSA È STATO VERIFICATO

Tre prove eseguite sulla VPS **su dati di test**, prima di qualunque deploy:

| prova | atteso | esito |
|---|---|---|
| Database sano | exit 0, artefatto completo e verificato | ✅ `status: ok`, `integrity: ok`, `local.db` 11,5 MB consolidato, `agent_settings.json` 3.816 byte, `runtime_state.tsv` 5.651 byte, `configs/` |
| Database corrotto (usato il file reale dell'incidente) | exit 1, artefatto **conservato** e marcato | ✅ `status: integrity_failed`, file `INTEGRITY_FAILED` presente, artefatto preservato |
| Errore reale (database illeggibile) | exit ≠ 0, **nessun** artefatto lasciato a terra | ✅ `status: failed`, solo `last_result.json`, nessuna staging residua |
| Database inesistente | exit ≠ 0, nessun artefatto | ✅ `status: db_missing` |

La prima esecuzione della prova con database corrotto ha rivelato un **difetto
nella prima stesura**: sotto `set -o pipefail` il codice di uscita di `sqlite3`
(26, `SQLITE_NOTADB`) interrompeva lo script prima che l'artefatto potesse essere
conservato e marcato. Corretto isolando quella pipeline; prove ripetute tutte
verdi.

Controllo sintattico `bash -n` superato sia in locale sia sulla VPS.

## SCOSTAMENTI DAL PIANO

Nessuno sul contenuto. Rispetto al piano iniziale è **caduta la modifica
all'unit systemd**: era prevista per dare accesso in scrittura alla cartella del
database, e non serve più — la copia risolve il problema senza allargare i
permessi. È un miglioramento rispetto a quanto proposto.

## QUESTIONI APERTE

1. **La notifica manca ancora.** Il fallimento è ora *visibile* (codice di uscita
   e `last_result.json`) ma non arriva sul telefono. Serve che il backend legga
   quel file e mandi l'allarme FCM: è il passo immediatamente successivo, e
   chiude anche il punto «allarme sulla corruzione del database» aperto in
   `NOTE/54`.
2. **Residui in produzione** da valutare: `local.db.backup.1786878638` e sidecar
   (dall'incidente del 16/08) e `local.db.CORRUPTED_20260818_1200` (conservato per
   l'analisi del 18/08).
3. La retention resta a 14 giorni. Con l'export della configurazione ora incluso,
   varrà la pena valutare se conservare più a lungo almeno i file di
   configurazione, che sono piccoli e raccontano la storia delle modifiche.

## STATO DELIVERABLE

- `deploy/scripts/backup_sqlite.sh` — **completo, provato, deployato e verificato
  in produzione**.
- `deploy/systemd/cryptosentinelv2-backup.service` — invariato, deliberatamente.
- Documentazione: questo report, `docs/PROJECT_STRUCTURE.md` aggiornato,
  `NOTE/54_terza_corruzione_db_e_procedura.md` per il contesto dell'incidente.
