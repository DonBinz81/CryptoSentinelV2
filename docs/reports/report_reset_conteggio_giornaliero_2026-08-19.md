# Azzeramento del conteggio giornaliero in app

Data: 19 agosto 2026 · Branch: `claude/reset-conteggio-ui` · Commit: `54d7325`
Perimetro: C (app Android e UI) · Backend: chat B (strategia e analisi), endpoint già in produzione

## COSA

Il banner del blocco rischio, quando scatta il guard sulla perdita giornaliera, ora ha un
comando per **far ripartire il conteggio da adesso**. Il limite non cambia e la protezione
non si disarma: lo stesso `daily_loss_limit_pct` vale sul nuovo tratto.

Aggiunta anche la **traccia**: se il conteggio è già stato azzerato oggi, sopra i comandi
compare in ambra «Conteggio azzerato N volte oggi · ultimo alle HH:MM».

## COME

**Tre livelli di attrito**, decisi da David («autorizzazione solo del boss»):

1. **admin token** — verificato dal backend, come per ogni comando sensibile;
2. **PIN** — lo stesso della modalità sviluppatore;
3. **conferma con i numeri veri** — non un generico "sei sicuro?", ma perdita di oggi e
   limite davanti agli occhi.

**Perché tanto attrito.** Quel limite serve proprio nel momento in cui uno vuole
scavalcarlo: dopo una giornata storta, con la voglia di recuperare. Se il gesto costasse un
tocco, la protezione non esisterebbe.

**Cosa dice la conferma, e in che ordine.** Per prima la cosa scomoda: *il limite non
cambia, quindi puoi perdere di nuovo la stessa cifra prima che il blocco torni*. È la
conseguenza che rende il limite un tetto **per tratto** invece che **per giornata**, ed è
stata segnalata a David prima che scegliesse.

Poi una tutela che il backend ha implementato e che si darebbe per scontata al contrario:
**le perdite delle posizioni ancora aperte continuano a contare**, l'azzeramento riguarda
solo quelle già chiuse. Il rischio in corso non si nasconde premendo un pulsante.

**Il pulsante è grigio**, non rosso, e sta sotto «Rivedi il limite giornaliero»: la via
ordinaria resta cambiare il parametro, che lascia il valore visibile. L'azzeramento è
l'eccezione.

**`DEV_PIN` era una costante privata** di `SettingsTab.tsx:67`. Estratta in
`src/utils/devPin.ts` e letta da entrambi i punti: due costanti uguali in due file prima o
poi divergono, e qui divergere significherebbe un comando che si sblocca con un PIN che
l'utente non conosce più.

## VERIFICATO

- **Endpoint provato dal vivo** prima di scrivere il componente: `POST
  /api/v1/agent/risk/reset-daily-counter` risponde `422` senza corpo (esiste e valida),
  contratto letto dal codice in produzione (`ResetDailyCounterRequest`, campo `note`).
- **Campi nuovi verificati sull'API reale**: `daily_counter_resets_today: 0`,
  `daily_counter_reset_at: None` dentro `risk_guardrail`.
- **Anteprima approvata da David** su banner e finestra di conferma.
- `npx tsc -b` (lo stesso della CI) pulito; ESLint ai **5 errori preesistenti**, nessuno
  introdotto.

## SCOSTAMENTI

- **Il comando non è mai stato eseguito davvero.** Ho verificato che l'endpoint esista e
  risponda, ma non l'ho invocato: avrebbe azzerato il conteggio reale del bot, che è una
  decisione di David, non mia. Il percorso completo (chiamata → risposta → aggiornamento
  del banner → comparsa della riga ambra) è quindi **da provare alla prima esecuzione
  vera**.
- Il controllo del PIN è **lato client**: non è un segreto crittografico, è attrito
  deliberato. La vera autorizzazione resta l'admin token, verificato dal backend.

## QUESTIONI APERTE

- Se il backend rispondesse con uno `status` diverso da `ok`/`success`, l'app mostra
  `reason` grezzo. Al primo uso reale va visto che sia comprensibile.
- Nessun limite al numero di azzeramenti giornalieri: è deliberato (la traccia serve a
  quello), ma se in pratica risultassero troppi se ne riparla.

## DELIVERABLE

- `src/components/AgentTab.tsx` — pulsante, traccia dei reset, `ResetCounterDialog`
- `src/services/agentApi.ts` — `resetDailyCounter()`, campi nuovi nel tipo del guardrail
- `src/utils/devPin.ts` — costante condivisa (nuovo)
- `src/components/SettingsTab.tsx` — usa la costante condivisa
- Branch `claude/reset-conteggio-ui`, commit `54d7325`, da `main` `d6f331a`
