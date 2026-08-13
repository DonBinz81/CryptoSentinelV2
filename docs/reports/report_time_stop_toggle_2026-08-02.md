# Report Toggle Time Stop - 2026-08-02

## 1. COSA È STATO FATTO

Aggiunto un toggle dedicato per il Time Stop Spot e Perp, visibile sia nell'app sia nella dashboard, con durata configurabile in ore.

## 2. COME È STATO FATTO

Sono stati aggiunti i campi `spot_time_stop_enabled` e `perp_time_stop_enabled` al contratto settings mobile/backend, con default `false`. Le ore esistenti `spot_time_stop_hours` e `perp_time_stop_hours` restano configurabili. Il fast loop backend valuta il time stop solo quando il toggle relativo e' attivo.

## 3. COSA È STATO VERIFICATO

Verificati i punti di integrazione tra schema backend, mapping runtime settings, app mobile, dashboard e default YAML. I test eseguiti sono riportati nella risposta operativa.

## 4. SCOSTAMENTI DAL PIANO

Nessuno. La modifica e' additiva e non cambia stop loss, take profit, breakeven o trailing.

## 5. QUESTIONI APERTE

Resta da validare su dispositivo reale che la posizione dei nuovi controlli nelle impostazioni mobile sia ergonomica.

## 6. STATO DELIVERABLE

Deliverable completato: toggle Time Stop disattivo di default, durata in ore configurabile e controllo applicato dal backend.
