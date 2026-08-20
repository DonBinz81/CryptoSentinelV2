/**
 * Nome campo (snake_case, quello che manda il backend in un 422) -> etichetta
 * italiana mostrata nel pannello Setup. Estratta dai NumberInput di AgentTab: se
 * in futuro se ne aggiunge uno nuovo con un vincolo min/max, aggiungere la coppia
 * qui, altrimenti l'errore di salvataggio mostrera' il nome tecnico invece
 * dell'etichetta — non e' un errore, solo un messaggio meno chiaro.
 */
export const ETICHETTA_CAMPO: Record<string, string> = {
  test_scaling_pct: 'Test scaling %',
  min_pool_liquidity_usd: 'Liquidità minima $',
  daily_loss_limit_pct: 'Daily loss %',
  drawdown_cap_pct: 'Drawdown cap %',
  post_close_candles: 'Candele post-chiusura (0=off)',
  chart_pre_open_candles: "Candele prima dell'apertura",
  spot_capital_per_trade_pct: 'Size % (Spot)',
  spot_per_trade_pct: 'Rischio % (Spot)',
  spot_max_open_positions: 'Max posizioni (Spot)',
  spot_max_exposure_pct: 'Exposure % (Spot)',
  spot_max_slippage_pct: 'Slippage % (Spot)',
  spot_cooldown_minutes: 'Cooldown min (Spot)',
  spot_confidence_threshold: 'Confidence',
  spot_volatility_trigger_pct: 'Vol trigger %',
  spot_relative_volume_threshold: 'Rel volume',
  spot_atr_stop_multiplier: 'ATR stop (Spot)',
  spot_structural_stop_buffer_pct: 'Buffer Min20 %',
  spot_structural_stop_lookback_candles: 'N° candele per calcolo stop (Spot)',
  spot_tp1_close_pct: 'Chiudi a TP1 % (Spot)',
  spot_time_stop_hours: 'Time Stop ore (Spot)',
  perp_capital_per_trade_pct: 'Size % (margine)',
  perp_per_trade_pct: 'Rischio % (Perp)',
  perp_max_open_positions: 'Max posizioni (Perp)',
  perp_max_exposure_pct: 'Exposure % (Perp)',
  perp_max_slippage_pct: 'Slippage % (Perp)',
  perp_cooldown_minutes: 'Cooldown min (Perp)',
  perp_fixed_margin_usd: 'Margine fisso $',
  perp_min_leverage: 'Leva min (alta vol.)',
  perp_max_leverage: 'Leva max (bassa vol.)',
  perp_value_area_pct: 'Value area %',
  perp_atr_stop_multiplier: 'ATR stop (Perp)',
  perp_structural_stop_buffer_pct: 'Buffer Min/Max20 %',
  perp_structural_stop_lookback_candles: 'N° candele per calcolo stop (Perp)',
  perp_min_rr: 'Filtro R:R min (0=off)',
  perp_tp1_atr_multiplier: 'TP1 (× ATR)',
  perp_tp2_atr_multiplier: 'TP2 (× ATR)',
  perp_trailing_pnl_pct: 'Trailing dist. % (0=solo ATR)',
  perp_tp1_close_pct: 'Chiudi a TP1 % (Perp)',
  perp_time_stop_hours: 'Time Stop ore (Perp)',
  perp_trend_shock_adx_threshold: 'ADX threshold',
  perp_trend_shock_natr_percentile: 'NATR percentile',
  perp_trend_shock_volume_threshold: 'Volume threshold',
  perp_trend_shock_recovery_confirmations: 'Recovery checks',
  perp_smart_sl_l1_frac: 'L1 frac',
  perp_smart_sl_l2_frac: 'L2 frac',
  perp_smart_sl_split_l1: 'Split L1 %',
  perp_smart_sl_split_l2: 'Split L2 %',
  perp_smart_sl_split_l3: 'Split L3 %',
  perp_smart_sl_confirmation_candles: 'Candele conferma SSL',
  perp_smart_sl_max_reentries: 'Max reentries',
  perp_smart_sl_rebuy_above_entry_pct: 'Rebuy % venduto',
  perp_smart_sl_split_l1_r2: 'R2 Split L1 %',
  perp_smart_sl_split_l2_r2: 'R2 Split L2 %',
  perp_smart_sl_split_l3_r2: 'R2 Split L3 %',
  perp_smart_sl_delta_l1: 'Delta L1',
  perp_smart_sl_delta_l2: 'Delta L2',
  perp_smart_sl_tp_recovery_delta_pct: 'Delta recovery TP %',
  perp_ratchet_breakeven_pct: 'Breakeven ratchet (% del tratto)',
  perp_ratchet_breakeven_after_step: 'Si arma dallo scalino n.',
  perp_ratchet_trailing_pct: 'Trailing oltre TP2 (% dal massimo)',
};

/**
 * "post_close_candles: Input should be less than or equal to 288" ->
 * "Candele post-chiusura (0=off): deve essere ≤ 288" — il messaggio del backend
 * arriva gia' col nome del campo grazie a describeError() in http.ts, ma quel
 * nome e' lo snake_case del backend, non l'etichetta che l'utente vede in Setup.
 * Un campo non in ETICHETTA_CAMPO resta col nome tecnico invece di sparire: e'
 * comunque un'informazione, solo meno chiara.
 */
export const traduciErroreSalvataggio = (msg: string): string =>
  msg.replace(/\b([a-z][a-z0-9_]*)(?=:)/g, (match) => ETICHETTA_CAMPO[match] ?? match);
