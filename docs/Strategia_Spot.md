# Strategia di Trading Spot - Agente AI Autonomo (V4)

> Documento aggiornato al codice corrente del repository.
> Riferimenti implementativi principali: `backend/app/agent/signals/spot/momentum.py`, `backend/app/agent/service.py`, `backend/app/agent/risk/manager.py`, `configs/strategy_spot.yaml`, `configs/risk.yaml`, `backend/app/schemas/mobile_agent.py`.

---

## 1. Sintesi V4

La strategia Spot V4 e' un motore long-only di momentum controllato, costruito per cercare asset che stanno iniziando a muoversi con struttura, volume e contesto coerenti, senza inseguire spike estremi.

Il flusso reale e':

1. scanner su watchlist Spot selezionata;
2. warmup OHLCV 5m via Binance klines spot, con cache breve;
3. calcolo segnale momentum/struttura;
4. filtri BTC di regime e inversione;
5. risk manager fail-closed;
6. meta-controller AI con poteri limitati;
7. esecuzione dry-run o preparazione live;
8. gestione posizione nel fast loop con stop, breakeven, trailing, TP e time stop.

Lo Spot resta diverso dal Perp: non usa Volume Profile come motore primario, ma una combinazione di trend/struttura, volume relativo, RSI, BTC context e sentiment.

---

## 2. Universo Operativo

- Opera solo su asset inclusi nell'universo eligible configurato.
- Usa la watchlist Spot selezionata dall'utente/app.
- Esclude stablecoin operative dallo scanner Spot.
- Una sola posizione aperta per asset, anche se l'asset e' gia' aperto sull'altro mercato.
- Il mercato Spot e' long-only: il segnale valido e' `enter_long`.

---

## 3. Dati Di Mercato

Lo scanner Spot lavora su candele 5m:

- minimo operativo: 50 candele;
- warmup: 100 candele;
- feed: Binance klines spot tramite `BinanceKlineFeed`;
- cache warmup: 240 secondi per ridurre chiamate HTTP.

Se il payload non contiene abbastanza candele e il warmup non riesce, il segnale salta con `insufficient_ohlcv_history`.

---

## 4. Motore Del Segnale

Il modulo `SpotMomentumSignal` calcola:

- VWAP sulle ultime 100 candele;
- ATR;
- EMA20 ed EMA50;
- RSI;
- relative volume;
- variazione percentuale tra ultima e penultima candela;
- estensione rispetto al VWAP in multipli di ATR.

### Score Di Qualita'

I pesi default sono:

| Componente | Peso default | Implementazione |
|---|---:|---|
| Trend/struttura | 30% | prezzo sopra VWAP, EMA20 > EMA50, breakout sopra massimo recente |
| Volume relativo | 30% | volume corrente rispetto alla media recente |
| BTC context | 15% | valore passato nel payload, default neutro 0.5 |
| RSI | 15% | fascia ottimale 45-72, penalita' fuori range |
| Sentiment | 10% | valore passato nel payload, default neutro 0.5 |

La qualita' finale e' normalizzata sui pesi configurati.

### Condizioni Di Trigger

Lo Spot entra solo se tutte le condizioni sono vere:

- volatilita' candela >= `spot_volatility_trigger_pct`;
- relative volume >= `spot_relative_volume_threshold`;
- trend score >= 0.45;
- estensione VWAP/ATR <= `spot_vwap_atr_extension_limit`;
- quality >= `spot_confidence_threshold`.

Default attuali da YAML:

| Parametro | Default |
|---|---:|
| `spot_confidence_threshold` | 0.55 |
| `spot_volatility_trigger_pct` | 0.4 |
| `spot_relative_volume_threshold` | 1.3 |
| `spot_vwap_atr_extension_limit` | 1.2 |

---

## 5. Filtro Anti-Spike

Prima dell'esecuzione, il segnale controlla se l'ATR corrente e' anomalo rispetto alla media ATR recente:

```text
atr_ratio = ATR_now / ATR_average
```

Default:

| Parametro | Default |
|---|---:|
| `spot_spike_filter_enabled` | true |
| `spot_spike_atr_ratio_max` | 3.0 |
| `spot_spike_atr_avg_period` | 50 |
| `spot_spike_action` | skip |
| `spot_spike_reduced_size_fraction` | 0.5 |

Se `spot_spike_action = skip`, un segnale valido viene annullato con reason `volatility_spike`. Se e' `reduce_size`, viene passato un `size_factor` ridotto, salvo margine Perp fisso che riguarda solo il Perp.

---

## 6. Filtri BTC Di Mercato

### Regime Spot Risk-Off

Il filtro `spot_market_regime` blocca nuovi buy Spot quando BTC e' in downtrend forte:

- timeframe: BTCUSDT 15m;
- EMA: 50;
- lookback nuovi minimi: 12 candele;
- entra in risk-off se BTC e' sotto EMA50 e fa nuovo minimo;
- esce dal risk-off solo quando BTC richiude sopra EMA50.

Lo stato e' persistito in `RuntimeState` per evitare flip-flop.

### Market Reversal Filter

Il filtro inversione BTC e' un secondo gate:

- timeframe: BTCUSDT 15m;
- EMA: 10;
- conferma default: 2 candele;
- bullish se ci sono 2 candele verdi consecutive sopra EMA10 e EMA10 sale;
- bearish se ci sono 2 candele rosse consecutive sotto EMA10.

Per lo Spot, dopo un segnale long valido:

- se il regime BTC e' risk-off, il segnale diventa `market_risk_off`;
- altrimenti, se il reversal filter non e' risk-on, il segnale diventa `market_reversal_waiting`.

Il filtro inversione non sblocca mai un blocco risk-off o un guardrail di rischio.

---

## 7. Stop Loss V4

Lo Stop Loss Spot ha due modalita' configurabili:

### Modalita' ATR

Default:

```text
stop_loss = entry - ATR * spot_atr_stop_multiplier
```

Default `spot_atr_stop_multiplier = 2.2`.

### Modalita' Lowest 20

Quando `spot_sl_mode = lowest`, lo stop e' strutturale:

```text
reference = minimo low nelle ultime N candele
stop_loss = reference * (1 - buffer_pct / 100)
```

Default:

| Parametro | Default |
|---|---:|
| `spot_structural_stop_lookback_candles` | 20 |
| `spot_structural_stop_buffer_pct` | 1.10 |

Il segnale salva anche `stop_reference` con:

- modalita';
- campo usato (`low`);
- timestamp candela;
- prezzo minimo;
- lookback;
- buffer.

Questo alimenta il dettaglio trade e il grafico con candela di riferimento.

---

## 8. Take Profit, Breakeven E Trailing

### Target ATR

I target sono ATR-based:

```text
TP1 = entry + ATR * spot_tp1_atr_multiplier
TP2 = entry + ATR * spot_tp2_atr_multiplier
```

Default:

| Parametro | Default |
|---|---:|
| `spot_tp1_atr_multiplier` | 2.0 |
| `spot_tp2_atr_multiplier` | 3.5 |

### Chiusura Parziale A TP1

Al primo raggiungimento di TP1:

- chiusura parziale;
- default UI/mobile `spot_tp1_close_pct = 50%`;
- parametro YAML storico `spot_tp1_close_fraction = 0.30`, ma la percentuale usata dal service arriva dai mobile settings.

TP2 diventa uscita finale solo dopo che TP1 e' stato raggiunto.

### Breakeven

Breakeven Spot e' abilitabile:

- default: attivo;
- trigger default: `entry + 0.6 * ATR`;
- modalita': `atr` oppure `tp1`;
- se `tp1`, il BE puo' scattare solo dopo TP1;
- con `spot_breakeven_offset_costs = true`, lo stop viene alzato a entry piu' costi stimati andata/ritorno;
- con `spot_breakeven_buffer_pct = 0.1`, se il prezzo lo permette, lo stop viene alzato a entry + 0.1%.

Lo stop non viene mai abbassato.

### Trailing

Trailing Spot:

- default: attivo;
- parte da subito se `spot_trailing_active_from_start = true`;
- usa il massimo raggiunto dalla posizione (`max_price`);
- formula:

```text
trailing_stop = max_price - ATR * min(spot_trailing_atr_multiplier, spot_tp1_atr_multiplier)
```

Il trailing diventa operativo solo se supera l'entry, cosi' non sostituisce lo stop iniziale con uno stop ancora in perdita.

---

## 9. Scale-In A Favore

Lo Spot V4 permette una sola aggiunta a favore, mai in perdita.

Condizioni default:

- `spot_scale_in_enabled = true`;
- posizione gia' in profitto;
- stop gia' a breakeven se `spot_scale_in_require_be_stop = true`;
- nuovo higher-high se `spot_scale_in_require_new_hh = true`;
- massimo aggiunte: `spot_scale_in_max_adds = 1`;
- size aggiunta: 50% del notional corrente;
- il notional totale non supera il cap nominale per trade.

La nuova entry viene ricalcolata come media ponderata, ma lo stop non viene abbassato.

---

## 10. Time Stop

Il time stop Spot e' opzionale e di default e' disattivato da app/dashboard.

Quando `spot_time_stop_enabled = true`, il time stop Spot e' ATR-aware:

- default `spot_time_stop_enabled = false`;
- default `spot_time_stop_mode = atr`;
- lookback default: 8 candele 5m;
- chiude solo se il movimento nelle ultime N candele e' inferiore a `0.5 * ATR`;
- usa la cache klines, senza fare HTTP dedicato;
- se non ci sono dati sufficienti non chiude;
- fallback orario default: 6 ore, usato solo se `spot_time_stop_mode = hours`.

---

## 11. Risk Management Spot

Il risk manager applica regole hard fail-closed:

- kill switch hard/soft/degraded;
- eligible universe;
- portfolio floor;
- drawdown cap;
- daily loss limit;
- liquidita' minima;
- dedup per asset tra Spot e Perp;
- max posizioni Spot;
- max esposizione Spot;
- cooldown per asset;
- min trade size.

Sizing Spot:

```text
nominal_size = equity * spot_capital_per_trade_pct / 100
risk_amount = equity * spot_per_trade_pct / 100
risk_size = min(nominal_size, risk_amount / stop_distance_pct)
```

Default mobile:

| Parametro | Default |
|---|---:|
| `spot_capital_per_trade_pct` | 6.0 |
| `spot_per_trade_pct` | 1.5 |
| `spot_max_open_positions` | 3 |
| `spot_max_exposure_pct` | 30.0 |
| `spot_cooldown_minutes` | 30 |
| `spot_max_slippage_pct` | 1.0 |

Il principio e': la size si adatta allo stop, lo stop non viene stretto per far tornare la size.

---

## 12. Esecuzione E Costi

### Dry-Run

In dry-run:

- viene creato uno `SpotTrade` con stato `prepared`;
- viene creata una `SpotPosition` aperta;
- lo slippage peggiora l'entry se `spot_fee_mode = all`;
- fee e slippage sono salvati sulla posizione e sul trade;
- PnL unrealized sottrae la swap fee.

### Live

In live:

- il provider Spot attivo viene usato via `ExecutionProvider`;
- gli indirizzi token vengono presi da `spot_token_map` o risolti via CMC;
- il quote token e' configurabile o risolto come USDT;
- se manca mapping/indirizzo, il trade viene saltato esplicitamente.

---

## 13. Gestione Posizione Nel Fast Loop

Il fast loop:

1. aggiorna prezzi live Spot in batch;
2. aggiorna PnL unrealized;
3. aggiorna massimo favorevole;
4. muove breakeven se le condizioni sono soddisfatte;
5. aggiorna trailing;
6. valuta scale-in;
7. chiude per priorita':
   - trailing stop;
   - stop loss o breakeven;
   - TP2 dopo TP1;
   - TP1 parziale;
   - time stop.

Le chiusure per SL/TP/trailing usano il livello di uscita specifico, non il prezzo corrente generico.

---

## 14. Osservabilita'

Ogni decisione salva:

- segnale;
- risk decision;
- brain decision;
- action;
- reasoning;
- trade id se eseguito.

Le viste app/dashboard mostrano:

- posizioni aperte;
- storico;
- PnL realized/unrealized;
- win rate;
- livelli SL/TP/trailing;
- costi;
- grafico trade con entry/exit, livelli e candela di riferimento dello stop.

---

## 15. Stato V4 E Debiti Futuri

Implementato:

- momentum Spot su VWAP/EMA/volume/RSI;
- filtri BTC;
- stop ATR o Lowest 20;
- TP ATR;
- breakeven e trailing;
- scale-in a favore;
- time stop ATR-aware;
- risk separato per mercato;
- costi dry-run espliciti;
- visualizzazione dettagli trade.

Debiti futuri:

- relative strength reale tra asset;
- market structure piu' granulare;
- candle exhaustion dedicato;
- order-flow/whale flow se disponibile;
- backtest quantitativo dei parametri V4.

---

## 16. Storico Versioni

| Versione | Sintesi |
|---|---|
| V1 | Score composito iniziale, RSI molto pesante. |
| V2 | Momentum + struttura, VWAP primario, RSI ridotto a filtro. |
| V3 | Risk e gestione posizione piu' aggressivi: ATR stop, TP ATR, breakeven, trailing, scale-in, anti-spike. |
| V4 | Allineamento al codice corrente: stop ATR/Lowest20 configurabile, filtri BTC persistiti, risk separato Spot/Perp, UI/dashboard e dettaglio trade con stop reference. |

---

*Fine documento Spot V4.*
