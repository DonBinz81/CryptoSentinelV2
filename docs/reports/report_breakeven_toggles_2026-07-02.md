# Report - Toggle breakeven Spot e Perp

## 1. COSA È STATO FATTO

- Aggiunti due toggle separati nel setup mobile: `Breakeven Spot` e `Breakeven Perp`.
- Aggiunti i flag configurabili `spot_breakeven_enabled` e `perp_breakeven_enabled`.
- Mantenuto il default attivo per entrambi.

## 2. COME È STATO FATTO

- Estesi i default YAML di strategia Spot e Perp.
- Esteso il loader unico `Settings` e il contratto `AgentMobileSettings`.
- Collegato il salvataggio runtime mobile ai campi `Settings` live.
- Applicato il controllo nel loop veloce di gestione posizioni: se il toggle e' spento, il relativo mercato non alza nuovi stop a breakeven.
- Lasciati invariati trailing, stop loss, take profit e stop gia' eventualmente spostati.

## 3. COSA È STATO VERIFICATO

- `npm exec tsc -- -b --pretty false`
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_mobile_agent_step7.py::test_mobile_agent_settings_are_persisted backend/tests/unit/test_agent_step6.py::test_spot_breakeven_toggle_disables_stop_lift backend/tests/unit/test_agent_step6.py::test_perp_breakeven_toggle_disables_stop_lift -q`

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Nessuna.

## 6. STATO DELIVERABLE

- Implementato, in attesa dei controlli finali.
