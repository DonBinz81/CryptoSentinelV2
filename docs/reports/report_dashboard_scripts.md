# Report dashboard scripts

## 1. COSA È STATO FATTO

- Aggiunto `scripts/start_dashboard.ps1` per avviare la dashboard web sulla porta 5176.
- Aggiunto `scripts/restart_dashboard.ps1` per chiudere eventuali processi già in ascolto sulla porta 5176 e riavviare la dashboard.

## 2. COME È STATO FATTO

- Gli script usano PowerShell e rilevano processi in ascolto tramite `Get-NetTCPConnection`.
- Lo start non avvia una seconda dashboard se la porta è già occupata.
- Il restart ferma il processo esistente sulla porta 5176 prima di eseguire `npm run dashboard:dev`.
- Gli script restano nella finestra PowerShell visibile; se falliscono o il comando termina, attendono input prima di chiudere.

## 3. COSA È STATO VERIFICATO

- Verifica sintattica PowerShell degli script.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Nessuna.

## 6. STATO DELIVERABLE

Script operativi aggiunti. Nessun controllo o tasto è stato inserito nella dashboard.
