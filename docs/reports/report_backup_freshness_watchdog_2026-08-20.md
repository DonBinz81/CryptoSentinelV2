# Report - Watchdog di freschezza sul backup

Data: 2026-08-20
Branch: `chat-infra/backup-freshness` (da creare al commit)
Perimetro: D — infrastruttura e dati

---

## COSA È STATO FATTO

`NOTE/54` §10 punto 2 lasciava scoperto un caso specifico: l'allarme sul backup (`OnFailure=`
su `cryptosentinelv2-backup.service`) copre un fallimento **attivo** — non prodotto, o
integrità non passata — ma non copre il timer che **smette di partire del tutto**: disabilitato,
rimosso, o un'esecuzione che resta appesa senza mai uscire. In nessuno di questi casi c'è un
evento di fallimento da cui partire, quindi `OnFailure=` non si attiva e non arriva nulla.

Aggiunto `deploy/scripts/backup_freshness_watchdog.sh`, eseguito ogni ora da una coppia
timer/service dedicata, con due segnali indipendenti:

1. `cryptosentinelv2-backup.timer` non risulta `active` — il caso diretto: lo schedulatore
   stesso è sparito.
2. `last_result.json` più vecchio di 13 ore (la cadenza è 6h: la soglia tollera un ciclo
   mancato più margine) — copre un'esecuzione appesa o un file che ha smesso di aggiornarsi
   pur col timer apparentemente sano.

## COME È STATO FATTO

Stesso schema di `db_watchdog.sh` (nota 54/nota 67): script `set -uo pipefail`, throttle su
file di stato (`STATE_DIRECTORY`, qui 6h — non riallarma a ogni giro orario per lo stesso
guasto, ma non oltre la cadenza che un backup fresco avrebbe comunque rispettato), consegna
delegata a `notify_alert.sh` (nota 67: FCM + Telegram, quest'ultimo indipendente da backend
e database).

Il parsing del timestamp (`20260819T175104Z`) usa python3, con lo stesso pattern di
`backup_alert.sh`: se python3 manca, il segnale 2 viene saltato ma il segnale 1 (il timer)
resta comunque attivo — degrado, non buio totale.

Due nuovi unit systemd modellati su `cryptosentinelv2-db-watchdog.{timer,service}`:
`OnBootSec=15min`, `OnUnitActiveSec=1h`, utente `cryptosentinelv2`, `ProtectSystem=strict`,
`ReadOnlyPaths` limitato a `/opt/cryptosentinelv2/app` e `/var/backups/cryptosentinelv2`.

## COSA È STATO VERIFICATO

Tutto in locale, con `systemctl` e `notify_alert.sh` sostituiti da finti controllabili (mai
toccata la VPS in questa fase):

| caso | atteso | esito |
|---|---|---|
| Timer attivo, esito di poche ore | silenzio, exit 0 | ✅ |
| Timer **non** attivo | allarme, titolo/corpo corretti | ✅ |
| Esito vecchio 20h (soglia 13h) | allarme, età riportata in ore | ✅ |
| Esito vecchio 10h (sotto soglia) | silenzio | ✅ |
| `last_result.json` assente | allarme, motivo esplicito | ✅ |
| Throttle: due guasti entro la finestra | un solo invio, il secondo giro logga ma non richiama l'helper | ✅ |
| Consegna fallita (nessun canale configurato) | il file di stato **non** si aggiorna, riprova al giro successivo | ✅ (verificato nella prima stesura del test, prima di correggere il finto helper) |
| `bash -n` sui tre file nuovi | pulito | ✅ |

**Non ancora fatto**: deploy, verifica per hash in produzione, e la prova che serve davvero —
disattivare il timer vero (o attendere un ciclo) e controllare che l'allarme arrivi. Questo
report descrive codice pronto, non ancora applicato.

## SCOSTAMENTI DAL PIANO

Nessuno rispetto a quanto descritto in NOTE/54: la soluzione è quella lì annunciata
("richiede un controllo di freschezza nel backend/nella cadenza"), realizzata come watchdog
indipendente invece che come endpoint del backend — coerente con `db_watchdog.sh`, che è
già questo pattern per un problema affine, e non richiede toccare il backend.

## QUESTIONI APERTE

1. **Soglia 13h**: scelta come 2 cicli (12h) + un'ora di margine. Se si preferisce una
   tolleranza diversa è un solo numero (`MAX_AGE_HOURS`).
2. **Nota 54 classificava questo lavoro "perimetro strategia"**, ma è infrastruttura pura
   (timer, allarmi) — nessuna logica di trading coinvolta. Segnalato a David, che ha confermato
   di procedere da questa chat (D) e di indirizzare il report alla chat B.
3. La prova end-to-end reale (disattivare il timer sulla VPS e verificare l'arrivo
   dell'allarme) non è stata fatta: richiede l'autorizzazione a toccare un timer di
   produzione, anche solo temporaneamente.

## STATO DELIVERABLE

- `deploy/scripts/backup_freshness_watchdog.sh` — nuovo, provato in locale con finti.
- `deploy/systemd/cryptosentinelv2-backup-freshness.timer` — nuovo.
- `deploy/systemd/cryptosentinelv2-backup-freshness.service` — nuovo.
- Non commitato, non deployato: in attesa dell'ok esplicito per il resume (regola fissa).
