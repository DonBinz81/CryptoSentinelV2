# Runbook Deploy VPS - Step 10

Questo runbook prepara CryptoSentinel per un VPS Linux 24/7. Non contiene segreti e non richiede di salvare credenziali nel repository.

## 1. Obiettivo

- Backend FastAPI in ascolto solo su `127.0.0.1:8000`.
- Dashboard Vite compilata come sito statico in `dist-dashboard`.
- Nginx pubblico su HTTP/HTTPS con proxy `/api/` verso il backend.
- Systemd con restart automatico.
- Timer systemd per backup e healthcheck.
- NTP attivo tramite `chrony`.
- Stato TWAK headless persistente in home del service user.

## 2. Percorsi previsti

| Percorso | Uso |
|---|---|
| `/opt/cryptosentinel/app` | repository sul VPS |
| `/etc/cryptosentinel/backend.env` | variabili sensibili fuori repo, permessi `0600` |
| `/var/backups/cryptosentinel` | backup SQLite/config non segreti/TWAK encrypted state |
| `/home/cryptosentinel/.twak` | stato TWAK headless persistente |
| `/etc/systemd/system/cryptosentinel-*.service` | unit systemd |
| `/etc/nginx/sites-available/cryptosentinel.conf` | reverse proxy/dashboard |

## 3. Prerequisiti VPS

- Ubuntu/Debian recente.
- Utente root o sudo.
- DNS del dominio puntato al VPS.
- Repository presente in `/opt/cryptosentinel/app`.
- Segreti disponibili solo sul VPS, mai nel repo.
- File Firebase service account salvato fuori repo, se FCM e' attivo.
- TWAK inizializzato in modalita' headless con `--no-keychain`, se si usa TWAK live.

## 4. Installazione base

Da root, dopo aver posizionato il repository:

```bash
cd /opt/cryptosentinel/app
bash deploy/scripts/install_vps.sh
```

Lo script:

- installa dipendenze OS minime;
- crea l'utente di servizio `cryptosentinel`;
- crea directory persistenti e protette;
- prepara `backend/.venv`;
- installa dipendenze Python;
- esegue `npm ci` e `npm run dashboard:build`;
- installa unit systemd, timer e config nginx;
- abilita backend, backup, healthcheck, nginx e chrony.

## 5. Configurazione segreti

Compilare solo sul VPS:

```bash
nano /etc/cryptosentinel/backend.env
chmod 600 /etc/cryptosentinel/backend.env
```

Variabili attese principali:

| Variabile | Uso |
|---|---|
| `API_READ_TOKEN` | read-only dashboard/mobile |
| `API_ADMIN_TOKEN` | operazioni admin |
| `API_DEVICE_TOKEN` | registrazione device |
| `API_ALERTS_TOKEN` | sync alert |
| `CMC_API_KEY` | dati CoinMarketCap |
| `ANTHROPIC_API_KEY` | Claude meta-controller |
| `TWAK_ACCESS_ID` / `TWAK_HMAC_SECRET` | Trust Wallet Agent Kit |
| `TWAK_WALLET_PASSWORD` | wallet TWAK headless |
| `WALLET_ENCRYPTED_PRIVATE_KEY_PATH` | path keystore cifrato |
| `WALLET_KEY_PASSPHRASE_ENV` | nome env che contiene passphrase |
| `FCM_CREDENTIALS_PATH` | path service account Firebase |
| `TATUM_RPC_API_KEY` | RPC Tatum opzionale |

Non stampare questi valori nei log o nei report.

## 6. Configurazione non segreta

`configs/instance.yaml` resta locale al VPS e gitignored. Lo script lo crea dal template se manca.

Impostazioni da verificare prima di live:

- `app.env: production`
- `api.host: 127.0.0.1`
- `api.port: 8000`
- `api.base_url` con URL pubblico HTTPS
- `frontend.backend_api_base_url` con URL pubblico HTTPS
- `bsc.network`, `chain_id`, RPC ed explorer
- `competition.contract_address`
- provider `market_data`, `execution`, `perp_execution`
- backup DB abilitato

Non mettere segreti in `configs/instance.yaml`.

## 7. Nginx e TLS

Aggiornare `deploy/nginx/cryptosentinel.conf` o il file installato in `/etc/nginx/sites-available/cryptosentinel.conf`:

- sostituire `cryptosentinel.example.com` con il dominio reale;
- verificare `root /opt/cryptosentinel/app/dist-dashboard`;
- mantenere `/api/` verso `http://127.0.0.1:8000/api/`;
- mantenere `/health/live` pubblico per liveness.

Verifica:

```bash
nginx -t
systemctl reload nginx
```

Per TLS usare Certbot o il provider scelto sul VPS. Dopo TLS, forzare redirect HTTP->HTTPS e verificare che `X-Forwarded-Proto` resti impostato.

## 8. TWAK headless

Sul VPS non usare keychain OS. Pattern operativo:

- usare `TWAK_WALLET_PASSWORD` in `/etc/cryptosentinel/backend.env`;
- creare/importare wallet con `twak` in modalita' `--no-keychain`;
- mantenere la directory persistente del service user;
- includere lo stato cifrato nei backup;
- non copiare mai wallet cifrati nel repository.

Il service user e' `cryptosentinel`; inizializzare TWAK nello stesso contesto utente quando possibile.

## 9. Comandi operativi

```bash
systemctl status cryptosentinel-backend.service
systemctl status cryptosentinel-backup.timer
systemctl status cryptosentinel-healthcheck.timer
journalctl -u cryptosentinel-backend.service -n 100 --no-pager
curl -fsS http://127.0.0.1:8000/health/live
```

Restart:

```bash
systemctl restart cryptosentinel-backend.service
systemctl reload nginx
```

Backup manuale:

```bash
systemctl start cryptosentinel-backup.service
```

## 10. Verifiche prima del live

- `systemctl is-active cryptosentinel-backend.service` restituisce `active`.
- `/health/live` risponde `200`.
- Dashboard pubblica si apre via HTTPS.
- Dashboard chiama `/api/` senza CORS error.
- Read token funziona per viste read-only.
- Admin token funziona per settings/kill switch.
- Read token non soddisfa endpoint admin.
- DB readiness autenticata risulta connessa.
- Backup timer produce una cartella in `/var/backups/cryptosentinel`.
- `chrony` e' attivo e sincronizzato.
- TWAK wallet headless e' disponibile al service user.
- Nessun segreto e' stato copiato nel repo.

## 11. Ripristino rapido

1. Fermare backend:

```bash
systemctl stop cryptosentinel-backend.service
```

2. Copiare il backup SQLite selezionato in `backend/local.db` mantenendo owner `cryptosentinel`.

3. Ripristinare eventuale stato TWAK cifrato nella home del service user.

4. Riavviare:

```bash
systemctl start cryptosentinel-backend.service
curl -fsS http://127.0.0.1:8000/health/live
```

## 12. Stato Step 10

Gli artefatti versionati preparano il deploy, ma il deliverable "sistema in produzione operativo 24/7" richiede:

- accesso al VPS;
- DNS/TLS reale;
- compilazione e installazione sul server;
- configurazione segreti fuori repo;
- verifica con backend e dashboard reali.
