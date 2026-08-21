# Report — Reset del picco drawdown con traccia (NOTE/83)

Data: 2026-08-21 · Branch: `claude/reset-drawdown-peak` · Richiesta di David (via chat C, gemello di NOTE/63)

## 1. COSA È STATO FATTO

Nuovo endpoint admin `POST /api/v1/agent/risk/reset-drawdown-peak` che ri-basa il
riferimento del drawdown (`portfolio_state.peak_equity_usd`) all'equity corrente.

Motivazione: il picco cresce e basta (`peak = max(peak, total)` in
`service.py`), quindi quando `drawdown_cap_guard` scatta resta agganciato senza
alcuna via d'uscita naturale — a differenza del daily counter, che almeno rolla a
mezzanotte. In produzione il blocco era attivo (drawdown 11.69% contro cap 10%)
e nessuna nuova entrata era possibile a tempo indeterminato.

Il cap NON viene toccato: stessa percentuale, subito attiva sul nuovo tratto.
`max_drawdown_pct` (record storico) resta intatto. Traccia visibile:
`drawdown_peak_reset_at` + `drawdown_peak_resets_today` in `risk_guardrail`
accanto ai gemelli `daily_counter_*`, in tutti i rami incluso il verde.

## 2. COME È STATO FATTO

Specchio 1:1 del pattern NOTE/63 (reset daily counter):

- `persistence/models/pnl.py`: due colonne nuove su `PortfolioState`
  (`drawdown_peak_reset_at` DATETIME, `drawdown_peak_resets_today` INT).
- `persistence/database.py`: migrazioni ALTER TABLE idempotenti (stessa lista).
- `agent/service.py`: metodo `reset_drawdown_peak()` (contatore per giorno,
  log strutturato `drawdown_peak_reset` con picco e drawdown cancellati,
  ricalcolo immediato del portfolio); rollover della traccia a mezzanotte nello
  stesso blocco del gemello in `_update_portfolio_state` (il picco non rolla:
  è già stato ri-basato al momento del reset).
- `api/routes/agent.py`: route con `AdminAccessDep`, body riusa
  `ResetDailyCounterRequest` (campo `note` opzionale, max 120).
- `schemas/views.py` + `persistence/views.py`: i due campi esposti in
  `RiskGuardrailView` in tutti e 4 i rami (floor, drawdown, daily loss, verde).

Protezione a tre livelli come deciso da David per NOTE/63 (token admin lato
backend; PIN 6878 e conferma con numeri reali lato app, a cura di chat C che
riusa `ResetCounterDialog`).

## 3. COSA È STATO VERIFICATO

- 5 test nuovi (`backend/tests/unit/test_drawdown_peak_reset.py`, specchio del
  gemello): reset porta il drawdown a ~0 e il picco all'equity; il cap resta
  armato sul nuovo tratto (−88 su base 880 → 10.00%); `max_drawdown_pct` non
  viene riavvolto; contatore incrementa nello stesso giorno e riparte da 1 il
  giorno dopo; la traccia si pulisce al primo aggiornamento dopo mezzanotte.
- Suite completa su VPS: **359 passed, 3 failed, 2 skipped**. I 3 falliti
  (`test_support_api` ticket-flow, 2 in `test_agent_step6`) falliscono
  identici anche su main pulito (`git archive HEAD` testato nella stessa
  sessione VPS): pre-esistenti, non regressioni di questa modifica.
- Anti-tautologia: i 5 test non possono passare sul codice vecchio (metodo,
  colonne e campi vista non esistono su main).

## 4. SCOSTAMENTI DAL PIANO

Nessuno. Spec di chat C implementata com'era: unica scelta interpretativa, il
rollover a mezzanotte pulisce SOLO la traccia (timestamp + contatore), non il
picco, perché il picco ri-basato è il nuovo stato funzionale e non ha nulla da
rollare — coerente col gemello, dove invece anche `daily_counter_since` rolla
perché lì il punto di partenza È lo stato funzionale.

## 5. QUESTIONI APERTE

- Lato app (dialog con PIN e numeri reali) a cura di chat C.
- Il reset è una decisione dell'owner: ogni uso resta nel log e nella vista,
  ma nessun limite automatico al numero di reset per giorno (come per il
  gemello — scelta deliberata NOTE/63).

## 6. STATO DELIVERABLE

Completo lato backend. Deploy su VPS con backup freddo del DB (migrazione
schema), servizio riavviato, hash verificati. Il reset in sé NON è stato
eseguito: è una decisione dell'owner, David lo lancia dall'app (o su sua
richiesta esplicita via endpoint). Merge in main e push eseguiti.
