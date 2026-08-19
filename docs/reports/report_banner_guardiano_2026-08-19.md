# Banner del guardiano di regime e stato esplicito dell'agente

Data: 19 agosto 2026 · Branch: `claude/banner-guardiano` · Commit: `1d69cd3`
Perimetro: C (app Android e UI) · Richiesta dalla chat B (strategia e analisi), `NOTE/61` §6-bis

## COSA

Il backend espone lo stato del guardiano di regime (VERDE/GIALLO/ROSSO) dal 19/08, ma in
app non si vedeva: la protezione poteva scattare e l'unico avviso era la notifica push.

1. **`GuardianBanner`**, nuovo componente, sopra ogni schermata dell'agente:
   - **ROSSO / GIALLO**: riquadro con stato, spiegazione e **comandi di emergenza dentro**;
   - **VERDE**: un puntino e due parole;
   - **guardiano spento**: niente.
2. **Pannello di emergenza corretto**: badge di stato esplicito al posto del pulsante
   "Riprendi agente" perennemente visibile ma disabilitato.

## COME

**Perché i comandi stanno dentro il banner.** Quando il bot si sta proteggendo, il momento
peggiore per cercare la chiusura di emergenza è quello: era a tre tocchi di distanza,
dentro il setup. Ora "Chiudi tutto" e "Blocca entrate" sono nel banner stesso, visibile da
qualunque scheda (Spot, Perp, Global, Wallet, Coins, Setup).

**Perché in VERDE quasi sparisce.** Se il banner occupasse spazio anche nei giorni normali,
dopo una settimana lo si smetterebbe di guardare — e allora non servirebbe più nemmeno da
rosso. In VERDE resta un chip da 11px.

**"Blocca entrate", non "Metti in pausa".** Il pulsante manda `soft_stop`, che ferma le
nuove aperture **senza toccare le posizioni già aperte** (`hard_stop` e "chiudi tutto"
restano nel setup). Chiamarlo "pausa" avrebbe fatto credere che si fermasse tutto: in un
comando di emergenza l'ambiguità è pericolosa.

**Ripiego quando manca la spiegazione.** Il campo `guardian.explanation` è stato aggiunto
oggi dalla chat B su mia richiesta, ma si popola **solo alla prossima transizione**: alla
consegna era `null`. Il banner quindi mostra la spiegazione se c'è, altrimenti i fatti
concreti — quanti stop, in quante ore, quando l'ultimo. Non un buco.

**Controllo di coerenza lato client.** Se `explained_at` è più vecchio di `changed_at`
oltre due minuti, la spiegazione viene nascosta: un testo che racconta la transizione
precedente è peggio di nessun testo. Il backend ha già le sue protezioni (azzera il campo
a ogni transizione e scarta le risposte tardive del Brain); questo è il secondo strato,
concordato con la chat B.

**Tempi relativi** ("35 min fa") invece di orari: leggendo un allarme conta *da quanto*,
non *a che ora*.

## VERIFICATO

- **Anteprima nel browser approvata da David** su sei casi: rosso con spiegazione, rosso
  senza, giallo (lo stato **reale** del bot in quel momento: 1 stop, dalle 11:25), giallo
  con spiegazione, verde, e rosso ad agente già in pausa (dove "Blocca entrate" sparisce).
- **Campi API verificati dal vivo** prima di scrivere il componente: `state`, `enabled`,
  `stops_in_window`, `window_hours`, `last_stop_at`, `changed_at`, più `explanation` e
  `explained_at` (entrambi `null`, come atteso).
- `npx tsc -b` (lo stesso della CI) pulito. ESLint ai **5 errori preesistenti**, nessuno
  introdotto.
- `soft_stop` verificato nel codice esistente prima di usarlo: "Soft stop blocca nuove
  entrate. Hard stop ferma tutto" (`AgentTab.tsx`, pannello Kill switch).

## SCOSTAMENTI

- **Il mockup HTML non è stato usato**: la chat B lo aveva consegnato a David, ma non mi è
  stato girato. Ho costruito seguendo la descrizione testuale dei requisiti (§6-bis). La
  resa è stata approvata sull'anteprima, quindi l'esito è lo stesso, ma va detto che il
  confronto con il mockup originale **non è avvenuto**.
- **La spiegazione del Brain non è mai stata vista in funzione**: alla consegna il campo era
  `null` su tutte le transizioni disponibili. Il percorso "con spiegazione" è stato provato
  solo con testo finto nell'anteprima. Da riverificare alla prima transizione reale.

## QUESTIONI APERTE

- Se il testo del Brain risultasse più lungo dei 200-300 caratteri stimati, servirà un
  troncamento con "espandi" (concordato con la chat B: avvisarli se succede).
- Il banner compare solo dentro la scheda Agente. Se in futuro si volesse che comparisse
  anche in Mercato/Preferiti/Allarmi, va sollevato al livello di `App.tsx`.
- Non c'è ancora un modo per **silenziare** il banner rosso: è deliberato (deve essere
  impossibile da ignorare), ma se in pratica risultasse invadente durante un rosso lungo,
  se ne riparla.

## DELIVERABLE

- `src/components/GuardianBanner.tsx` — nuovo
- `src/components/AgentTab.tsx` — banner innestato, pannello emergenza corretto
- `src/services/agentApi.ts` — tipi `GuardianState` e `GuardianStatus`
- Branch `claude/banner-guardiano`, commit `1d69cd3`, da `main` `46bc74c`
