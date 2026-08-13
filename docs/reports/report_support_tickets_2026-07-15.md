# Ticket supporto in-app - 2026-07-15

## 1. COSA È STATO FATTO

- Aggiunto un sistema ticket in-app per utenti e amministratori.
- Aggiunto il profilo device con display name utente, separato dal device token FCM.
- Permesso all'utente di creare ticket, vedere tutti i propri ticket, leggere risposte e stato finale.
- Permesso all'admin di vedere i ticket da dashboard e app, rispondere, segnare risolto e chiudere.
- Aggiunta archiviazione admin: long-press/context menu in app, rimozione dalle liste app e archivio consultabile solo da dashboard.
- Corretto il filtro utente: i ticket restano visibili per `user_id` anche se cambia il `device_id`; il device id rimane solo associazione device/notifiche.
- Reso persistente l'admin token mobile: Agent e Settings condividono lo stesso valore salvato localmente.
- Aggiunto client frontend dedicato e test backend di integrazione.

## 2. COME È STATO FATTO

- Introdotti modelli SQLite `DeviceProfile`, `SupportTicket` e `SupportMessage`.
- Introdotti repository dedicati per profilo device e ticket.
- Aggiunto router FastAPI `/api/v1/support` con endpoint read per utente e admin-only per gestione amministrativa.
- Estesa la registrazione FCM per salvare `display_name` e `build_number` senza usare il token device come identita' applicativa.
- Aggiornata la tab impostazioni dell'app con nome utente, form ticket, lista ticket, thread messaggi e modalita' admin.
- Aggiornata la dashboard con tab Support, vista Active/Archive e azioni admin.
- Esteso lo stato ticket con `archived`, escluso dalle liste utente/admin app e richiedibile esplicitamente dalla dashboard.
- Rimosso il `device_id` come filtro di proprieta' dei ticket utente, mantenendolo come metadato/sender id.
- `SettingsTab` non mantiene piu' un admin token solo in memoria, ma riceve quello persistito dalla root app.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_support_api.py -q`
- Esito aggiornato: `1 passed in 5.22s`.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_device_alert_separation.py backend/tests/integration/test_market_data_api.py backend/tests/integration/test_support_api.py -q`
- Esito: `7 passed in 17.07s`.
- `npm run build`
- Esito aggiornato: build completata; resta il warning Vite noto sul chunk oltre 500 kB.
- `npm run dashboard:build`
- Esito aggiornato: build completata.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno scostamento funzionale rispetto alle regole concordate.
- Non sono state introdotte notifiche push automatiche per nuove risposte ticket; il thread e lo stato sono consultabili da app/dashboard.

## 5. QUESTIONI APERTE

- Verificare su APK/dispositivo reale il flusso completo di apertura ticket e risposta admin con backend operativo.
- Valutare in uno step futuro notifiche push o badge quando l'admin risponde o chiude un ticket.

## 6. STATO DELIVERABLE

- Deliverable completato e verificato localmente con test backend mirati e build frontend/dashboard.
