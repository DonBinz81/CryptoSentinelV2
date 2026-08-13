# Strategia di Uscita - SPOT

> Come l'agente chiude le posizioni spot in profitto e in perdita.
> Riferimento codice: `backend/app/agent/service.py` e `backend/app/agent/signals/spot/momentum.py`.
> Parametri attivi: `configs/strategy_spot.yaml`.

Lo spot e' solo long: l'agente compra e poi rivende. Il comportamento corrente non usa piu' target percentuali fissi: stop, take profit e trailing sono ancorati all'ATR congelato all'ingresso.

## 1. Livelli fissati all'apertura

| Livello | Formula corrente | Default | Uso |
|---|---|---:|---|
| Stop Loss | `entry - ATR * atr_stop_multiplier` oppure minimo ultime 20 candele con buffer se `spot_sl_mode=lowest` | `2.2 ATR` oppure `1.10%` sotto minimo20 | uscita in perdita |
| Take Profit 1 | `entry + ATR * tp1_atr_multiplier` | `2.0 ATR` | chiusura parziale |
| Take Profit 2 | `entry + ATR * tp2_atr_multiplier` | `3.5 ATR` | chiusura finale dopo TP1 |
| Breakeven | `entry + costi round-trip + buffer` | trigger `0.6 ATR`, buffer `0.1%` | protezione trade in profitto |
| Trailing | `max_price - ATR * trailing_multiplier` | `2.5 ATR`, cappato a TP1 | segue il massimo favorevole |

I costi dry-run spot sono stimati in `backend/app/execution/spot_fees.py`: swap fee PancakeSwap V3 e slippage simulato. Se `breakeven_offset_costs` e' attivo, lo stop a breakeven copre anche fee/slippage di apertura e chiusura.

La modalita' stop loss e' selezionabile dal setup mobile:

| Modalita' | Regola |
|---|---|
| `spot_sl_mode: atr` | `entry - ATR(14) * spot_atr_stop_multiplier` |
| `spot_sl_mode: lowest` | `minimo ultime 20 candele * (1 - structural_stop_buffer_pct / 100)` |

Default strutturale: `structural_stop_lookback_candles: 20`, `structural_stop_buffer_pct: 1.10`.

## 2. Ordine di controllo

Ad ogni aggiornamento prezzo l'agente controlla:

1. Trailing stop, se piu' protettivo dello stop loss.
2. Stop loss.
3. TP2, solo se TP1 e' gia' stato preso.
4. TP1, solo la prima volta.
5. Time stop.

Il prezzo di chiusura simulato usa il livello che ha scatenato l'uscita, non genericamente il prezzo corrente.

## 3. Uscite in profitto

TP1 chiude solo la quota configurata da `tp1_close_fraction`, oggi `0.30`: il 30% della posizione viene venduto e il 70% resta aperto. Il flag `tp1_reached` abilita TP2 come uscita finale sul residuo.

Il trailing ATR e' attivo da subito (`trailing_active_from_start: true`) e si alza soltanto. Il moltiplicatore viene cappato al moltiplicatore di TP1, cosi' il trailing non si attiva troppo tardi.

Il breakeven scatta quando il prezzo supera `entry + 0.6 ATR`. Lo stop viene alzato almeno a entry, piu' costi round-trip se configurati, e puo' aggiungere un buffer extra dello `0.1%` solo se il prezzo lo ha gia' superato.

## 4. Uscite in perdita

Lo stop loss ha priorita' alta, ma se il trailing e' piu' protettivo viene controllato prima. Non esiste media in perdita.

Lo spot puo' aggiungere size solo a favore: `scale_in_enabled` permette al massimo una aggiunta (`scale_in_max_adds: 1`) se la posizione e' in profitto, lo stop e' gia' a breakeven e c'e' un nuovo higher high. L'aggiunta rispetta il cap nominale per trade.

## 5. Time stop

Il time stop corrente e' opzionale e disattivato di default. Quando `time_stop_enabled` e' attivo, la modalita' primaria e' ATR-aware:

| Modalita' | Regola |
|---|---|
| `time_stop_mode: atr` | dopo `time_stop_lookback_candles` da 5m, chiude solo se il movimento e' inferiore a `time_stop_min_move_atr * ATR` |
| fallback orario | se `time_stop_mode: hours`, chiude oltre `time_stop_hours_fallback` |

Con il toggle attivo, la modalita' primaria e' `atr`: il trade viene chiuso solo se e' davvero fermo rispetto alla sua volatilita'.

## 6. Motivi di chiusura

| Motivo | Quando | Quota |
|---|---|---|
| `take_profit_1` | prezzo >= TP1 | 30% default |
| `take_profit_2` | prezzo >= TP2 dopo TP1 | residuo |
| `trailing_stop` | prezzo ritraccia sotto trailing protettivo | residuo o posizione intera |
| `stop_loss` | prezzo <= stop loss/breakeven | posizione residua/intera |
| `time_stop_atr` | movimento insufficiente su finestra ATR | posizione residua/intera |
| `time_stop` | fallback orario | posizione residua/intera |

## 7. Parametri principali

| Parametro | Valore attuale |
|---|---:|
| `atr_stop_multiplier` | `2.2` |
| `tp1_atr_multiplier` | `2.0` |
| `tp2_atr_multiplier` | `3.5` |
| `tp1_close_fraction` | `0.30` |
| `breakeven_trigger_atr` | `0.6` |
| `breakeven_buffer_pct` | `0.1` |
| `trailing_atr_multiplier` | `2.5` |
| `scale_in_max_adds` | `1` |
| `time_stop_enabled` | `false` |
| `time_stop_mode` | `atr` |
| `time_stop_lookback_candles` | `8` |
| `time_stop_min_move_atr` | `0.5` |
