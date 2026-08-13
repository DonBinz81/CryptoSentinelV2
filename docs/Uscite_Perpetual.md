# Strategia di Uscita - PERPETUAL

> Come l'agente chiude le posizioni perp in profitto e in perdita.
> Riferimento codice: `backend/app/agent/service.py`, `backend/app/agent/signals/perp/volume_profile.py` e `backend/app/execution/perp_fees.py`.
> Parametri attivi: `configs/strategy_perp.yaml`.

Il perp supporta long e short con leva. Il comportamento corrente combina Volume Profile come mappa operativa e livelli ATR per controllare rischio, target e trailing.

## 1. Livelli fissati all'apertura

| Livello | LONG | SHORT | Default |
|---|---|---|---:|
| Stop Loss | `entry - ATR * atr_stop_multiplier` oppure minimo ultime 20 candele con buffer | `entry + ATR * atr_stop_multiplier` oppure massimo ultime 20 candele con buffer | `0.8 ATR` oppure `1.10%` oltre Min/Max20 |
| TP1 | `entry + ATR * tp1_atr_multiplier` | `entry - ATR * tp1_atr_multiplier` | `2.5 ATR` |
| TP2 | target ATR o POC se piu' ambizioso | target ATR o POC se piu' ambizioso | `4.0 ATR` |
| Liquidazione stimata | `entry * (1 - 1 / leva)` | `entry * (1 + 1 / leva)` | informativa |
| Breakeven | `entry + costi + buffer` | `entry - costi - buffer` | trigger `1.0 ATR`, buffer `0.1%` |
| Trailing | estremo favorevole `- ATR * mult` | estremo favorevole `+ ATR * mult` | dinamico sulla leva |

Se `use_poc_for_tp2` e' attivo, TP2 usa il POC quando e' piu' ambizioso del target ATR: sopra il target ATR per long, sotto il target ATR per short.

La modalita' stop loss e' selezionabile dal setup mobile:

| Modalita' | LONG | SHORT |
|---|---|---|
| `perp_sl_mode: atr` | `entry - ATR(14) * perp_atr_stop_multiplier` | `entry + ATR(14) * perp_atr_stop_multiplier` |
| `perp_sl_mode: lowest` | `minimo ultime 20 candele * (1 - structural_stop_buffer_pct / 100)` | `massimo ultime 20 candele * (1 + structural_stop_buffer_pct / 100)` |

Default strutturale: `structural_stop_lookback_candles: 20`, `structural_stop_buffer_pct: 1.10`.

La liquidazione stimata viene salvata sulla posizione Perp, esposta nel dettaglio trade e disegnata come livello sul grafico. Non e' un trigger di chiusura gestito dall'agente: serve a capire quanto margine c'e' tra stop loss operativo e rischio di liquidazione.

## 2. Fee, funding e margine

Le fee perp vengono lette da PancakeSwap Perpetuals v2 quando disponibile, con fallback a costanti:

| Voce | Default/fallback |
|---|---:|
| Taker open | `0.06%` |
| Taker close | `0.06%` |
| Maker open | `0.02%` |
| Maker close | `0.02%` |
| Funding | live per asset, fallback `0` |

Il modello salva `fee_mode`, fee taker/maker, slippage, funding rate, funding maturato e `margin_usd`. Nelle viste globali l'esposizione perp e' trattata come margine impegnato, non come nozionale.

## 3. Ordine di controllo

Ad ogni aggiornamento prezzo l'agente controlla:

1. Trailing stop, se piu' protettivo dello stop loss.
2. Stop loss.
3. TP2, solo dopo TP1.
4. TP1, solo la prima volta.
5. Time stop.

Il riempimento dry-run usa il livello trigger (`stop_loss`, `trailing_stop`, `take_profit_1`, `take_profit_2`) invece del prezzo corrente generico.

## 4. Breakeven e trailing

Il breakeven scatta a favore di `1.0 ATR`. Lo stop viene spostato a entry piu' costi round-trip stimati; se il prezzo ha gia' superato il buffer, aggiunge anche `0.1%`.

Il trailing e' attivo da subito ma viene popolato solo quando e' piu' protettivo dello stop. Il moltiplicatore ATR dipende dalla leva:

| Modalita' | Leva minima | Leva massima |
|---|---:|---:|
| `largo` | `4.0 ATR` | `2.5 ATR` |
| `stretto` | `2.5 ATR` | `1.5 ATR` |

Il moltiplicatore viene comunque cappato a TP1 per evitare che il trailing si attivi solo oltre il primo target.

## 5. Uscite in profitto

TP1 chiude il 50% della posizione. La parte restante rimane aperta con `tp1_reached = true`.

Dopo TP1, TP2 chiude il residuo. In alternativa, il trailing puo' chiudere il residuo se il prezzo ritraccia oltre il livello dinamico.

Per i long il PnL e' `exit - entry`; per gli short e' `entry - exit`. Le fee pure e il funding maturato vengono ripartiti sulla chiusura parziale e applicati integralmente sulla chiusura finale.

## 6. Uscite in perdita

Lo stop loss chiude la posizione quando il prezzo invalida il trade. Il breakeven puo' trasformare lo stop in uscita neutra/leggermente positiva dopo un movimento iniziale favorevole.

Non e' prevista media in perdita. La leva dinamica, la liquidazione stimata e i controlli di rischio restano guardrail/informazioni separati dall'uscita.

## 7. Time stop

Il time stop perp resta orario ma e' opzionale e disattivato di default: con `time_stop_enabled: true` e `time_stop_hours: 8`, una posizione aperta oltre 8 ore viene chiusa se non ha gia' toccato SL, trailing o target. Serve a limitare esposizione con leva e funding.

## 8. Motivi di chiusura

| Motivo | LONG | SHORT | Quota |
|---|---|---|---|
| `take_profit_1` | prezzo >= TP1 | prezzo <= TP1 | 50% |
| `take_profit_2` | prezzo >= TP2 dopo TP1 | prezzo <= TP2 dopo TP1 | residuo |
| `trailing_stop` | prezzo <= trailing protettivo | prezzo >= trailing protettivo | residuo o posizione intera |
| `stop_loss` | prezzo <= SL/breakeven | prezzo >= SL/breakeven | posizione residua/intera |
| `time_stop` | eta' >= 8h | eta' >= 8h | posizione residua/intera |

## 9. Parametri principali

| Parametro | Valore attuale |
|---|---:|
| `atr_stop_multiplier` | `0.8` |
| `tp1_atr_multiplier` | `2.5` |
| `tp2_atr_multiplier` | `4.0` |
| `use_poc_for_tp2` | `true` |
| `breakeven_trigger_atr` | `1.0` |
| `breakeven_buffer_pct` | `0.1` |
| `trailing_mode` | `largo` |
| `time_stop_enabled` | `false` |
| `time_stop_hours` | `8` |
| `default_leverage` | `2` |
| `min_leverage` / `max_leverage` | `4` / `40` |
