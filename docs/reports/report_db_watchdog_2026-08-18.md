# Report - Watchdog del database: dal rilevamento in sei ore a quello in un minuto

Data: 2026-08-18

---

## COSA È STATO FATTO

Aggiunto `cryptosentinelv2-db-watchdog`, un controllo che gira **ogni minuto** e
segnala i guasti del database mentre stanno accadendo.

Prima di questo, il primo presidio ad accorgersi di una corruzione era il backup
periodico: fino a **sei ore** di ritardo. Il 18/08 il database è rimasto corrotto
per tre ore senza che nessuno lo sapesse (`NOTE/54`).

Il watchdog cerca le due firme che quell'incidente ha prodotto, nell'ordine in
cui sono comparse:

1. **Descrittori orfani**: il backend che tiene un `-wal`/`-shm` cancellato, più
   di un `-wal` in uso, oppure un `-wal` presente senza `-shm`. Questa condizione
   è comparsa alle **09:27:11**, venti secondi *prima* del primo errore
   applicativo. È il segnale più precoce disponibile.
2. **Errori di corruzione nel journal**: `malformed`, `file is not a database`,
   `transaction has been rolled back`. Comparsi alle **09:27:38**.

Il database non viene mai aperto, e nemmeno letto: il watchdog guarda solo
`/proc/<pid>/fd`, la presenza dei file e il journal del servizio.

## COME È STATO FATTO

- `deploy/scripts/db_watchdog.sh` più unit e timer `oneshot` a 60 secondi
  (`OnUnitActiveSec=1min`, `AccuracySec=15s`, `Nice=15`).
- Gira come `cryptosentinelv2`, lo **stesso utente del backend**: è ciò che gli
  consente di leggere `/proc/<pid>/fd` del backend senza privilegi elevati.
  `SupplementaryGroups=systemd-journal` serve per leggere il journal, ed è
  l'unico privilegio aggiuntivo.
- **Throttle a 30 minuti** sulla notifica: il rilevamento continua a finire nel
  journal a ogni giro, ma un incidente in corso non genera una push al minuto. Se
  la consegna fallisce il timestamp **non** viene aggiornato, così il tentativo si
  ripete al giro successivo.
- **Servizio fermo = nessun allarme**: a backend spento l'assenza dei sidecar è
  normale e l'API sarebbe irraggiungibile.

## COSA È STATO VERIFICATO

| prova | atteso | esito |
|---|---|---|
| Stato sano, finestra corrente | nessun rilevamento | ✅ nessun output, exit 0 |
| **Log reali dell'incidente** (dalle 09:27) | rilevamento | ✅ «370 errori di database nei log» |
| Servizio non attivo | uscita silenziosa | ✅ exit 0 |
| Consegna end-to-end | notifica ricevuta | ✅ `POST /notifications/send` → 200, notifica arrivata sul dispositivo, timestamp di throttle salvato |
| Deploy | hash identici | ✅ script, unit e timer |

La prima esecuzione dei test è stata **fuorviante e va segnalata**: eseguendo lo
script con `sudo -u cryptosentinelv2` il journal risultava vuoto (4 righe invece
di 26.626) e il rilevamento non scattava. La causa non era lo script ma il
metodo di prova: l'utente non appartiene a `systemd-journal`, gruppo che nella
unit reale viene concesso da `SupplementaryGroups`. Ripetuta la prova con
`systemd-run` nelle stesse condizioni dell'unit, il rilevamento è corretto.
**Una prova che non riproduce l'ambiente reale può assolvere o condannare per il
motivo sbagliato.**

## SCOSTAMENTI DAL PIANO

Nessuno. Il canale di consegna è FCM, come deciso, con il limite qui sotto
accettato consapevolmente.

## QUESTIONI APERTE

1. **Il limite del canale, dichiarato**: l'allarme viaggia su FCM, che ha bisogno
   della tabella `device_tokens`. Durante l'incidente del 18/08 era proprio quella
   la tabella corrotta, quindi in quello scenario l'allarme sarebbe stato
   rilevato ma **non consegnato**. Chiuderlo richiede un canale indipendente dal
   database (Telegram o SMTP): valutato e rimandato.
2. **Canale Android silenzioso**: le notifiche arrivano sul canale `price_alerts`,
   che sul dispositivo risulta declassato a silenzioso. Il backend invia già
   `priority=high` e `notification.priority=max`, quindi la correzione sta
   nell'app — un canale dedicato agli allarmi di sistema. Perimetro app.
3. **Timer che smette di partire**: resta scoperto, come per il backup.

## STATO DELIVERABLE

- `deploy/scripts/db_watchdog.sh` — completo, deployato, provato sui log reali
  dell'incidente.
- `deploy/systemd/cryptosentinelv2-db-watchdog.service` / `.timer` — installati,
  timer **abilitato e attivo**, esecuzione ogni minuto.
