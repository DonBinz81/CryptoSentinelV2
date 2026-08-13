# Fix Freeze Backend Durante Sync Alert

## 1. COSA È STATO FATTO

- Diagnosticato il blocco degli endpoint usati da app/dashboard durante il refresh dei grafici trade.
- Identificato `/api/v1/alerts/sync` come percorso capace di bloccare l'event loop FastAPI mentre SQLite resta in busy timeout.
- Spostata la persistenza sincrona degli alert su worker thread.
- Allineato il busy timeout SQLite del motore sincrono a 5 secondi, come il motore async principale.

## 2. COME È STATO FATTO

- In `backend/app/api/routes/alerts.py`, `sync_alerts` ora usa `anyio.to_thread.run_sync` per eseguire `AlertStore.save_config` fuori dall'event loop.
- Aggiunto helper `_save_alert_config` per mantenere esplicito il lavoro delegato al thread.
- In `backend/app/persistence/sync_database.py`, `connect_args["timeout"]` e `PRAGMA busy_timeout` sono stati ridotti da 30s a 5s.
- Aggiunto test unitario per verificare che la route alert deleghi la persistenza al worker thread.

## 3. COSA È STATO VERIFICATO

- Dai log runtime prima della correzione: richieste app/dashboard completate dopo oltre 210 secondi e `/api/v1/alerts/sync` fallita dopo circa 100 secondi con `sqlite3.OperationalError: database is locked`.
- Eseguiti test mirati: `backend/tests/unit/test_device_alert_separation.py` e `backend/tests/unit/test_alert_store.py`.
- Eseguita verifica compileall sui file backend modificati.
- Riavviato il backend con `backend/scripts/run_backend.ps1`.
- Verificato `/health/live` con risposta HTTP 200.
- Dopo restart, osservati endpoint principali in completamento entro pochi secondi invece che dopo centinaia di secondi.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Se l'app continua a mostrare endpoint non raggiungibili, serve correlare un nuovo refresh con i nuovi `request_id` nei log, per distinguere eventuali timeout provider esterni da blocchi SQLite.
- Il primo warm-up dopo restart resta piu' lento per le chiamate Binance/CoinGecko iniziali.

## 6. STATO DELIVERABLE

- Implementato e verificato localmente.
