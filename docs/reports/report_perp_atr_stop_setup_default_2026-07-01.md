# Perp ATR Stop Setup Default - 2026-07-01

## COSA È STATO FATTO

- Portato il default dello stop ATR Perp a `0.8`.
- Allineato il parametro esistente nel setup del bot (`perp_atr_stop_multiplier`) tra configurazione backend, schema mobile, default frontend e strategia Perpetual.
- Aggiornata la migrazione di backfill Perp per ricostruire gli stop iniziali aperti con `0.8 * ATR`.

## COME È STATO FATTO

- Aggiornato `configs/strategy_perp.yaml` con `atr_stop_multiplier: 0.8`.
- Aggiornato `Settings.perp_atr_stop_multiplier` e lo schema `MobileAgentSettings`.
- Aggiornato il default di `AgentTab.tsx`; il campo era già presente nel setup bot e continua a salvare tramite la route mobile esistente.
- Aggiornati i fixture dei test Step 6/7 e la documentazione Perpetual.

## COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m py_compile backend/app/core/config.py backend/app/schemas/mobile_agent.py backend/app/api/routes/mobile_agent.py backend/app/persistence/migration.py backend/app/agent/signals/perp/volume_profile.py` completato con successo.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_mobile_agent_step7.py::test_mobile_agent_settings_are_persisted backend/tests/unit/test_agent_step6.py::test_perp_sl_tp_are_atr_anchored_with_controlled_rr -q` completato con successo: 2 passed.
- `npm exec tsc -- -b --pretty false` completato con successo.
- La suite completa `backend/tests/unit/test_agent_step6.py` non è green per 4 failure non introdotte da questo intervento: `selected_assets` non definito nello slow tick e due assert esistenti sul motivo `breakeven`/`trailing_stop`.

## SCOSTAMENTI DAL PIANO

- Nessuno.

## QUESTIONI APERTE

- Restano da trattare separatamente le failure non correlate emerse nella suite completa `test_agent_step6.py`.

## STATO DELIVERABLE

- Implementato e verificato con test mirati.
