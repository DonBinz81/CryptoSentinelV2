# Report - Il trade forzato giornaliero rispetta i mercati attivi

## COSA È STATO FATTO

Con `markets_enabled = "perp"` il motore apriva comunque **un trade spot forzato su ETH al
giorno**. L'interruttore dei mercati nell'app risultava su "solo perp" mentre il motore
continuava a operare in spot: lo stato mostrato e lo stato reale non coincidevano.

La causa è l'ordine delle istruzioni in `slow_tick`: `_daily_trade_heartbeat` veniva
chiamato **prima** del calcolo dei mercati attivi, e la funzione non li consulta mai per
conto suo. Controlla soltanto il numero di trade del giorno, la finestra oraria
20:00–23:30 UTC, il kill switch, e che ETH non sia già in posizione.

Ora il heartbeat viene invocato solo quando lo spot è fra i mercati attivi. Quando non lo
è restituisce `{"status": "skipped", "reason": "spot_market_disabled"}`.

**Le posizioni spot già aperte non sono toccate**: le gestisce `fast_tick`, che opera a
prescindere da questa impostazione, quindi arrivano a chiusura normalmente.

## COME È STATO FATTO

`backend/app/agent/service.py`, dentro `slow_tick` — una riga spostata, undici aggiunte:

```python
markets = _active_markets(self._ms.markets_enabled)
trade_heartbeat = (
    await self._daily_trade_heartbeat(session, now=_now)
    if "spot" in markets
    else {"status": "skipped", "reason": "spot_market_disabled"}
)
```

Il valore restituito finisce nel payload di `slow_tick` (campo `daily_trade_heartbeat`) e
nel campo `status` del ciclo, che resta `"idle"` perché il confronto esistente è
`!= "executed"`. Nessun consumatore esterno legge quel campo: verificato su tutto
`backend/app`.

**Non sono stati toccati**: `_daily_trade_heartbeat`, `minimum_trades_per_day`,
`HARD_MIN_TRADES_PER_DAY`, né alcun file di configurazione.

## COSA È STATO VERIFICATO

Due test nuovi in `backend/tests/unit/test_agent_step6.py`, **visti fallire prima**:

| test | versione precedente | con la modifica |
|---|---|---|
| `test_heartbeat_does_not_open_spot_when_market_disabled` | **FALLISCE** | passa |
| `test_heartbeat_still_opens_spot_when_market_enabled` | passa | passa |

Il secondo è di non-regressione: senza di esso, anche **rimuovere** del tutto la chiamata
al heartbeat farebbe passare il primo. Il primo verifica il fatto che conta — nessun trade
spot raggiunge il database — non solo l'etichetta restituita.

Suite completa sulla VPS: **634 passed, 2 failed, 2 skipped**. I due falliti sono i
preesistenti noti (`test_support_api::test_support_ticket_thread_and_admin_status_flow` e
`test_agent_step6::test_meta_controller_reduce`). I 634 sono i 632 della baseline più i due
nuovi.

## SCOSTAMENTI DAL PIANO

**Deroga dichiarata a una regola di `AGENTS.md`**: *«Minimum trade frequency must be at
least 1 trade per day»*. Con lo spot disattivato il trade giornaliero non viene più aperto,
quindi la regola non è più soddisfatta.

Non è una scelta tecnica: è la conseguenza diretta della decisione di David di spegnere lo
spot (22/11/2026). Il minimo rigido `HARD_MIN_TRADES_PER_DAY = 1` resta invariato nel
codice e continua a impedire l'avvio del servizio se qualcuno prova ad abbassarlo da
configurazione: la deroga vale solo quando il mercato spot è spento.

## QUESTIONI APERTE

**Un test intermittente, non introdotto da questa modifica.**
`test_agent_step6::test_agent_service_dry_run_persists_perp_decision_and_trade` è stato
visto fallire **una volta** nella suite completa, e poi passare: da solo, dentro il proprio
file, e in una seconda esecuzione identica della suite completa. Non dipende da questa
modifica — che non tocca il percorso perp — ma è reale ed è stato osservato. Un domani farà
dubitare di un deploy sano.

**Il rimborso della perdita spot** (punto 2 del piano) va calcolato **dopo** questo deploy:
finché il motore opera in spot la cifra cresce. Al 22/11 16:20 UTC vale −41,68 $, tutto
realizzato, con zero posizioni spot aperte.

## STATO DELIVERABLE

- `backend/app/agent/service.py` — modificato, 12 righe
- `backend/tests/unit/test_agent_step6.py` — due test nuovi, 54 righe
- `docs/reports/report_spot_heartbeat_off_2026-11-22.md` — questo report

Pronto per il deploy su `main`. Non modifica lo schema del database, non richiede
migrazioni, non tocca configurazioni.
