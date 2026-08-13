# Report TWAK RPC route probe

## 1. COSA È STATO FATTO

- Aggiunto script diagnostico `backend/scripts/twak_rpc_route_probe.py`.
- Lo script ruota manualmente gli endpoint `Settings.bsc_rpc_urls`, uno alla volta.
- Per ogni RPC esegue preflight `eth_chainId` e `eth_gasPrice`.
- Dopo il preflight chiama TWAK `/amber-api/v1/route` in modalità quote-only autenticata.

## 2. COME È STATO FATTO

- Le credenziali TWAK vengono caricate solo tramite `Settings`; non vengono stampate.
- Gli endpoint RPC vengono loggati solo con indice e hostname, non con URL completi.
- La chiamata non firma e non invia transazioni.

## 3. COSA È STATO VERIFICATO

- Aggiunto script pronto per test manuale con asset/address/amount operativi.

## 4. SCOSTAMENTI DAL PIANO

- Non è stato eseguito uno swap reale; il test è route/quote-only per evitare movimento fondi.

## 5. QUESTIONI APERTE

- Se il 403 persiste su tutti gli endpoint, la causa è lato autenticazione/account TWAK e non RPC locale.
- Se un endpoint funziona, usare il log `twak_rpc_probe_route_ok` per identificare l'indice RPC riuscito.

## 6. STATO DELIVERABLE

Diagnostica pronta. Eseguire con parametri espliciti di wallet e token.
