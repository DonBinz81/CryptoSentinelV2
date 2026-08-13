# Report - Dettaglio Entry Originale Smart SL Perp - 2026-08-09

## 1. COSA È STATO FATTO

- Corretto il dettaglio trade Smart Stop Loss Perp per mostrare l'entry originale anche dopo un rebuy che modifica l'entry corrente della posizione.
- Collegati i trade `ssl_...` alla relativa posizione Perp nel backend.
- Aggiornate mobile app e dashboard per leggere il nuovo campo `original_entry_price`.

## 2. COME È STATO FATTO

- `backend/app/api/routes/views.py` ora riconosce il prefisso `ssl_` in `_find_trade_position`.
- Il payload `trade-detail` Smart SL espone `original_entry_price` e `current_position_entry_price`.
- Per compatibilità, nei dettagli Smart SL `entry_price` resta valorizzato con l'entry originale.
- `dashboard/src/types.ts` e `src/services/agentApi.ts` sono stati estesi con i campi opzionali.
- Le viste dettaglio mostrano l'entry corrente solo quando differisce dall'entry originale.

## 3. COSA È STATO VERIFICATO

- Aggiunto un test unitario backend che simula uno Smart SL con `original_entry=100` ed entry posizione corrente `97`, verificando che il dettaglio esponga entrambi i valori.
- Eseguito `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py -q -k "smart_sl_detail_preserves_original_entry or perp_trade_detail_exposure_uses_notional_once"`: 2 test passati.
- Eseguito `npm run build`: build mobile/web completata.
- Eseguito `npm run dashboard:build`: build dashboard completata.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno. La modifica è limitata alla read model e alla visualizzazione del dettaglio trade.

## 5. QUESTIONI APERTE

- La history continua a includere gli eventi Smart SL come righe operative separate. Se serve, si può aggiungere un filtro UI dedicato per nasconderli o raggrupparli sotto la posizione principale.

## 6. STATO DELIVERABLE

- Deliverable completato e verificato.
