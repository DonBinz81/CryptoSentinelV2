# Report — Cap di rischio sul margine fisso perp

Data: 2026-08-20 · Branch: `claude/cap-margine-fisso` · Riferimento: `NOTE/70`, `NOTE/60` §2

## 1. COSA È STATO FATTO

Chiuso il difetto per cui il margine fisso perp scavalcava il vincolo di rischio FIX-1:
la perdita allo stop poteva superare il budget configurato (`equity × per_trade_pct`)
fino a ~2× (LINK 19/08: budget 15,2 $, perdita 27,5 $). Ora il margine fisso è un
bersaglio cappato dal budget: `risk_size = min(margine_fisso, risk_bounded)`. Nessun
parametro nuovo: `Rischio %` (già esposto in app) torna a essere la manopola vera.

## 2. COME È STATO FATTO

- `agent/risk/manager.py`: `risk_bounded` (già calcolato da FIX-1) tracciato fuori dal
  blocco condizionale; il ramo del margine fisso applica `min(fisso, bound)` invece
  dell'override incondizionato. Reason distinta `risk_approved_fixed_margin_capped`
  quando il cap morde, così il log decisioni mostra quando e quanto riduce.
- Fail-closed: margine cappato sotto `min_trade_size_usd` → rifiuto
  (`below_minimum_trade_size`), non un trade sottodimensionato.
- Limite dichiarato e inchiodato da test: senza stop loss non esiste bound → il fisso
  passa come prima (sul perp lo stop strutturale c'è sempre: caso teorico).
- Prima del via, replay sulle 32 posizioni reali dal 18/08 (NOTE/70 §2): PnL netto
  quasi neutro (+7 $), perdite delle 6 stoppate −132,7 → −86,3; il cap morde sul 100%
  delle posizioni coi settaggi attuali — segnalato a David con la scelta (a)/(b) su
  `Rischio %`, che resta sua dall'app.

## 3. COSA È STATO VERIFICATO

- 4 test nuovi (`backend/tests/unit/test_risk_fixed_margin_cap.py`), inclusa la
  regressione coi numeri veri di LINK: perdita allo stop == budget al centesimo.
- Il test legacy `test_risk_engine_perp_fixed_margin_overrides_dynamic_size` passa
  invariato (leva 1 → bound non mordente → comportamento identico a prima).
- Suite completa su VPS (interprete di produzione, copia isolata): **341 passed,
  2 failed** — i 2 preesistenti documentati. Golden test economico verde.
- Deploy col protocollo standard (hash verificati), verifica runtime nei log.

## 4. SCOSTAMENTI DAL PIANO

Nessuno rispetto al resume approvato. La fixture Settings del test è stata riusata da
`test_agent_step6` invece di duplicarla (una copia a mano falliva la validazione sui
campi gas reserve).

## 5. QUESTIONI APERTE

- Scelta di taratura di David, dall'app: (a) restare a Rischio 1,5% (margini effettivi
  25-40 $, max loss 15,2 $) o (b) alzare a ~3% (fisso 50 quasi sempre intero, coda
  cappata ~30 $). Il codice è lo stesso.
- Le giornate etichettate precedenti al 20/08 portano i numeri del difetto: nel
  confronto col campione successivo va dichiarato (NOTE/70 §5).
- Se il cap morde mentre il Guardiano è GIALLO, la reason mostra il GIALLO (l'ultima
  scrittura vince): perdita d'informazione minima, solo nel log.

## 6. STATO DELIVERABLE

Completo, testato, deployato (esito nel presente report e in NOTE/70).
