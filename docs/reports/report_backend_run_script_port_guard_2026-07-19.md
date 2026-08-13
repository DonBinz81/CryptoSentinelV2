# Guard Porta Backend In Run Script

## 1. COSA È STATO FATTO

- Diagnosticato l'errore Windows `Errno 10048` su `0.0.0.0:8001`.
- Confermato che la porta era occupata da un backend già avviato, non da processi dashboard o altri servizi.
- Modificato `backend/scripts/run_backend.ps1` per fermare automaticamente un listener esistente sulla porta configurata prima di avviare Uvicorn.

## 2. COME È STATO FATTO

- Aggiunta funzione `Stop-ExistingBackendOnPort` in `run_backend.ps1`.
- La funzione legge la porta da `Settings`, cerca processi in `LISTENING` su quella porta, li termina e attende fino a 5 secondi che la porta si liberi.
- Se la porta resta occupata, lo script fallisce con errore esplicito invece di arrivare al bind Uvicorn.

## 3. COSA È STATO VERIFICATO

- Sintassi PowerShell di `run_backend.ps1` e `stop_backend.ps1` verificata con parser PowerShell.
- Test operativo: eseguito `run_backend.ps1` mentre `8001` era già occupata.
- Risultato: il vecchio backend è stato chiuso, il nuovo backend è partito senza `Errno 10048`.
- Verificato `/health/live`: risposta `200`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Il primo warm-up market-data dopo restart può ancora impiegare diversi secondi; non è un errore di porta ma carico di startup/cache.

## 6. STATO DELIVERABLE

- Implementato e verificato localmente.
