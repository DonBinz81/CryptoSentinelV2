# App: pulsante per azzerare il picco del drawdown

Data: 22 agosto 2026 · Branch: `claude/reset-drawdown-peak-app` · Commit: `292bda2`
Perimetro: C (app Android e UI) — lato app di NOTE/83 (backend, chat B)

## COSA

Il backend è in produzione da ieri: `POST /api/v1/agent/risk/reset-drawdown-peak`
(admin, campo `note`), gemello 1:1 del reset del conteggio giornaliero (NOTE/63).
Riporta `peak_equity_usd` all'equity corrente, azzerando il drawdown senza toccare il
cap in percentuale. Mancava solo il lato app.

## COME

Generalizzato `ResetCounterDialog` (prima specifico del solo daily-loss) con un
parametro `kind: 'daily_loss' | 'drawdown_peak'`: stessa cornice — admin token, PIN,
conferma coi numeri veri — testi e numeri diversi per tipo, scelti da un piccolo
dizionario (`RESET_COPY`) invece di duplicare il componente.

`RiskGuardrailBanner`: pulsante "Azzera il picco del drawdown" quando
`reason === 'drawdown_cap_guard'` (prima il pulsante esisteva solo per
`daily_loss_limit_guard`), e riga ambra "Picco azzerato N volte oggi" gemella di
quella già presente per il conteggio giornaliero.

`GlobalPane` esportata (come già `SetupPane`) per poterla montare nel banco di
anteprima.

## VERIFICATO

Nel banco di anteprima, con i **numeri reali** dello screenshot di David (drawdown
11,69%, cap 10%):

- il pulsante compare e apre il dialogo corretto, con "Drawdown 11,69% / Cap 10,00%"
  e l'avviso specifico del picco — non quello del daily loss
- il tasto "Azzera" resta disabilitato finché il PIN non è quello giusto, verificato
  in entrambi gli stati (senza PIN → disabilitato; con `6878` → abilitato)
- la riga ambra "Picco azzerato 2 volte oggi · ultimo alle HH:MM" compare quando il
  backend riporta `resets_today > 0`
- il **gemello daily-loss** verificato invariato nello stesso banco, per assicurarsi
  che generalizzare il dialogo non l'avesse rotto

`npx tsc -b` ed ESLint puliti: stessi 5 avvisi preesistenti su `AgentTab.tsx`,
nessuno nuovo.

## SCOSTAMENTI

⚠️ **Il comando non è mai stato eseguito contro il backend reale** (stesso
avvertimento di NOTE/63 §6): verificato che l'endpoint esista e risponda nella forma
attesa, non invocato — azzererebbe lo stato reale del bot, decisione di David.

## DELIVERABLE

- `src/services/agentApi.ts` — `resetDrawdownPeak()`, `ResetDrawdownPeakResponse`,
  campi `drawdown_peak_resets_today`/`drawdown_peak_reset_at` sul tipo
  `GlobalView['risk_guardrail']`
- `src/components/AgentTab.tsx` — `ResetCounterDialog` generalizzato, pulsante e riga
  di stato nel banner, `GlobalPane` esportata
- Branch `claude/reset-drawdown-peak-app`, commit `292bda2`, da `main` `2dec533`
