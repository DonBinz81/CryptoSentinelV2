# Report — Throttle delle notifiche di rischio

Data: 2026-08-19 · Branch: `claude/guardiano-regime` · Riferimento: `NOTE/60` §4

## 1. COSA È STATO FATTO

Fermato lo spam degli allarmi rischio (202 push in 2 ore il 19/08): ora, per ogni
`alert_type`, al massimo **un push per intervallo** (default 60 minuti, promemoria di
condizione persistente) con **re-invio anticipato solo se il valore peggiora di almeno
1 punto** (escalation). Parametri: `risk_alert_min_interval_minutes`,
`risk_alert_escalation_step` (Settings + `configs/instance.example.yaml`, gruppo fcm).

## 2. COME È STATO FATTO

- `AgentNotifier.notify_risk_alert`: la vecchia dedup sul testo esatto (che re-inviava a
  ogni variazione di 0,1 punti del drawdown nel messaggio) è sostituita da stato per
  alert_type in RuntimeState (`last_risk_notification:<tipo>`): `detail`, `value`,
  `sent_at`. Invia se l'intervallo è trascorso O se `value >= ultimo_inviato + step`.
- `_check_risk_notifications` (service.py) passa `value=drawdown` all'allarme drawdown;
  kill_switch e portfolio_floor restano senza valore (solo intervallo).
- La notifica del Guardiano (`notify_guardian_state`) non è toccata: le transizioni sono
  eventi discreti e restano una-per-cambio.

## 3. COSA È STATO VERIFICATO

Suite completa su VPS: **318 passed, 2 failed** (i 2 preesistenti documentati), 2 skipped.
Test nuovi: oscillazione 0,1-0,4 punti soppressa entro l'intervallo (il bug del 19/08),
escalation +1 punto re-invia subito, promemoria dopo intervallo scaduto re-invia.
Aggiornato `test_risk_different_detail_resends` che codificava il comportamento difettoso.

## 4. SCOSTAMENTI DAL PIANO

Nessuno. I due parametri non sono esposti nell'app (solo YAML/env): esporli è banale se
David li vorrà nel Setup.

## 5. QUESTIONI APERTE

- Con la chiave nuova per alert_type, il primo allarme dopo il deploy riparte da stato
  vuoto: un push singolo anche se la condizione era già notificata prima del deploy.
- Il pulsante snooze in-app resta perimetro C.

## 6. STATO DELIVERABLE

Completo, testato, deployato il 2026-08-19 col protocollo standard (hash verificati).
