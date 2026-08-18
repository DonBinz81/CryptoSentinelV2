# Setup: quattro parametri esposti e stato del pannello ricordato

Data: 18 agosto 2026 · Branch: `claude/setup-minori` · Commit: `2d6639a`, `097d3bc`

## COSA

Due lavori minori sul pannello Setup dell'app, chiusi insieme.

1. **Lo stato del pannello sopravvive ai rientri.** La sotto-scheda attiva
   (Generale/Spot/Perp/Sistema) e i blocchi richiudibili (Smart SL, shock BTC)
   ripartivano da capo a ogni uscita: si tornava sempre su "Generale" con tutto
   richiuso.
2. **Quattro parametri usati dal motore ma invisibili nell'app** ora hanno un
   controllo, ciascuno col suo `HelpTip`:

| controllo | dove | campo |
|---|---|---|
| N° candele per calcolo stop | Spot → SPOT — STRATEGIA, sotto "Buffer Min20 %" | `spot_structural_stop_lookback_candles` |
| N° candele per calcolo stop | Perp → PERP — STRATEGIA, sotto "Buffer Min/Max20 %" | `perp_structural_stop_lookback_candles` |
| Trailing Stop Perp | Perp, sopra "Protezione profitto" | `perp_trailing_enabled` |
| Liquidità minima $ | Generale → FILTRI GLOBALI, primo controllo | `min_pool_liquidity_usd` |

3. **Le intestazioni di sezione sono colorate per significato.** Erano tutte
   grigie e indistinguibili: in una pagina lunga non si capiva a colpo d'occhio
   che tipo di parametri si stesse guardando.

| tono | sezioni |
|---|---|
| rosso | Risk globale · Spot — risk · Perp — risk |
| blu | Spot/Perp — strategia · **Posizioni aperte** (cio' che e' vivo adesso) |
| verde | Spot/Perp — protezioni |
| ambra | Filtri globali |
| grigio | storici, wallet, watchlist: consultazione, non azione |

## COME

**Stato ricordato:** non è stato introdotto alcun meccanismo nuovo. `agentCache`,
la cache di modulo che il file usa già per non azzerare i dati ai rientri, ha due
campi in più (`setupTab`, `openBlocks`). La sincronizzazione avviene con un
effetto: il primo tentativo scriveva nella cache **dentro l'updater di
`setState`**, che React può rieseguire — segnalato dal linter e corretto.

**Selezione dei parametri:** dei 100 campi dello schema `AgentMobileSettings`, 85
erano già esposti. I 15 restanti sono stati classificati confrontando lo schema
con gli usi reali nel motore:

- **5 legacy** (`max_open_positions`, `cooldown_minutes`, `per_trade_pct`,
  `capital_per_trade_pct`, `max_slippage_pct`, `market_reversal_filter_enabled`):
  già sostituiti dalle varianti `spot_`/`perp_` che l'app espone. Lasciati stare.
- **4 vivi**: esposti (tabella sopra).
- **3 scollegati**: vedi §SCOSTAMENTI.
- **`network`**: non esposto di proposito — l'interruttore testnet/mainnet non
  deve stare a un tocco di distanza in un pannello di impostazioni.

**Nomi:** decisi da David guardando l'anteprima. "Candele stop Min20" e
"Candele stop Min/Max20" (nomi interni del tipo di stop) sono diventati
**"N° candele per calcolo stop"**, che dice cosa si conta e a cosa serve — utile
perché la sezione "Grafico trade" ha da stanotte un "Candele prima
dell'apertura", e i due parametri sono diversi. Il trailing perp è stato
allineato al gemello già esistente nella scheda Spot: **"Trailing Stop Perp"**.

**Intestazioni:** nuovo componente `SectionTitle` (barretta verticale + testo
colorato), scelto da David fra tre varianti guardate nell'anteprima. Il colore
segue il **significato**, non il mercato: le linguette in alto dicono gia' se sei
in Spot o Perp, mentre il colore dice cosa stai per toccare. Fuori dal Setup il
colore acceso resta l'eccezione — se tutto fosse colorato, il colore sarebbe
decorazione invece che indicazione.

**File nuovo:** i 101 valori di partenza passano a
`src/components/agentDefaults.ts`. Non è una scelta estetica: esportarli da un
file di componenti rompe il ricaricamento rapido (`react-refresh`), ed erano da
esportare per montare il pannello nel banco di anteprima.

## VERIFICATO

- **Fotografia meccanica del pannello**, prima (da `main`) e dopo: **87 → 91
  controlli, 85 → 89 campi**, quattro aggiunte e nessuna modifica al resto.
- **Default invariati**: confronto valore per valore dei 101 default prima e dopo
  lo spostamento nel file nuovo — **nessuna differenza**.
- **Persistenza provata nel banco**: aperto il blocco Smart SL nella scheda Perp,
  simulato uscita e rientro (rimontaggio del componente): scheda e blocco
  ritrovati aperti. Prima si tornava a "Generale" con tutto richiuso.
- **Posizioni verificate nel DOM**, non solo nel codice: ogni controllo nuovo con
  i suoi vicini sopra e sotto.
- **Intestazioni verificate nel pannello reale** leggendo i colori calcolati dal
  browser, non le classi CSS: "Filtri globali" ambra, "Risk globale" rosso, e
  nella scheda Perp la sequenza rosso -> blu -> verde. Zero intestazioni rimaste
  col vecchio stile grigio (19 su 19 convertite).
- `npx tsc -b` (lo stesso della CI) pulito; ESLint ai **5 errori preesistenti**,
  nessuno introdotto.

⚠️ **La fotografia meccanica era difettosa e lo era anche stanotte.** Leggeva
400 caratteri per tag e **perdeva i controlli con testi di aiuto lunghi**: ne
vedeva 72 su 86. La verifica di stanotte sul campo "Candele prima
dell'apertura" resta valida (quel controllo è corto, quindi visibile), ma una
modifica a un controllo "lungo" sarebbe passata inosservata. Ora legge fino alla
chiusura del tag e **confronta il numero di controlli letti con i tag presenti
nel file**, così il punto cieco si manifesta invece di restare muto.

## SCOSTAMENTI

Tre parametri **non** esposti perché il motore non li usa. Esporli darebbe
manopole che sembrano funzionare e non fanno nulla — peggio della loro assenza:

| campo | cosa succede davvero |
|---|---|
| `max_total_exposure_pct` | il salvataggio dall'app **non lo applica**: non è in `_MOBILE_TO_SETTINGS` e il risk manager legge solo `settings.risk_max_total_exposure_pct` (variabile d'ambiente) |
| `spot_trailing_distance_pct` | **nessun uso nel motore**: la distanza fissa del trailing spot non è implementata (l'interruttore `spot_trailing_enabled` invece funziona) |
| `spot_partial_take_profit_pct` | **nessun uso nel motore**: l'incasso parziale spot non è implementato |
| `operating_hours_utc` | solo rimandato indietro nel payload: il filtro orario non esiste |

Sono difetti latenti del backend, fuori dal perimetro di questa sessione.

## QUESTIONI APERTE

- I tre parametri scollegati: decidere se **implementarli** o **rimuoverli dallo
  schema**. Finché restano, l'API accetta valori che non hanno effetto.
- `network` resta non esposto: se un giorno servisse, va protetto come il PIN
  sviluppatore, non messo fra le impostazioni ordinarie.
- Il vecchio `TradeCandleChart.tsx` (resa SVG di ripiego) può essere rimosso: il
  grafico nuovo è approvato e in produzione dalla v1.0.52.

## DELIVERABLE

- `src/components/AgentTab.tsx` — quattro controlli, stato ricordato, −101 righe
- `src/components/agentDefaults.ts` — valori di partenza (file nuovo)
- `SectionTitle` in `AgentTab.tsx` — 19 intestazioni colorate per significato
- Branch `claude/setup-minori`, commit `2d6639a`, da `main` `d70805a`
