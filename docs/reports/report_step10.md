# Report Step 10 - Deploy VPS

## 1. COSA È STATO FATTO

- Preparati artefatti versionati per deploy VPS Linux 24/7:
  - unit systemd backend con restart automatico;
  - timer systemd per backup periodico;
  - timer systemd per healthcheck liveness;
  - template nginx per dashboard statica e proxy backend;
  - script installazione VPS;
  - script backup SQLite/config non segrete/TWAK encrypted state;
  - script healthcheck.
- Aggiunto `docs/RUNBOOK_DEPLOY_VPS.md` con runbook operativo:
  - prerequisiti;
  - percorsi standard;
  - installazione;
  - gestione segreti fuori repo;
  - nginx/TLS;
  - TWAK headless;
  - comandi operativi;
  - checklist pre-live;
  - ripristino rapido.
- Aggiornato `docs/PROJECT_STRUCTURE.md` con cartella `deploy/`, runbook, report e stato Step 10.

## 2. COME È STATO FATTO

- Il backend viene esposto solo localmente su `127.0.0.1:8000` tramite Uvicorn.
- Nginx serve `dist-dashboard` come dashboard statica e inoltra `/api/` al backend locale.
- I segreti sono deliberatamente esclusi dal repository: il template usa `/etc/cryptosentinel/backend.env`.
- La configurazione non segreta di installazione resta in `configs/instance.yaml`, locale e gitignored.
- Lo stato TWAK headless viene trattato come persistente e cifrato nella home del service user.
- Il backup esporta:
  - SQLite se presente;
  - YAML versionati non segreti;
  - stato TWAK cifrato se presente.
- Il backup non esporta `.env`, `configs/instance.yaml`, service account o materiale wallet in chiaro.

## 3. COSA È STATO VERIFICATO

- Verificato che il repository fosse pulito prima dello Step 10.
- Letti i documenti obbligatori prima dello step:
  - `plans/Plan_forHackathon.md`
  - `docs/Strategia_Spot.md`
  - `docs/Strategia_Perpetual.md`
  - `docs/PROJECT_STRUCTURE.md`
  - `docs/CURRENT_STRUCTURE.md`
- Ispezionati gli script esistenti di avvio backend e la config dashboard per rispettare porta e convenzioni esistenti.
- Verificata coerenza dei path:
  - repository: `/opt/cryptosentinel/app`;
  - env sensibile: `/etc/cryptosentinel/backend.env`;
  - backup: `/var/backups/cryptosentinel`;
  - TWAK headless: home del service user;
  - dashboard build: `dist-dashboard`.
- Tentata verifica `bash -n` sugli script di deploy, ma il `bash.exe` disponibile nella sessione Windows non esegue comandi; la sintassi va ricontrollata su VPS/Linux.

## 4. SCOSTAMENTI DAL PIANO

- Il deploy reale non e' stato eseguito perche' mancano accesso al VPS, DNS/TLS e segreti runtime.
- Non sono stati avviati servizi locali o remoti.
- Non e' stata letta alcuna configurazione reale contenente segreti.
- Non e' stata eseguita una validazione systemd/nginx reale: richiede Linux con systemd/nginx installati.
- La dashboard viene proposta in produzione come build statica dietro nginx, invece di tenere Vite preview come processo systemd: e' piu' adatto a un VPS 24/7 e riduce superficie operativa.

## 5. QUESTIONI APERTE

- Configurare dominio reale e TLS sul VPS.
- Compilare e installare sul server reale.
- Popolare `/etc/cryptosentinel/backend.env` con segreti runtime senza stamparli.
- Validare TWAK headless come service user con `--no-keychain`.
- Verificare FCM con service account esterno al repo.
- Eseguire test runtime su VPS:
  - `systemctl status cryptosentinel-backend.service`;
  - `/health/live`;
  - dashboard HTTPS;
  - endpoint read/admin;
  - backup timer;
  - liveness timer;
  - cronologia log non sensibile.

## 6. STATO DELIVERABLE

Parziale.

Gli artefatti di deploy e il runbook sono pronti e versionati. Il deliverable completo "sistema in produzione operativo 24/7" richiede esecuzione sul VPS reale, configurazione DNS/TLS, segreti fuori repo e verifica runtime end-to-end.
