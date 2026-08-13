# Report - Fix Back dettaglio trade mobile

## 1. COSA È STATO FATTO

- Corretto il comportamento del pulsante Back nel dettaglio trade della tab mobile Agente.
- Impedito ai refresh automatici del dettaglio di riaprire la schermata dopo l'uscita.

## 2. COME È STATO FATTO

- Aggiunto un loader del dettaglio che aggiorna `tradeDetail` solo se il `trade_id` richiesto e' ancora quello attivo.
- Centralizzato il Back in `closeTradeDetail`, che azzera id attivo, stato di loading e dettaglio.
- Applicato lo stesso guard al refresh principale, al refresh veloce ogni 5 secondi e al caricamento manuale del dettaglio.

## 3. COSA È STATO VERIFICATO

- `npm exec tsc -- -b --pretty false`
- `git diff --check`

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Resta utile una verifica manuale su dispositivo/emulatore con refresh attivo mentre si entra/esce dai dettagli.

## 6. STATO DELIVERABLE

- Implementato e verificato con controlli mirati.
