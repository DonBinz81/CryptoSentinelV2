# Report Dashboard Tailscale Host - 2026-08-04

## 1. COSA E STATO FATTO

La dashboard Vite e stata configurata per ascoltare su tutte le interfacce di rete invece che solo su `127.0.0.1`.

Gli script Windows di avvio e riavvio mostrano sia l'URL locale sia l'URL Tailscale quando viene rilevato un indirizzo `100.x.y.z`.

Il backend accetta anche l'origin CORS della dashboard servita via Tailscale sulla porta dashboard configurata.

Il client dashboard normalizza il backend URL: se l'utente inserisce l'URL della dashboard su `:5176`, le chiamate API vengono indirizzate al backend su `:8001`.

## 2. COME E STATO FATTO

Gli script npm `dashboard:dev` e `dashboard:preview` usano `--host 0.0.0.0`. La configurazione `dashboard/vite.config.ts` imposta `server.host` e `preview.host` a `0.0.0.0`.

Gli script PowerShell leggono l'IPv4 dell'interfaccia Tailscale e stampano l'indirizzo da usare dagli altri dispositivi.

Il middleware CORS FastAPI usa un regex ristretto a `localhost`, `127.0.0.1` e IP Tailscale `100.x.y.z` sulla porta `dashboard_port`, evitando wildcard globali.

Il client API centralizzato converte la porta dashboard `5176` nella porta backend `8001` e il form dashboard salva il valore normalizzato dopo il blur.

## 3. COSA E STATO VERIFICATO

E stato verificato che il processo dashboard precedente era in ascolto solo su `127.0.0.1:5176` e che l'IP Tailscale locale rilevato era `100.66.71.112`.

E stato verificato che il backend era raggiungibile via Tailscale ma rifiutava il preflight CORS con `Disallowed CORS origin`, causa del `Failed to fetch` nel browser remoto.

E stato verificato con TypeScript che la normalizzazione del backend URL compila nella dashboard.

## 4. SCOSTAMENTI DAL PIANO

Nessuno.

## 5. QUESTIONI APERTE

Per chiamare il backend da altri dispositivi, la dashboard deve usare come backend URL l'indirizzo Tailscale della macchina backend.

Se nel form viene inserito per errore `http://100.66.71.112:5176/`, il client lo corregge in `http://100.66.71.112:8001`.

## 6. STATO DELIVERABLE

Implementato a livello configurazione/script/backend CORS/client dashboard. Serve aggiornare o ricaricare la dashboard per applicare il client aggiornato nel browser.
