# Report - Allarme push sul fallimento del backup (e sulla corruzione del database)

Data: 2026-08-18

---

## COSA È STATO FATTO

Aggiunto un allarme push che scatta quando un'esecuzione del backup non
completa. Copre due casi:

| stato in `last_result.json` | significato | notifica |
|---|---|---|
| `failed` | il backup non è stato prodotto | «Backup fallito» |
| `integrity_failed` | la copia del database non passa `integrity_check`, quindi il database di produzione è molto probabilmente corrotto | «Database illeggibile» |

Il secondo caso è, in pratica, un **controllo di corruzione ogni 6 ore**: chiude
la questione «nessun allarme sulla corruzione» aperta in `NOTE/54`, senza
toccare il backend.

Contesto: il 18/08 il database è rimasto corrotto per tre ore e l'unica traccia
era un file da 0 byte in una cartella di backup che nessuno stava guardando.
Con questo allarme la stessa condizione sarebbe stata segnalata alle 10:44.

## COME È STATO FATTO

Tre file, tutti dentro `deploy/`:

- `deploy/scripts/backup_alert.sh` — legge `last_result.json`, compone il
  messaggio e chiama `POST /api/v1/notifications/send` in locale con severità
  `critical`. Il payload è costruito con `python3` per gestire correttamente
  l'escape del messaggio di `integrity_check`, che contiene virgolette e
  parentesi; senza `python3` c'è un messaggio fisso di ripiego, perché un allarme
  con meno dettagli è comunque meglio di nessun allarme.
- `deploy/systemd/cryptosentinelv2-backup-alert.service` — unit `oneshot`
  attivata da `OnFailure=`. Deliberatamente **non** dipende dall'unit di backup:
  una dipendenza la escluderebbe proprio quando serve.
- `deploy/systemd/cryptosentinelv2-backup.service` — aggiunta la sola riga
  `OnFailure=cryptosentinelv2-backup-alert.service`.

Sul token di amministrazione: arriva da `EnvironmentFile`, che systemd legge come
root e passa a un servizio che gira **non privilegiato** (`cryptosentinelv2`) —
lo stesso meccanismo già usato dall'unit del backend. Nessun permesso modificato,
nessun segreto copiato altrove, e lo script non stampa mai il token, nemmeno in
caso di errore. I due file di ambiente sono caricati **nello stesso ordine del
backend**: `API_ADMIN_TOKEN` è definito in entrambi e vale il secondo, quindi
caricarne uno solo avrebbe prodotto un 401.

## COSA È STATO VERIFICATO

- `bash -n` sullo script, in locale e sulla VPS.
- Deploy verificato per hash su tutti e tre i file.
- `systemd-analyze verify` sull'unit nuova e su quella modificata.
- **Prova end-to-end**: esecuzione dell'allarme con un `last_result.json` di
  stato `integrity_failed`, con notifica realmente consegnata al dispositivo.
- **Prova della catena `OnFailure`**: fallimento reale del backup simulato con un
  percorso di database illeggibile, per confermare che systemd attivi da solo
  l'unit di allarme senza intervento manuale.

## SCOSTAMENTI DAL PIANO

Nel report precedente era scritto che l'unit del backup sarebbe rimasta
invariata. Con l'allarme non è più vero: acquisisce la riga `OnFailure=`. È
l'unica modifica, e richiede `daemon-reload` ma nessun riavvio del backend.

## QUESTIONI APERTE

1. **Timer che smette di partire**: questo allarme scatta quando il backup
   *fallisce*, non quando non viene *eseguito affatto*. Coprirlo richiede un
   controllo di freschezza (`last_result.json` più vecchio di N ore), che ha
   senso accanto al watchdog del motore nel backend — **perimetro strategia**,
   quindi segnalato e non fatto da qui.
2. La notifica raggiunge i dispositivi registrati. Se i token vengono persi, come
   nell'incidente del 18/08, l'allarme parte ma non arriva: è un limite comune a
   tutte le notifiche del sistema.

## STATO DELIVERABLE

- `deploy/scripts/backup_alert.sh` — completo, deployato, verificato.
- `deploy/systemd/cryptosentinelv2-backup-alert.service` — installata e attiva.
- `deploy/systemd/cryptosentinelv2-backup.service` — aggiornata con `OnFailure=`.
- Documentazione: questo report, `docs/PROJECT_STRUCTURE.md` aggiornato,
  `report_backup_sqlite_hardening_2026-08-18.md` per l'intervento che lo precede.
