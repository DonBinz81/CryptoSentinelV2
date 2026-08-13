# Report - Raggruppamento visivo history Perp

## 1. COSA È STATO FATTO

- Aggiunto `position_id` opzionale ai trade della history Perp.
- Mostrato un badge/colonna posizione nelle UI mobile e dashboard.
- Reso piu' chiaro che TP1 parziale e chiusura finale possono appartenere alla stessa posizione.

## 2. COME È STATO FATTO

- Per i close trade `cls_<position_id>_<suffix>` il backend estrae il `position_id` dal `trade_id`.
- Per gli open trade associa il `position_id` tramite `open_trade_id`.
- Mobile mostra `Pos <id breve>` sulle card della history Perp.
- Dashboard aggiunge la colonna `Pos` nella tabella history Perp.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m py_compile backend/app/persistence/views.py backend/app/schemas/views.py`
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_persistence_layer.py -q -k "perp_history_uses_position_entry_for_partial_closes or spot_and_perp_views_return_open_positions"`
- `npm exec tsc -- -b --pretty false`
- `npx tsc -p dashboard/tsconfig.json --noEmit`

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Per trade molto vecchi senza posizione associabile il campo resta vuoto.

## 6. STATO DELIVERABLE

- Implementato e verificato con controlli mirati.
