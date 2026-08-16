# Report - Profit Lock Ratchet: uscite parziali nel tratto TP1-TP2

Data: 2026-08-16

---

## COSA È STATO FATTO

Riscritto il Profit Lock Ratchet secondo la strategia definita dall'utente. La
versione precedente misurava le soglie **dall'entry price** e si limitava ad
alzare lo stop; la strategia prevede invece **uscite parziali** misurate sul
tratto **TP1→TP2**, piu' un breakeven dedicato e la corsa oltre il TP2.

Con TP1 a 2,5 ATR e TP2 a 4,0, appena toccato il TP1 il progresso valeva gia'
62,5%: il primo scalino scattava in partenza e lo stop finiva **sotto** il prezzo
del parziale appena incassato.

## COME È STATO FATTO

Tre meccanismi distinti, tutti configurabili dall'app:

1. **Uscite parziali** agli scalini, con quote **cumulative** sul residuo
   post-TP1 (default 50→25 / 70→50 / 95→80: al 95% del tratto si e' chiuso l'80%,
   il 20% corre verso il TP2).
2. **Breakeven del ratchet**: stop fisso a una quota del tratto, armato solo
   dallo scalino configurato in poi (default 50% del tratto, dal 3° scalino).
3. **Oltre il TP2**: se al controllo il prezzo risulta gia' oltre il TP2 ("superato
   di slancio") non si chiude e parte un trailing percentuale dal massimo
   (default 1%). Il TP2 chiude solo se toccato esattamente.

Modifiche:

- `backend/app/agent/service.py`
  - `_profit_lock_stop` sostituita da `_ratchet_progress`, `_ratchet_level`,
    `_ratchet_breakeven_price`.
  - `_close_perp_position` accetta `close_fraction` per chiudere quote arbitrarie;
    una quota che azzererebbe la size diventa **chiusura piena** (altrimenti la
    posizione resterebbe `open` con size 0).
  - nuovo blocco ratchet in `_check_sl_tp` + gestione della corsa oltre il TP2.
- `backend/app/persistence/models/positions.py`: campo `ratchet_state` (JSON con
  `base_size`, `closed_frac`, `last_step`).
- `backend/app/persistence/database.py`: migrazione idempotente
  `ALTER TABLE perp_positions ADD COLUMN ratchet_state TEXT`.
- `backend/app/core/config.py`, `schemas/mobile_agent.py`,
  `api/routes/mobile_agent.py`: 4 parametri nuovi.
- `configs/strategy_perp.yaml`: default funzionali (aggiunti il 17/08, vedi
  Scostamenti).
- `src/components/AgentTab.tsx`, `src/services/agentApi.ts`: etichette
  "Livello/Chiudi" e i quattro controlli nuovi.

Validatore corretto: rimosso il vincolo `lock < soglia`, privo di senso con la
nuova semantica (livello raggiunto e quota da chiudere sono grandezze diverse).
`ratchet_breakeven_after_step` viene **clampato** al numero di scalini invece di
far fallire il salvataggio.

## COSA È STATO VERIFICATO

- **22/22 test** del ratchet passano: progresso misurato dal TP1, quote cumulative
  e non a catena, clamp, simmetria short, breakeven sopra il TP1, guardie sui
  parametri assenti.
- Suite `backend/tests/unit`: 199 passed, 3 failed. Tutte e tre **preesistenti o
  ambientali**, verificate con controprova sul codice originale — la terza
  (`test_agent_service_dry_run_persists_perp_decision_and_trade`) dipende dai dati
  di mercato reali (`relative_volume` cambia a ogni esecuzione).
- Deploy: backup `~/backups/pre_ratchet_20260816_224221.db`, `integrity_check`
  **ok** prima e dopo, migrazione applicata (`ratchet_state` presente in
  `PRAGMA table_info`), impostazioni utente preservate, API espone i 4 parametri,
  heartbeat attivo, nessun errore correlato nei log.
- Caricamento del YAML verificato: le liste diventano `tuple`, gli altri parametri
  perp restano invariati.

## SCOSTAMENTI DAL PIANO

- **Violazione sanata il 17/08**: i default dei nuovi parametri erano stati messi
  solo nei default Pydantic, non in `configs/strategy_perp.yaml`, contro la regola
  di precedenza della configurazione. Corretto e verificato.
- Commenti del codice in italiano anziche' in inglese come da regola: scelta
  esplicita dell'utente per coerenza con la prassi del repository (il
  `service.py` upstream ne contiene 36 in italiano).
- Test eseguiti con il virtualenv della VPS: `backend\.venv` non esiste su questa
  workstation.
- Numero di scalini fisso a 3 (non aggiungibili dall'app): rimandato allo step
  successivo per non allargare l'intervento.

## QUESTIONI APERTE

- **Le fee aumentano**: dopo il TP1 si passa da una chiusura a un massimo di
  quattro. E' lo stesso problema del TP1 sotto le fee: su posizioni piccole le
  parziali possono erodere il guadagno. Da misurare sui primi trade reali.
- **Nessuna protezione del ratchet fra il TP1 e l'ultimo scalino** (scelta
  dell'utente): in quella fascia restano attivi solo stop loss e breakeven classico.
- **Il TP2 chiudera' di rado**: la condizione "prezzo esattamente uguale al TP2"
  e' rara con prezzi Decimal, quindi in pratica si passera' quasi sempre al
  trailing.
- **Non validato su backtest**: il motore non modella chiusure parziali multiple.
- Il blocco integrato in `_check_sl_tp` **non ha test end-to-end**: nessuna
  posizione ha ancora superato il TP1 dopo il deploy.

## STATO DELIVERABLE

**Completato.** Deployato in produzione, commit `bda10be` pushato. Prima verifica
sul campo attesa sulla posizione COMP, aperta e non ancora arrivata al TP1.
