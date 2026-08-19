# Report — Reset del contatore di perdita giornaliera (comando admin)

Data: 2026-08-19 sera · Branch: `claude/reset-daily-counter` · Riferimento: `NOTE/63`

## 1. COSA È STATO FATTO

Comando admin per far ripartire da adesso il conteggio della perdita giornaliera quando
il `daily_loss_limit_guard` blocca il trading — senza alzare il limite né disarmare la
protezione, e con traccia visibile e permanente di ogni utilizzo (scelta esplicita di
David: il limite resta aggirabile, ma mai in silenzio).

- `POST /api/v1/agent/risk/reset-daily-counter` (admin only, `note` opzionale).
- 3 colonne nuove su `portfolio_state`: `daily_counter_since` (nuovo punto di partenza
  della somma), `daily_counter_reset_at`, `daily_counter_resets_today`.
- Traccia esposta in `/api/v1/views/global` → `risk_guardrail` (`daily_counter_resets_today`,
  `daily_counter_reset_at`), in tutti i rami del guardrail — incluso il verde, che è
  esattamente lo stato che un reset produce.

## 2. COME È STATO FATTO

- Il valore giornaliero non è un contatore ma una somma ricalcolata a ogni tick da
  `day_start`: il reset sposta il punto di partenza (`effective_start = max(day_start,
  daily_counter_since)`) dentro `_update_portfolio_state`. Un marker rimasto da un giorno
  precedente viene ripulito lì, nello stesso tick che attraversa la mezzanotte — nessun
  job di rollover separato.
- **L'unrealized delle posizioni aperte continua a contare dopo il reset**: riparte solo
  la somma del realized. Semantica deliberata: il rischio aperto non si nasconde mai.
- `reset_daily_loss_counter` registra la perdita corrente PRIMA di azzerare (log
  strutturato `daily_loss_counter_reset`: pnl_before_pct, equity, resets_today, note),
  incrementa il contatore se l'ultimo reset è dello stesso giorno UTC (altrimenti riparte
  da 1) e ricalcola subito il portafoglio, così la view riflette il nuovo conteggio alla
  lettura successiva e non al prossimo tick da 5 s.
- Migrazione idempotente `ALTER TABLE` come per `ratchet_state`; datetimi da SQLite
  normalizzati a UTC (`_ensure_utc`) prima di ogni confronto.

## 3. COSA È STATO VERIFICATO

- 4 test nuovi (`backend/tests/unit/test_daily_counter_reset.py`): perdita pre-reset
  fuori dal conteggio e perdita post-reset dentro; incremento del contatore nello stesso
  giorno; pulizia automatica al rollover di mezzanotte; primo reset di un giorno nuovo
  riparte da 1.
- Suite completa su VPS (interprete di produzione, copia isolata): **326 passed,
  2 failed** — i 2 preesistenti documentati. Baseline precedente 322/2 → +4, tutti verdi.
- Deploy con protocollo standard e backup freddo del DB (la migrazione tocca
  `portfolio_state`); hash verificati; endpoint e campi della view provati dal vivo.

## 4. SCOSTAMENTI DAL PIANO

- Il resume citava NOTE/62 come numero della nota: era già occupato da un'altra sessione
  (banner in app) — la nota è la **63** e i riferimenti nel codice sono stati allineati.
- Nessun altro scostamento rispetto al resume approvato.

## 5. QUESTIONI APERTE

- Lato app (chat C): pulsante con conferma esplicita sui numeri correnti e badge
  «azzerato alle HH:MM · N volte oggi» — i campi ci sono già.
- La traccia vive nelle colonne (stato corrente) e nei log strutturati (storico):
  nessuna tabella di audit dedicata in v1, come concordato.
- Semantica dichiarata da conoscere: subito dopo un reset con posizioni aperte in
  perdita, il conteggio NON è zero — mostra l'unrealized vivo. È voluto.

## 6. STATO DELIVERABLE

Completo, testato, deployato (esito nel presente report e in NOTE/63).
