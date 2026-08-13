# Prezzo Candela Riferimento SL Perp - 2026-07-29

## COSA È STATO FATTO

Aggiunto nei dettagli trade Perp il prezzo minimo/massimo della candela usata come riferimento per lo stop loss.

## COME È STATO FATTO

Il backend espone `stop_reference_price` e `stop_reference_field` nel payload del dettaglio Perp. App mobile e dashboard mostrano il valore sotto `Risk levels` con etichetta `Min candela ref SL` per riferimenti `low` e `Max candela ref SL` per riferimenti `high`.

## COSA È STATO VERIFICATO

Aggiunta una regressione unit sul dettaglio Perp per verificare prezzo e campo della candela riferimento SL. Eseguiti `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py -q`, `backend\.venv\Scripts\python.exe -m compileall backend/app -q`, `npx tsc --noEmit -p tsconfig.app.json` e `npx tsc --noEmit -p dashboard/tsconfig.json`.

## SCOSTAMENTI DAL PIANO

Nessuno. La modifica e' solo di esposizione dati e UI, senza cambiare il calcolo dello stop loss.

## QUESTIONI APERTE

Nessuna.

## STATO DELIVERABLE

Completato e pronto per commit/push.
