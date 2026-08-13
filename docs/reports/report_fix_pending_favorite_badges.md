# Report Fix Badge Preferiti da FCM

## 1. COSA È STATO FATTO

- Corretto il mancato badge arancione dopo notifiche preferiti ricevute con app in background o chiusa.
- Aggiunta persistenza backend degli alert preferiti pendenti per coin.
- Aggiunto recupero pending all'avvio e a ogni rientro in foreground.
- Aggiunto acknowledgement backend quando l'utente preme “Ho capito”.
- Aggiunti endpoint `GET/DELETE /api/v1/alerts/pending-favorites`.
- Aggiunti test di regressione per persistenza, sync, rimozione preferito e acknowledgement.

## 2. COME È STATO FATTO

- Il listener FCM JavaScript resta il percorso immediato per foreground e tap.
- Dopo una consegna FCM riuscita, il checker salva l'ultimo evento pending nel medesimo stato autorevole backend.
- La sincronizzazione ordinaria degli alert preserva i pending delle coin ancora preferite.
- L'app converte la risposta backend nello stesso `FavAlertData` già usato da card e popup.
- Il badge locale e quello backend vengono rimossi insieme tramite azione esplicita dell'utente.

## 3. COSA È STATO VERIFICATO

- Suite backend: `17 passed, 1 skipped`.
- `ruff check backend/app backend/tests`: passato.
- `npx tsc -b`: passato.
- Verificato che un pending sopravviva a una sincronizzazione identica.
- Verificato che “Ho capito” rimuova il pending.
- Verificato che la rimozione della coin dai preferiti elimini anche il pending.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno Step successivo avviato.
- Il fix aggiunge stato temporaneo JSON coerente con lo Step 2; la migrazione a database resta prevista nello Step 5.

## 5. QUESTIONI APERTE

- Verificare su APK reale i tre casi: app in foreground, app in background aperta manualmente, tap sulla notifica da app chiusa.
- Nello Step 5 migrare i pending badge insieme allo stato alert nel database.

## 6. STATO DELIVERABLE

**Raggiunto nel codice e nei test automatici.**

Resta necessaria la verifica funzionale sul dispositivo dopo una nuova build APK.
