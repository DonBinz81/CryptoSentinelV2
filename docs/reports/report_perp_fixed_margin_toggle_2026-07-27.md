# Toggle Margine Fisso Perp - 2026-07-27

## COSA È STATO FATTO

Aggiunto un toggle per usare un margine fisso sulle nuove posizioni Perp. Il default resta disattivato; quando attivo usa 50 USD come margine predefinito configurabile.

## COME È STATO FATTO

Il contratto `AgentMobileSettings` ora include `perp_fixed_margin_enabled` e `perp_fixed_margin_usd`. Il risk manager usa il valore fisso solo per segnali Perp e solo quando il toggle e' attivo; con toggle spento resta il sizing dinamico esistente. Quando il toggle e' attivo, il margine fisso resta anche il margine finale eseguito: il brain puo' bloccare il trade, ma non dimezzare quell'importo.

## COSA È STATO VERIFICATO

Verificato il risk sizing Perp con margine fisso, la persistenza dei settings mobile, la compilazione Python backend e i tipi TypeScript di app e dashboard.

## SCOSTAMENTI DAL PIANO

Nessuno. La modifica e' additiva sui settings di rischio Perp.

## QUESTIONI APERTE

Nessuna.

## STATO DELIVERABLE

Completato e pronto per commit/push.
