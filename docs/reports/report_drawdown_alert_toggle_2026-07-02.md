# Report - Toggle allarme drawdown

## 1. COSA È STATO FATTO

- Aggiunto nel setup mobile il toggle `Allarme drawdown`.
- Aggiunto il flag backend `risk_drawdown_alert_enabled`, default attivo.
- Collegato il toggle al salvataggio runtime delle impostazioni agente.
- Disattivato l'invio notifiche drawdown quando il toggle e' spento.

## 2. COME È STATO FATTO

- Esteso `Settings` e il mapping YAML/env per la configurazione FCM/risk.
- Esteso il contratto mobile `AgentMobileSettings` e il client TypeScript.
- Inserito il toggle nella sezione `Risk globale`.
- Protetto `_check_risk_notifications`: il drawdown chiama `notify_risk_alert` solo se `risk_drawdown_alert_enabled` e' attivo.
- Lasciati invariati gli altri alert rischio critici, inclusi kill switch e portfolio floor.

## 3. COSA È STATO VERIFICATO

- `npm exec tsc -- -b --pretty false`
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_mobile_agent_step7.py::test_mobile_agent_settings_are_persisted backend/tests/unit/test_agent_step6.py::test_drawdown_alert_toggle_disables_notification -q`

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Nessuna.

## 6. STATO DELIVERABLE

- Implementato, in attesa dei controlli finali.
