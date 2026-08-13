# Market Reversal Filter - 2026-07-01

## COSA È STATO FATTO

- Aggiunto il filtro configurabile `Filtro inversione mercato`, attivo di default nel setup del bot.
- Il filtro usa BTC su timeframe 15m con EMA10, due candele verdi consecutive, close sopra EMA10 ed EMA10 in salita.
- Una volta entrato bullish, resta attivo finché BTC non fa due candele rosse consecutive sotto EMA10.
- Lo Spot lo applica solo quando un segnale vorrebbe già aprire una nuova posizione; non sblocca mai stati `market_risk_off` o altri guardrail.
- Il Perp lo usa in modo simmetrico: blocca nuovi short quando BTC è bullish e blocca nuovi long quando BTC è bearish.

## COME È STATO FATTO

- Aggiunti campi Settings/YAML e contratto mobile: `market_reversal_filter_enabled` e parametri BTC/EMA/confirmations.
- Aggiunto toggle nel setup mobile con label `Filtro inversione mercato`.
- Reso il controllo visibile come toggle dedicato nella sezione `Filtri mercato` del setup, invece di un selettore dentro `Risk globale`.
- Implementato `_market_reversal_filter()` in `AgentService`, riusando il feed Binance klines già presente e persistendo lo stato direzionale `bullish`/`bearish`/`neutral`.
- Aggiunti test unitari per Spot risk-off non sbloccato, Spot in attesa conferma, blocco short Perp, blocco long Perp e passaggio bullish→bearish solo dopo due rosse sotto EMA10.

## COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m py_compile backend/app/core/config.py backend/app/schemas/mobile_agent.py backend/app/api/routes/mobile_agent.py backend/app/agent/service.py` completato con successo.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py backend/tests/unit/test_mobile_agent_step7.py -q` completato con successo: 61 passed.
- `npm exec tsc -- -b --pretty false` completato con successo.
- Dopo la revisione UI del toggle, `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_mobile_agent_step7.py::test_mobile_agent_settings_are_persisted -q` completato con successo: 1 passed.

## SCOSTAMENTI DAL PIANO

- Nessuno.

## QUESTIONI APERTE

- Nessuna per questa implementazione.

## STATO DELIVERABLE

- Implementato e verificato.
