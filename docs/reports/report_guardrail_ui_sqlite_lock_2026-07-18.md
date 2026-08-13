# Report Guardrail UI e SQLite Lock - 2026-07-18

## 1. COSA È STATO FATTO

Reso visibile il blocco operativo dei guardrail risk su app mobile e dashboard. Mitigato l'errore SQLite `database is locked` osservato su `/api/v1/alerts/sync`.

## 2. COME È STATO FATTO

La vista globale backend ora espone `risk_guardrail` con stato `blocked`, motivo, dettagli e soglie operative. Mobile e dashboard renderizzano un banner quando il blocco è attivo. Il motore SQLite sincrono usa timeout/WAL/busy timeout e `AlertStore` serializza le scritture con retry/backoff breve.

## 3. COSA È STATO VERIFICATO

- `py_compile` sui file backend modificati.
- `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/unit/test_alert_store.py backend/tests/unit/test_persistence_layer.py -q`: 29 passed.
- `npm run build`: completato.
- `npm run dashboard:build`: completato.

## 4. SCOSTAMENTI DAL PIANO

Nessuno. Le modifiche sono additive e non allentano i guardrail.

## 5. QUESTIONI APERTE

La lock SQLite è mitigata per il carico single-user; se il traffico concorrente cresce, PostgreSQL resta la soluzione strutturale.

## 6. STATO DELIVERABLE

Implementazione completata e verificata.
