# Strategia di Trading Perpetual - Agente AI Autonomo (V4)

> Documento aggiornato al codice corrente del repository.
> Riferimenti implementativi principali: `backend/app/agent/signals/perp/volume_profile.py`, `backend/app/agent/service.py`, `backend/app/agent/risk/manager.py`, `configs/strategy_perp.yaml`, `configs/risk.yaml`, `backend/app/schemas/mobile_agent.py`.

---

## 1. Sintesi V4

La strategia Perpetual V4 e' un motore long/short basato su Volume Profile rolling e rientro in value, con gestione del rischio separata dal mercato Spot.

Il flusso reale e':

1. scanner su watchlist Perp selezionata;
2. fetch OHLCV 5m futures via Binance klines;
3. costruzione Volume Profile 24h;
4. rilevazione setup di rientro in value;
5. filtro direzionale e filtro BTC inversione;
6. leva dinamica su ATR;
7. risk manager fail-closed con sizing separato Perp;
8. meta-controller AI con poteri limitati;
9. esecuzione dry-run o provider Perp live;
10. gestione posizione nel fast loop con breakeven, trailing, TP, time stop e funding.

Il Perp non cerca momentum puro: cerca eccessi rispetto alla value area e rientri confermati.

---

## 2. Universo Operativo

- Opera solo su asset inclusi nell'universo eligible configurato.
- Usa la watchlist Perp selezionata dall'utente/app.
- Una sola posizione aperta per asset, anche se l'asset e' gia' aperto sullo Spot.
- Direzione configurabile:
  - `long_short`;
  - `long`;
  - `short`.

Se il segnale produce una direzione non consentita, viene annullato.

---

## 3. Dati Di Mercato

Il Volume Profile usa candele futures Binance:

| Parametro | Default |
|---|---:|
| `perp_volume_profile_window_hours` | 24 |
| `perp_volume_profile_candle_minutes` | 5 |
| Candele teoriche | 288 |
| Minimo dati accettato | max(24, finestra / 4) |

Se i dati sono insufficienti, il segnale salta con `insufficient_binance_klines`.

Filtro liquidita' Volume Profile:

```text
total_quote_volume = somma(close * volume)
```

Default `perp_min_volume_profile_liquidity_usd = 50000`.

Se il volume e' sotto soglia, il segnale salta con `volume_profile_liquidity_filter`.

---

## 4. Volume Profile

Il profilo viene costruito su bucket di prezzo:

```text
tick = max((high - low) / 80, high * 0.0005)
bucket = round(round(typical_price / tick) * tick, 8)
typical_price = (high + low + close) / 3
```

Per ogni bucket viene sommato il volume.

Livelli:

- `POC`: bucket con volume massimo;
- `VAH`: massimo prezzo dentro la value area;
- `VAL`: minimo prezzo dentro la value area;
- value area default: 68%.

Questa e' una mappa operativa, non un segnale automatico.

---

## 5. Setup Di Entrata

La strategia cerca rientro in value dopo un eccesso.

### Long

Condizione implementata:

```text
previous.close < VAL
current.close > previous.high
```

Interpretazione:

- candela precedente sotto value area;
- candela corrente rompe sopra il massimo precedente;
- il rientro suggerisce che l'eccesso ribassista non e' stato accettato.

### Short

Condizione implementata:

```text
previous.close > VAH
current.close < previous.low
```

Interpretazione:

- candela precedente sopra value area;
- candela corrente rompe sotto il minimo precedente;
- il rientro suggerisce che l'eccesso rialzista non e' stato accettato.

---

## 6. Filtri Di Trend E Direzione

Il filtro VWAP impedisce mean reversion contro un impulso troppo estremo:

- long annullato se il prezzo e' sotto `VWAP * 0.97`;
- short annullato se il prezzo e' sopra `VWAP * 1.03`.

Il filtro direzionale applica `perp_direction_mode`:

- se modalita' `long`, gli short vengono annullati;
- se modalita' `short`, i long vengono annullati.

---

## 7. Market Reversal Filter BTC

Il filtro inversione BTC e' condiviso con lo Spot:

- timeframe: BTCUSDT 15m;
- EMA: 10;
- conferme: 2 candele;
- stato persistito: `neutral`, `bullish`, `bearish`.

Nel Perp:

- se BTC e' bullish/risk-on, gli short vengono bloccati con `market_reversal_short_blocked`;
- se BTC e' bearish/risk-off, i long vengono bloccati con `market_reversal_long_blocked`.

Il filtro e' simmetrico e non sblocca mai altri guardrail.

---

## 8. Qualita' Del Segnale

Il quality score combina:

| Componente | Peso interno | Descrizione |
|---|---:|---|
| Map score | 35% | distanza dal POC |
| Trend score | 25% | coerenza con VWAP |
| ATR score | 15% | presenza ATR valido |
| Value edge | 25% | posizione relativa rispetto al POC |

Il segnale diventa operativo solo se:

```text
side != null
quality >= 0.6
```

Altrimenti viene restituito `skip`.

---

## 9. Stop Loss V4

Il Perp supporta due modalita' di stop loss.

### Modalita' ATR

Default:

```text
long:  stop_loss = entry - ATR * perp_atr_stop_multiplier
short: stop_loss = entry + ATR * perp_atr_stop_multiplier
```

Default `perp_atr_stop_multiplier = 0.8`.

Se ATR non e' disponibile:

- long: fallback a `previous.low`;
- short: fallback a `previous.high`.

### Modalita' Lowest/Highest 20

Quando `perp_sl_mode = lowest`, il nome e' legacy ma la logica e' strutturale:

```text
long:
  reference = minimo low nelle ultime N candele
  stop_loss = reference * (1 - buffer_pct / 100)

short:
  reference = massimo high nelle ultime N candele
  stop_loss = reference * (1 + buffer_pct / 100)
```

Default:

| Parametro | Default |
|---|---:|
| `perp_structural_stop_lookback_candles` | 20 |
| `perp_structural_stop_buffer_pct` | 1.10 |

Il segnale salva `stop_reference` con:

- modalita';
- campo (`low` o `high`);
- timestamp candela;
- prezzo riferimento;
- lookback;
- buffer.

Questo alimenta risk levels e grafico dettaglio trade.

---

## 10. Take Profit

I target principali sono ATR-based.

### Long

```text
TP1 = entry + ATR * perp_tp1_atr_multiplier
TP2_ATR = entry + ATR * perp_tp2_atr_multiplier
TP2 = POC se POC > TP2_ATR e use_poc_for_tp2, altrimenti TP2_ATR
```

### Short

```text
TP1 = entry - ATR * perp_tp1_atr_multiplier
TP2_ATR = entry - ATR * perp_tp2_atr_multiplier
TP2 = POC se POC < TP2_ATR e use_poc_for_tp2, altrimenti TP2_ATR
```

Default:

| Parametro | Default |
|---|---:|
| `perp_tp1_atr_multiplier` | 2.5 |
| `perp_tp2_atr_multiplier` | 4.0 |
| `perp_use_poc_for_tp2` | true |

Se ATR non e' disponibile:

- long: TP1 = VAL, TP2 = POC;
- short: TP1 = VAH, TP2 = POC.

---

## 11. Chiusura Parziale E Sequenza Uscite

Al raggiungimento di TP1:

- chiusura parziale;
- default mobile `perp_tp1_close_pct = 70%`;
- `tp1_reached = true`;
- fee/funding residui vengono scalati sulla posizione restante.

Dopo TP1:

- TP2 diventa uscita finale;
- breakeven e trailing possono continuare a proteggere il residuo.

Priorita' uscite nel fast loop:

1. trailing se piu' protettivo dello stop;
2. stop loss o breakeven;
3. TP2 dopo TP1;
4. TP1 parziale;
5. time stop.

Le chiusure per SL/TP/trailing usano il livello specifico di uscita, non il mark corrente generico.

---

## 12. Breakeven

Breakeven Perp:

- default: attivo;
- trigger default: `1.0 * ATR` a favore dell'entry;
- modalita': `atr` oppure `tp1`;
- se `tp1`, il BE puo' scattare solo dopo TP1;
- con `perp_breakeven_offset_costs = true`, lo stop copre fee andata/ritorno;
- con `perp_breakeven_buffer_pct = 0.1`, se il prezzo lo permette, aggiunge buffer extra:
  - long: entry + 0.1%;
  - short: entry - 0.1%.

Lo stop si muove solo verso il sicuro:

- long: solo verso l'alto;
- short: solo verso il basso.

---

## 13. Trailing Dinamico

Il trailing Perp e' gestito dal service, non seminato dal segnale.

Input:

- ATR congelato all'ingresso;
- estremo favorevole dalla posizione:
  - long: massimo raggiunto;
  - short: minimo raggiunto;
- leva del trade;
- modalita' trailing `largo` o `stretto`.

Il moltiplicatore ATR viene interpolato sulla leva:

```text
leva minima -> moltiplicatore base
leva massima -> moltiplicatore floor
```

Default:

| Modalita' | Base | Floor |
|---|---:|---:|
| Largo | 4.0 ATR | 2.5 ATR |
| Stretto | 2.5 ATR | 1.5 ATR |

Il moltiplicatore viene cappato a `perp_tp1_atr_multiplier`, cosi' il trailing non si attiva dopo TP1.

Formula:

```text
long:  trailing_atr = max_price - ATR * multiplier
short: trailing_atr = min_price + ATR * multiplier
```

Opzionale:

- `perp_trailing_pnl_pct > 0` aggiunge anche un trailing percentuale dall'estremo favorevole;
- vince il livello piu' protettivo.

Il trailing si attiva solo se e' gia' in profitto rispetto all'entry.

---

## 14. Leva Dinamica ATR

La leva viene calcolata in apertura confrontando ATR corrente con una baseline storica:

- ATR periodo: 72 candele;
- baseline default: 120 ore;
- limite fetch: max 1500 candele;
- bassa volatilita' -> leva massima;
- alta volatilita' -> leva minima;
- ATR oltre massimo storico -> leva minima;
- dati insufficienti -> leva minima.

Default mobile/config:

| Parametro | Default |
|---|---:|
| `perp_min_leverage` | 4 |
| `perp_max_leverage` | 40 |
| `perp_leverage_atr_period` | 72 |
| `perp_leverage_atr_baseline_hours` | 120 |

Il segnale calcola una leva preliminare, ma `AgentService.evaluate_perp` la sovrascrive con i mobile settings correnti.

---

## 15. Margine, Size E Fixed Margin

Nel Perp, il risk manager tratta `size_quote` come margine impegnato.

Sizing dinamico:

```text
nominal_size = equity * perp_capital_per_trade_pct / 100
risk_amount = equity * perp_per_trade_pct / 100
risk_size = min(nominal_size, risk_amount / stop_distance_pct)
```

Se `perp_fixed_margin_enabled = true`:

```text
risk_size = perp_fixed_margin_usd
```

In questo caso:

- il margine e' fisso;
- `size_factor` del segnale non riduce il margine;
- il moltiplicatore size del brain non riduce il margine;
- il notional reale e' `margin * leverage`.

Default mobile:

| Parametro | Default |
|---|---:|
| `perp_capital_per_trade_pct` | 4.0 |
| `perp_per_trade_pct` | 1.5 |
| `perp_max_open_positions` | 5 |
| `perp_max_exposure_pct` | 20.0 |
| `perp_cooldown_minutes` | 15 |
| `perp_max_slippage_pct` | 0.5 |
| `perp_fixed_margin_enabled` | false |
| `perp_fixed_margin_usd` | 50.0 |

---

## 16. Risk Management Perp

Il risk manager e' comune a Spot e Perp, ma usa limiti separati quando arrivano i mobile settings.

Guardrail:

- kill switch hard/soft/degraded;
- eligible universe;
- portfolio floor;
- drawdown cap;
- daily loss limit;
- liquidita' minima;
- dedup per asset;
- max posizioni Perp;
- max esposizione Perp;
- cooldown;
- min trade size.

Esposizione Perp:

```text
exposure = entry_price * size / leverage
```

Quindi nelle viste Global la exposure Perp rappresenta il margine impegnato, non il nozionale.

Nel dettaglio trade, invece, `exposure_usd` rappresenta il nozionale controllato e `margin_usd` e' separato.

---

## 17. Costi, Funding E Liquidazione

In dry-run Perp:

- fetch fee/funding da PancakeSwap Perps v2, con fallback se offline;
- calcolo taker fee, maker fee, slippage e funding rate;
- se `perp_fee_mode = taker`, lo slippage peggiora l'entry:
  - long: entry piu' alta;
  - short: entry piu' bassa;
- funding accrued viene aggiornato nel fast loop;
- PnL unrealized sottrae fee pure e aggiunge funding accrued;
- liquidation price viene stimato da entry e leva.

In live:

- il provider attivo Perp riceve `PerpOrder`;
- se il provider non e' pronto, deve fallire chiuso.

---

## 18. Time Stop

Il Perp usa un time stop orario opzionale, disattivato di default da app/dashboard:

| Parametro | Default |
|---|---:|
| `perp_time_stop_enabled` | false |
| `perp_time_stop_hours` | 8 |

Se `perp_time_stop_enabled = true` e la posizione resta aperta oltre la soglia, viene chiusa con `time_stop`, salvo che prima scattino trailing, stop o target.

---

## 19. Meta-Controller AI

L'AI riceve segnale e risk decision.

Azioni ammesse:

- `approve`;
- `reduce`;
- `block`;
- `skip`.

Vincoli hard nel prompt:

- non aumenta leva;
- non inverte direzione;
- non cambia parametri strategici;
- restituisce JSON strict.

In fallback locale dry-run:

- quality >= 0.85 -> approve;
- quality >= 0.65 -> reduce size 50%;
- sotto soglia -> skip.

Se Claude non e' disponibile, il sistema marca degraded e blocca nuove entrate.

---

## 20. Osservabilita'

Le viste app/dashboard espongono:

- posizioni long/short;
- leva;
- margine;
- nozionale nel dettaglio;
- liquidation price;
- funding rate;
- funding accrued;
- fee taker/maker;
- slippage;
- SL/TP/trailing;
- stop reference price e field;
- grafico trade con candela di riferimento e linea `SL ref` che non copre la candela.

---

## 21. Stato V4 E Debiti Futuri

Implementato:

- Volume Profile 24h su 5m futures;
- rientro in value long/short;
- filtro VWAP;
- filtro BTC inversione simmetrico;
- stop ATR o Lowest/Highest20;
- TP ATR con POC opzionale;
- breakeven e trailing dinamico su leva;
- leva dinamica ATR con baseline storica;
- margine fisso opzionale;
- risk separato Perp;
- funding/fee/slippage dry-run;
- dettaglio trade con livelli e grafico.

Debiti futuri:

- delta reale da Binance aggregate trades futures;
- HVN/LVN espliciti;
- profili multipli;
- filtro funding/OI piu' strutturato;
- backtest dei parametri V4;
- integrazione live completa su venue Perp definitiva.

---

## 22. Storico Versioni

| Versione | Sintesi |
|---|---|
| V1 | Volume Profile mean reversion iniziale. |
| V2 | Gerarchia segnali, VWAP per trend, conferme price action. |
| V3 | Stop strutturale, cap rischio, TP parziale e breakeven. |
| V4 | Allineamento al codice corrente: stop ATR/Lowest20, filtro BTC simmetrico, leva ATR 4x-40x, trailing dinamico su leva, fixed margin opzionale e osservabilita' completa. |

---

*Fine documento Perpetual V4.*
