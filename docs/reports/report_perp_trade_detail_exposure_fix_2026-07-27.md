# Fix Exposure Dettaglio Trade Perp - 2026-07-27

## COSA È STATO FATTO

Corretto il campo `exposure_usd` nei dettagli dei trade Perp dashboard/app.

## COME È STATO FATTO

La vista dettaglio Perp ora calcola l'exposure come nozionale reale `size * entry_price`. Il margine resta esposto nel campo separato `margin_usd`.

## COSA È STATO VERIFICATO

Aggiunta una regressione unit mirata su un caso Perp long TRX 25x: margine 8.86 USD ed exposure 221.55 USD.

## SCOSTAMENTI DAL PIANO

Nessuno.

## QUESTIONI APERTE

Nessuna.

## STATO DELIVERABLE

Pronto per commit e push dopo esecuzione dei test.
