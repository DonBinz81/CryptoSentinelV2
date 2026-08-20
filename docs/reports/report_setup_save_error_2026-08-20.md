# App: clamp e traduzione dell'errore su Setup, campi "candele grafico"

Data: 20 agosto 2026 · Branch: `claude/setup-save-error-fix` · Commit: `6572b77`
Perimetro: C (app Android e UI)

## COSA

David ha mandato uno screenshot: campo "Candele post-chiusura" a `2876` (il vincolo
del backend è ≤ 288), salvataggio rifiutato con `Agent API: 422 —
post_close_candles: Input should be less than or equal to 288`. Nessun altro valore
della pagina Setup veniva salvato insieme, perché il `PUT /agent/settings` manda
**tutto il modello Pydantic in un blocco unico**: un solo campo fuori range fa
fallire l'intero salvataggio.

## COME

Due correzioni indipendenti, entrambe nel gruppo "GRAFICO TRADE" del pannello Setup:

**1. Clamp al blur.** `NumberInput` accetta ora `min`/`max` opzionali. Quando l'utente
esce dal campo con un valore fuori range, viene riportato dentro il limite (non
mentre digita, per non litigare con la battitura), con un avviso giallo temporaneo
("Riportato al massimo consentito (288)"). Applicato a `post_close_candles` (0-288) e
`chart_pre_open_candles` (1-288) — gli unici due campi di quel gruppo con un tetto
dichiarato nello schema Pydantic e già annunciato nel testo di aiuto ("Massimo 288"),
quindi non una sorpresa per l'utente.

**2. Traduzione del messaggio d'errore.** Il 422 mostrava il nome tecnico del campo
(`post_close_candles`) invece dell'etichetta che l'utente vede in Setup ("Candele
post-chiusura (0=off)"). `traduciErroreSalvataggio()` sostituisce il nome tecnico con
l'etichetta italiana quando la conosce; un campo non mappato resta col nome tecnico
invece di sparire — non è un errore, solo un messaggio meno chiaro.

### Il difetto trovato mentre correggevo il difetto

Il primo tentativo esportava `traduciErroreSalvataggio` direttamente da
`AgentTab.tsx`. ESLint (`react-refresh/only-export-components`) l'ha segnalato subito:
un file di componenti non può esportare anche funzioni pure, o Fast Refresh smette di
funzionare per l'intero file. Spostata la funzione e la mappa delle etichette in un
nuovo modulo, `src/services/settingsErrorLabels.ts`.

## VERIFICATO

Nel banco di anteprima con `SetupPane` **reale** (non un mock), non con codice
duplicato. Digitato `2876` nel campo vero, verificato che l'`onBlur` reale lo riporti
a 288 con l'avviso corretto; simulato il messaggio 422 esatto ricevuto da David e
verificato che diventi "Candele post-chiusura (0=off): Input should be less than or
equal to 288".

⚠️ Il browser di questa sessione non compone i frame (screenshot e click non
disponibili). Un primo tentativo di simulare `blur`/`focusout` via `dispatchEvent` non
funzionava — **non per un difetto del componente**, ma perché quegli eventi sintetici
non attraversano la delega di React senza un vero ciclo di focus del browser.
Verificato chiamando `props.onBlur` direttamente dal Fiber di React: è comunque il
componente vero (stessa funzione, stesso closure), non una riscrittura della sua
logica — solo un modo diverso di invocarlo che bypassa il sistema di eventi del DOM,
non la logica applicativa.

`npx tsc -b` pulito. ESLint: 5 avvisi su `AgentTab.tsx`, verificati preesistenti su
`main` con `git stash` prima di committare (il sesto, introdotto dal primo tentativo,
è stato corretto spostando il codice in un modulo separato — non nascosto).

## SCOSTAMENTI

- Non è stato possibile verificare il comportamento con un vero gesto di tocco/tab
  sul campo (limite del browser di questa sessione, non del codice).
- La mappa `ETICHETTA_CAMPO` copre 60 campi estratti automaticamente dai
  `NumberInput` esistenti in `AgentTab.tsx` più i 3 con firma di callback diversa
  aggiunti a mano (verificati uno per uno). Un campo futuro con vincolo min/max andrà
  aggiunto lì, altrimenti l'errore resta leggibile ma col nome tecnico.

## QUESTIONI APERTE

- Il salvataggio resta **un blocco unico**: un solo campo fuori range blocca ancora
  tutti gli altri valori della pagina. Il clamp risolve il caso più comune (digitazione
  distratta), ma se in futuro capitasse un valore fuori range non prevenibile lato
  client (es. arrivato da un default corrotto), il problema di fondo (nessun salvataggio
  parziale) resterebbe. Non affrontato qui: fuori dallo scopo della segnalazione di
  David, e cambierebbe il contratto dell'endpoint lato backend.

## DELIVERABLE

- `src/components/AgentTab.tsx` — `NumberInput` con clamp, `min`/`max` sui due campi,
  uso di `traduciErroreSalvataggio` in `handleSave`
- `src/services/settingsErrorLabels.ts` — nuovo modulo, mappa + funzione di traduzione
- Branch `claude/setup-save-error-fix`, commit `6572b77`, da `main` `acbc90d`
