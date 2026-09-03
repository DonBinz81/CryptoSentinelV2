# App: chiusura manuale (parziale/totale) delle posizioni Perp

Data: 2 settembre 2026 · Branch: `claude/manual-close-ui` · Commit: `918caac`
Perimetro: C (app Android e UI) — lato app del contratto congelato dalla chat A (NOTE/107)

## COSA

Comando `[ Riduci / Chiudi ]` su ogni card di posizione **Perp aperta**, con modale a
25/50/75/100% della size residua. Solo Perp — Spot fuori perimetro per questa missione.

Separato e invariato dal pulsante "Chiudi tutto & metti in pausa" del banner del
guardiano: la chiusura manuale non tocca mai il kill switch e non mette mai in pausa
l'agente.

## COME

`ClosePositionModal`, nuovo componente, gestisce tutti gli esiti del contratto
(`confirmed`, `stale_position`, `already_closed`, `key_reused_with_different_payload`,
`in_progress`, `invalid_request`, `not_found`, `execution_failed`) e le due protezioni
obbligatorie:

- **Idempotency-Key**: nuova per ogni tentativo nuovo (apertura modale, o dopo un esito
  che cambia i presupposti — `stale_position`), identica sul retry dello stesso
  tentativo (errore di rete, `execution_failed`)
- **expected_size**: sempre l'ultimo dato mostrato, aggiornato automaticamente quando il
  backend segnala `stale_position`

`closePerpPosition` in `agentApi.ts` **non** usa `backendRequest()`/`request()`: quel
wrapper lancia un'eccezione su ogni stato non-2xx e scarta il corpo, ma qui l'esito
preciso sta sempre nel body — anche su 409/422/404/502 — quindi va sempre letto, mai
trattato come un errore generico.

La card è passata da un `<button>` intero a un `<div>` con due `<button>` sibling (tocco
per il dettaglio, "Riduci / Chiudi" separato): evita un `<button>` annidato in un
`<button>`, HTML non valido.

## ⚠️ Due bug veri trovati durante la verifica, non solo nel test

1. Sul caso `confirmed` la prima versione chiamava `onClosed()` **subito**: la modale si
   chiudeva prima che l'utente vedesse quantità/prezzo eseguiti e l'avviso
   `forced_full`. La schermata di esito era codice scritto ma mai mostrato.
2. Il pulsante "Chiudi" (dopo un esito definitivo) era agganciato a `onCancel`, non a
   `onClosed`: il padre non si sarebbe **mai** aggiornato dopo una chiusura riuscita se
   l'utente usciva da lì — la card sarebbe rimasta con dati vecchi indefinitamente.

Entrambi trovati eseguendo il flusso vero nel banco di anteprima, non per ispezione del
codice — il secondo in particolare non era visibile solo leggendo, perché il primo bug
mascherava il secondo (la modale si chiudeva prima di arrivare al pulsante incriminato).

## VERIFICATO

Banco di anteprima (regola del progetto: dati finti prima del `tsc`, prima del commit).
`ClosePositionModal` accetta un `closeFn` opzionale, di default la funzione vera — usato
**solo** dal banco per iniettare risposte finte, dato che l'endpoint non è ancora in
produzione (`VITE_BACKEND_API_BASE_URL` vuoto per regola condivisa del banco:
`requireBackend()` fallirebbe subito).

- **card reale**: il pulsante "Riduci / Chiudi" apre la modale, verificato dalla card
  vera dentro `PerpPane`, non solo dalla modale isolata
- **stime**: 50% di 12,345678 → 6,1728 quota e residuo, PnL stimato $2,46 — corretto
- **confirmed (parziale)**: schermata di esito con eseguito/prezzo/residuo/PnL, resta a
  schermo finché l'utente non preme "Chiudi" (dopo la correzione del bug #1)
- **confirmed + forced_full**: avviso esplicito "chiusa PER INTERO, non solo la quota
  richiesta"
- **stale_position**: la size mostrata si aggiorna da 12,3457 a 9,8765 (quella dal
  backend), le stime si ricalcolano, pulsante diventa "Riprova"
- **execution_failed**: messaggio "la posizione non è cambiata, puoi riprovare in
  sicurezza"
- **in_progress**: pulsante di conferma **disabilitato**, verificato via `.disabled`,
  non solo dal testo
- **errore di rete**: messaggio esplicito, nessun crash

**Verifica di sicurezza sulle due chiavi**, la parte che conta di più — non solo
dichiarata nel commento ma osservata: registrate le idempotency key ricevute a ogni
chiamata via un `closeFn` strumentato.

| Sequenza | Chiave | Atteso |
|---|---|---|
| 1. errore di rete | `c3b917...` | primo tentativo |
| 2. retry sullo stesso | `c3b917...` (identica) | stesso tentativo |
| 3. nuovo tentativo → `stale_position` | `471c75...` (nuova) | presupposti cambiati |
| 4. riconferma con size aggiornata | `f122ef...` (nuova ancora) | ancora presupposti cambiati |

`npx tsc -b` ed ESLint puliti: stessi 5 avvisi preesistenti su `AgentTab.tsx`, nessuno
nuovo.

## SCOSTAMENTI

- **Endpoint non in produzione**: verificato dalla chat A che non esiste ancora sulla
  VPS. Non è stato possibile un test end-to-end contro il backend vero — solo contro il
  contratto congelato, simulato.
- Working copy condivisa: durante il lavoro un checkout di `main` ha spostato sotto la
  chat A il branch su cui stava lavorando (`claude/manual-close-perp`, backend, 3 commit
  non pushati) — segnalato e corretto in tempo reale, nessun danno. Creato subito il
  branch proprio (`claude/manual-close-ui`).

## DELIVERABLE

- `src/services/agentApi.ts` — `closePerpPosition()`, tipi `ClosePerpPositionResponse`/
  `ClosePerpOutcome`/`ClosePerpPercentage`
- `src/components/AgentTab.tsx` — `ClosePositionModal`, card Perp ristrutturata,
  `PerpPane` con le nuove props
- Branch `claude/manual-close-ui`, commit `918caac`, da `main` `eed1bbd`

## NON FATTO — in attesa

Merge su `main`: **rimandato**. L'endpoint non è ancora in produzione; pubblicare ora
significherebbe un pulsante funzionante nell'app che chiama un endpoint inesistente per
chiunque lo premesse. In attesa che la chat A confermi il deploy del backend, o
un'indicazione esplicita di David.
