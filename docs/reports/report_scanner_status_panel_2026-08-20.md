# App: pannello "sta cercando o è bloccato" per spot e perp

Data: 20 agosto 2026 · Branch: `claude/scanner-status-panel` · Commit: `ec20e01`
Perimetro: C (app Android e UI) — lato app del lavoro backend della chat D

## COSA

David: *"il perp è fermo da ieri, non so se sono i filtri o se è la strategia che non
trova edge. Stessa domanda per lo spot."* Voleva un'informazione in tempo reale in app
che distingua i due casi.

Il backend (chat D, commit `4f72717`) ha già risolto il lato dati: persiste l'esito di
ogni ciclo di scansione e lo espone su `GET /api/v1/views/scanner-status`. Questo è il
lato app: `ScannerStatusPanel`, montato subito dopo `GuardianBanner` in `AgentTab.tsx`.

## COME

Quattro stati, con lo stesso registro del banner del guardiano (nota 62): silenzioso
nei giorni normali, netto quando serve attenzione.

- **verde (chip)** — nessun mercato bloccato in modo significativo: "Scanner attivo:
  in cerca di un segnale"
- **giallo (banner)** — un mercato ha una quota rilevante di asset filtrati, col motivo
  prevalente tradotto in italiano (es. "18 bloccati: guardiano in rosso")
- **rosso (banner, `role="alert"`)** — `stale`: il ciclo non gira più. Diverso da
  "nessun segnale" e segnalato con urgenza diversa, esplicitamente: *"Non è nessun
  segnale: il bot non sta guardando il mercato."*
- **chip neutro** — primo ciclo non ancora registrato (es. dopo un riavvio): non è un
  allarme, è solo presto

I codici del motore (`market_reversal_short_blocked`, `guardian_red_capital_preservation`,
…) sono tradotti in italiano leggibile in un dizionario (`MOTIVI`); un codice non
previsto si mostra così com'è invece di sparire.

### La soglia di "bloccato" — trovata sbagliata testando coi dati veri

Prima versione: `bloccato = filter + error > 0`. Provando il pannello nel banco di
anteprima con i **numeri reali** passati dalla chat D (1 filtrato su 28 perp), quella
soglia produceva un banner giallo "FILTRI ATTIVI" — che **contraddiceva** la lettura
corretta fatta dalla chat D sugli stessi identici numeri: *"il bot non è bloccato, sta
cercando e non trova."*

Un asset isolato su una lista ampia è rumore statistico, non una notizia. Soglia
corretta: `error > 0` (un errore conta sempre, non è mai rumore) oppure
`filter >= max(2, 20% degli scansionati)`.

⚠️ Senza aver provato il pannello contro il caso reale invece che con dati inventati a
caso, questa contraddizione sarebbe passata inosservata: un numero qualsiasi scelto per
comodo (tipo "3 filtrati su 10") non l'avrebbe fatta emergere.

## VERIFICATO

- **Col DOM renderizzato**, non con lo screenshot: il pannello screenshot del browser
  non era disponibile in questa sessione (limite lato client dello strumento). La verifica
  è stata fatta leggendo il testo effettivamente montato nella pagina (`get_page_text`),
  sui quattro stati e sull'inserimento nel contesto reale accanto a `GuardianBanner`.
- I quattro stati, uno per uno, coi dati del banco di anteprima.
- L'inserimento reale: `GuardianBanner` (verde) + `ScannerStatusPanel` (verde) montati
  insieme, per controllare che il layout regga con entrambi presenti.
- `npx tsc -b` (lo stesso della CI) pulito.
- ESLint sui tre file toccati: 5 avvisi, **verificati preesistenti su `main`** con
  `git stash` prima di committare — nessuno introdotto da questa modifica.
- Build APK di prova sul branch: vedi esito nel log del task.

## SCOSTAMENTI

- Non è stato possibile vedere il rendering **visivo** (colori, spaziatura) in questa
  sessione — solo la struttura e il testo. Da controllare a occhio alla prima apertura
  reale dell'app.
- La soglia `20% / minimo 2` è una scelta ragionevole ma arbitraria, tarata sull'unico
  caso reale disponibile (1/28). Se in produzione risultasse troppo o poco sensibile,
  va rivista con più cicli osservati.

## DELIVERABLE

- `src/components/ScannerStatusPanel.tsx` — nuovo componente
- `src/services/agentApi.ts` — `ScannerStatusResponse`, `ScannerMarketStatus`,
  `fetchScannerStatus()`
- `src/components/AgentTab.tsx` — stato, polling (refresh completo e veloce), montaggio
- Branch `claude/scanner-status-panel`, commit `ec20e01`, da `main` `4f72717`
