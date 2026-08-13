# Report finale Step 2 - Notifiche backend FCM

Data chiusura: 13 giugno 2026

## 1. COSA È STATO FATTO

- Completata la migrazione delle notifiche background dal `PriceCheckWorker` Android al backend FastAPI.
- Implementato un checker backend ogni 60 secondi per alert soglia, range e movimenti percentuali dei preferiti.
- Implementata la sincronizzazione della configurazione alert dall'app tramite `POST /api/v1/alerts/sync`.
- Persistiti temporaneamente configurazione e stato alert in JSON, in attesa del database dello Step 5.
- Registrati i token FCM Android tramite Capacitor e backend.
- Gestite le notifiche FCM con app aperta, in background e chiusa.
- Rimossi `PriceCheckWorker`, `BootReceiver` e il relativo scheduling Android.
- Aggiunta diagnostica di raggiungibilità backend nell'area sviluppatore.
- Corretti i confini di autorizzazione: il token device può solo registrare/rimuovere device; la sincronizzazione usa uno scope alerts dedicato; stato e invio restano read/admin.
- Corretto il riarmo involontario degli alert già notificati durante sincronizzazioni identiche.
- Corretto il mantenimento dei prezzi di riferimento aggiornati dal backend mentre l'app è chiusa.
- Disattivati gli eventi locali prodotti dal polling frontend: niente seconda notifica, beep o popup; l'unica origine è FCM backend.
- Ripristinata l'evidenziazione arancione dei preferiti come stato derivato dal payload FCM; il tap sul push apre la tab Preferiti senza generare un secondo evento.
- Aggiornati piano, README e struttura progetto.

## 2. COME È STATO FATTO

- Il backend riceve dall'app solo gli alert attivi e li salva in `backend/storage/alerts.json`, percorso gitignored.
- `price_checker_loop()` legge i prezzi ogni 60 secondi e usa il servizio notifiche centralizzato per l'invio FCM.
- Il client Android registra il token FCM con credenziale device limitata e sincronizza gli alert con una credenziale alerts separata.
- In foreground, il listener Capacitor converte il push ricevuto in notifica locale visibile.
- Gli hook frontend mantengono configurazione e UI, ma non marcano autonomamente gli alert come scattati e non inviano notifiche locali.
- Lo stato backend conserva alert già scattati, cooldown range e riferimenti dei preferiti tra tick, restart e risincronizzazioni.
- Lo stato FCM resta accessibile solo con token read/admin; l'invio manuale resta admin-only; il token device non soddisfa altri scope.
- Il modello `critical` / `warning` / `info` e il servizio centralizzato preparano il routing browser che verrà completato nello Step 8.

## 3. COSA È STATO VERIFICATO

- Verifica end-to-end su dispositivo reale dichiarata completata dall'utente:
  - ricezione FCM con app aperta;
  - ricezione FCM con app in background;
  - ricezione FCM con app chiusa;
  - sincronizzazione alert e assenza di duplicati nel flusso provato;
  - diagnostica backend/FCM e invio di test durante lo sviluppo.
- Revisione dei commit `af09664`, `e3ba379`, `514884b` e `f393390`.
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit -q`: 4 test superati.
- `backend/.venv/Scripts/python.exe -m compileall -q backend/app backend/tests`: completato senza errori.
- `npx tsc -b`: completato senza errori.
- `npx eslint src/components/SettingsTab.tsx src/utils/alertSync.ts`: completato senza errori.
- Parsing YAML di `.github/workflows/build-apk.yml`: completato senza errori.
- `git diff --check`: nessun errore di whitespace.
- Verificato che nessun file sensibile risulti tracciato; non sono stati aperti `.env`, service account o file sotto directory segrete.

## 4. SCOSTAMENTI DAL PIANO

- Il fallback WorkManager inizialmente mantenuto è stato rimosso: FCM/backend è ora il percorso unico per il background.
- Il checker usa temporaneamente CoinGecko. La sostituzione con CMC resta parte dello Step 3.
- Il pulsante mobile di test FCM è stato rimosso nella revisione finale perché richiedeva al token device di inviare notifiche, in contrasto con il confine di sicurezza del repository. I test manuali restano disponibili tramite endpoint admin.
- La preferenza telefono/browser/entrambi non è persistita nello Step 2 perché il canale browser non esiste ancora. Severity model e servizio centralizzato sono pronti; il routing completo resta nello Step 8.
- La build CI richiede il nuovo secret `VITE_API_ALERTS_TOKEN` per mantenere separato lo scope di sincronizzazione alert.

## 5. QUESTIONI APERTE

- Migrare token FCM, configurazione alert e stato checker da JSON al database nello Step 5.
- Sostituire CoinGecko con il client CMC centralizzato nello Step 3.
- Implementare preferenze di routing e notifiche browser Livello A nello Step 8.
- Configurare il secret GitHub Actions `VITE_API_ALERTS_TOKEN` prima della prossima build APK.
- Configurare esplicitamente `asyncio_default_fixture_loop_scope` per eliminare il warning futuro di `pytest-asyncio`; non blocca lo Step 2.

## 6. STATO DELIVERABLE

**RAGGIUNTO.**

Le notifiche telefono via FCM funzionano server-side 24/7 e sono state verificate dall'utente con app aperta, in background e chiusa. Lo Step 2 è chiuso. Non avviare lo Step 3 senza approvazione esplicita.
