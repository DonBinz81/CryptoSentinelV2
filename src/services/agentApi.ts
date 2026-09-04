import { Capacitor, CapacitorHttp } from '@capacitor/core';
import { BackendHttpError, backendRequest, requireBackend, authHeaders } from './http';

export type KillSwitchState = 'running' | 'soft_stop' | 'hard_stop' | 'degraded';

/** Stato del guardiano di regime: verde normale, giallo prudenza, rosso stop alle aperture. */
export type GuardianState = 'green' | 'yellow' | 'red';

export interface GuardianStatus {
  state: GuardianState;
  enabled: boolean;
  stops_in_window: number;
  window_hours: number;
  /** Ore pulite (senza nuovo stop pieno) per un passo di de-escalation: RED->YELLOW,
   * poi YELLOW->GREEN separatamente. L'ancora si sposta a ogni nuovo stop (NOTE/95). */
  reentry_hours: number;
  last_stop_at: string | null;
  changed_at: string | null;
  /** Spiegazione del Brain sull'ultima transizione. null quando non disponibile. */
  explanation: string | null;
  explained_at: string | null;
  /** Livello calcolato dal motore, MAI toccato dall'override manuale. */
  automatic_level?: GuardianState;
  /** Livello con cui il motore sta davvero operando. `state` mappa qui sopra. */
  effective_level?: GuardianState;
  /** Forzatura admin attiva, oppure null quando si segue l'automatico. */
  manual_override?: { level: GuardianState; at: string } | null;
}

/**
 * Salute del sistema. Ogni campo e' opzionale e puo' essere null: un valore che
 * il backend non sa calcolare va mostrato come "non disponibile", MAI come uno
 * zero o un 100% — un pannello che rassicura sempre e' peggio di nessun pannello.
 */
export interface OperationalStats {
  disk?: {
    used_pct: number;
    free_bytes: number;
    total_bytes: number;
    path?: string;
    /** Soglie che fanno scattare l'ALLARME (risk.yaml). Il pannello usa queste e non
     *  le proprie: se divergessero, l'app direbbe "verde" mentre la notifica suona. */
    warn_pct?: number;
    critical_pct?: number;
  } | null;
  db_size_bytes?: number | null;
  degraded_reasons?: string[] | null;
  heartbeat?: Record<string, string | number | null> | null;
  /** Ultimo backup: e' il guasto che altrimenti si vede solo via Telegram — e se
   *  il canale stesso e' rotto, non lo si vede affatto. */
  last_backup?: {
    status?: string | null;
    integrity?: string | null;
    timestamp_utc?: string | null;
    age_seconds?: number | null;
  } | null;
}

export function fetchOperationalStats(): Promise<OperationalStats> {
  return request<OperationalStats>('/api/v1/views/operational-stats');
}

/** "auto" non forza il verde: rimuove l'override e torna a seguire l'automatico. */
export type GuardianOverrideChoice = GuardianState | 'auto';

export interface GuardianOverrideResponse {
  status: string;
  action: 'set' | 'cleared';
  automatic_level: GuardianState;
  effective_level: GuardianState;
  manual_override: GuardianState | null;
  note: string;
}

export function setGuardianOverride(
  level: GuardianOverrideChoice,
  note: string,
  adminToken: string,
): Promise<GuardianOverrideResponse> {
  return request<GuardianOverrideResponse>('/api/v1/agent/guardian/override', {
    method: 'POST',
    body: { level, note },
    token: adminToken,
  });
}

/** Esito dell'ultimo ciclo di scansione per un mercato: quanti asset in ognuna delle
 * cinque uscite possibili. scanned = entered + no_edge + filter + error + other. */
export interface ScannerMarketStatus {
  scanned: number;
  entered: number;
  no_edge: number;
  filter: number;
  error: number;
  other: number;
  /** Codice del motore -> quanti asset. Solo per le uscite diverse da "entered". */
  reasons: Record<string, number>;
}

export interface ScannerStatusResponse {
  /** false quando il backend non ha ancora registrato nessun ciclo (es. appena riavviato). */
  available: boolean;
  timestamp_utc: string | null;
  age_seconds: number | null;
  /** true = il ciclo non gira piu' da un pezzo: e' un problema, non "nessun segnale". */
  stale: boolean;
  markets: {
    spot: ScannerMarketStatus | null;
    perp: ScannerMarketStatus | null;
  };
}

export interface AgentStatus {
  mode: string;
  markets_enabled: string;
  execution_mode: string;
  kill_switch: KillSwitchState;
  fast_loop_last_tick: string | null;
  slow_loop_last_tick: string | null;
  guardian?: GuardianStatus | null;
}

export interface EligibleTokensResponse {
  count: number;
  tokens: string[];
}

export interface AgentWatchlistResponse {
  eligible_count: number;
  eligible_tokens: string[];
  selected_count: number;
  selected_tokens: string[];
  ranking?: WatchlistRanking;
}

export interface SymbolRanking {
  /** Global CoinMarketCap rank (BTC is 1). Null when the provider has no figure. */
  rank: number | null;
  market_cap: number | null;
}

/** Ranking per symbol, keyed by symbol. Display only: it never reorders the stored watchlist. */
export type WatchlistRanking = Record<string, SymbolRanking>;

export type VenueAvailabilityStatus = 'available' | 'unavailable' | 'unknown';

export interface VenueAvailability {
  venue: string;
  status: VenueAvailabilityStatus;
  reason?: string;
}

/** Per-symbol availability, keyed by symbol. Absent when the backend could not compute it. */
export type WatchlistAvailability = Record<string, { spot: VenueAvailability; perp: VenueAvailability }>;

export interface AgentMarketWatchlistResponse {
  master_tokens: string[];
  selected_tokens: string[];
  selected_count: number;
  availability?: WatchlistAvailability;
  ranking?: WatchlistRanking;
}

export interface SpotPositionView {
  position_id: string;
  open_trade_id?: string | null;
  asset: string;
  size: string;
  entry_price: string;
  current_price: string;
  pnl_unrealized: string;
  pnl_pct?: string | null;
  stop_loss?: string | null;
  take_profit_1?: string | null;
  take_profit_2?: string | null;
  fee_mode?: string | null;
  swap_fee_usd?: string | null;
  slippage_usd?: string | null;
  status: string;
  opened_at: string;
}

export interface SpotTradeView {
  trade_id: string;
  asset: string;
  side: string;
  amount: string;
  price: string;
  pnl_usd?: string | null;
  pnl_pct?: string | null;
  entry_price?: string | null;
  current_or_exit_price?: string | null;
  status: string;
  close_reason?: string | null;
  tx_hash?: string | null;
  timestamp_utc: string;
}

export interface SpotView {
  open_positions: SpotPositionView[];
  history: SpotTradeView[];
  realized_pnl_usd: string;
  unrealized_pnl_usd: string;
  win_rate_pct: number;
  trade_count: number;
  trade_count_today: number;
  bot_active_days: number;
  market_risk_off?: boolean;
  /** Volume SCAMBIATO, tutte le gambe incluse. Sul perp e' il NOZIONALE,
   *  non il capitale impegnato: con la leva le cifre sono molto maggiori. */
  volume_total_usd?: string;
  volume_today_usd?: string;
}

export interface PerpPositionView {
  position_id: string;
  open_trade_id?: string | null;
  asset: string;
  side: string;
  size: string;
  entry_price: string;
  current_price: string;
  leverage: number;
  pnl_unrealized: string;
  pnl_pct?: string | null;
  stop_loss?: string | null;
  take_profit_1?: string | null;
  take_profit_2?: string | null;
  liquidation_price?: string | null;
  funding_rate?: string | null;
  fee_mode?: string | null;
  margin_usd?: string | null;
  opening_fee_usd?: string | null;
  taker_fee_usd?: string | null;
  maker_fee_usd?: string | null;
  slippage_usd?: string | null;
  funding_accrued_usd?: string | null;
  smart_sl_active?: boolean;
  smart_sl_levels_sold?: boolean[] | null;
  status: string;
  opened_at: string;
  /** Chiusure manuali confermate ancora riflesse sulla posizione aperta. 0 se mai toccata a mano. */
  manual_close_count?: number;
  /** % della size di apertura chiusa a mano. null se manual_close_count è 0, o non calcolabile. */
  manual_reduced_pct?: string | null;
}

export interface PerpTradeView {
  trade_id: string;
  position_id?: string | null;
  asset: string;
  side: string;
  direction: string;
  size: string;
  price: string;
  pnl_usd?: string | null;
  pnl_pct?: string | null;
  entry_price?: string | null;
  current_or_exit_price?: string | null;
  leverage: number;
  status: string;
  close_reason?: string | null;
  /** % della size di apertura tolta da QUESTA chiusura manuale (evento singolo,
   *  non cumulativo). null sulle righe non manuali e se non calcolabile. */
  manual_close_pct?: string | null;
  tx_hash?: string | null;
  timestamp_utc: string;
}

export interface PerpView {
  open_positions: PerpPositionView[];
  history: PerpTradeView[];
  realized_pnl_usd: string;
  unrealized_pnl_usd: string;
  win_rate_pct: number;
  trade_count: number;
  trade_count_today: number;
  bot_active_days: number;
  /** Volume SCAMBIATO, tutte le gambe incluse. Sul perp e' il NOZIONALE,
   *  non il capitale impegnato: con la leva le cifre sono molto maggiori. */
  volume_total_usd?: string;
  volume_today_usd?: string;
}

export interface PnlPoint {
  timestamp_utc: string;
  total_equity_usd: string;
  drawdown_pct: string;
}

export interface GlobalView {
  total_equity_usd: string;
  initial_equity_usd: string;
  pnl_total_usd: string;
  pnl_total_pct: number;
  realized_pnl_usd: string;
  unrealized_pnl_usd: string;
  drawdown_pct: string;
  max_drawdown_pct: string;
  drawdown_cap_pct: number;
  exposure_pct: string;
  daily_pnl_usd: string;
  agent_status: string;
  trades_today: number;
  open_spot_positions: number;
  open_perp_positions: number;
  total_fees_usd: string;
  /** Volume SCAMBIATO, tutte le gambe incluse. Sul perp e' il NOZIONALE,
   *  non il capitale impegnato: con la leva le cifre sono molto maggiori. */
  volume_total_usd?: string;
  volume_today_usd?: string;
  daily_pnl_net_pct: number;
  pnl_total_net_pct: number;
  risk_guardrail?: {
    blocked: boolean;
    reason?: string | null;
    title: string;
    detail: string;
    drawdown_pct: string;
    drawdown_cap_pct: number;
    daily_loss_used_pct: string;
    daily_loss_limit_pct: number;
    min_portfolio_value_usd: number;
    /** Quante volte il conteggio giornaliero e' stato azzerato oggi (NOTE/63). */
    daily_counter_resets_today?: number;
    daily_counter_reset_at?: string | null;
    /** Quante volte il picco del drawdown e' stato azzerato oggi (NOTE/83). */
    drawdown_peak_resets_today?: number;
    drawdown_peak_reset_at?: string | null;
  } | null;
  pnl_history: PnlPoint[];
}

export type EquityRange = '24h' | '7d' | 'all';

export interface EquityCurveResponse {
  market: 'spot' | 'perp' | 'global';
  range: EquityRange;
  initial_equity_usd: string;
  benchmark_available?: boolean;
  items: Array<{
    timestamp_utc: string;
    equity_usd: string;
    pnl_usd: string;
    pnl_pct: string;
    drawdown_pct: string;
    btc_pct?: string;
  }>;
}

export interface AgentDecisionResponse {
  items: Array<{
    decision_id: string;
    timestamp_utc: string;
    asset?: string | null;
    market: string;
    action: string;
    signal_quality: string;
  }>;
  limit: number;
  offset: number;
}

export interface AssetBreakdownResponse {
  market: 'spot' | 'perp';
  items: Array<{
    asset: string;
    trade_count: number;
    win_rate_pct: string;
    pnl_usd: string;
    pnl_pct: string;
    allocation_pct: string;
  }>;
}

export interface TradeChartCandle {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
}

/** Una chiusura decisa da una persona, da marcare sul grafico.
 *  Il backend spedisce solo eventi che cadono DENTRO la finestra disegnata:
 *  quelli fuori sono gia' scartati la', quindi qui non serve nessun controllo. */
export interface ManualCloseMarker {
  t: string;
  price: string;
  size: string;
  /** % della size di apertura tolta da questa chiusura. null se non calcolabile. */
  pct?: string | null;
}

export interface TradeChart {
  interval: string;
  market: string;
  side: string;
  entry_price: string;
  exit_price: string;
  stop_loss?: string | null;
  take_profit_1?: string | null;
  take_profit_2?: string | null;
  liquidation_price?: string | null;
  opened_at: string;
  closed_at: string;
  live?: boolean;
  stop_reference?: {
    t: string;
    price?: string | null;
    field?: string | null;
    pre_candles?: number;
    inferred?: boolean;
  } | null;
  candles: TradeChartCandle[];
  post_close_candles?: TradeChartCandle[];
  /** Sempre presente (anche vuota) quando il grafico c'e'. */
  manual_closes?: ManualCloseMarker[];
  /** Risoluzioni che reggono per QUESTO trade: le altre vanno disabilitate,
   *  perche' mostrerebbero una finestra parziale come se fosse tutta la storia.
   *  La regola sta nel backend: il tetto e' suo e puo' cambiare. */
  intervals_available?: string[];
}

export interface TradeDetail {
  trade_id: string;
  asset: string;
  market: 'spot' | 'perp';
  direction: string;
  entry_price: string;
  original_entry_price?: string | null;
  current_position_entry_price?: string | null;
  current_or_exit_price: string;
  pnl_usd: string;
  pnl_pct: string;
  stop_loss?: string | null;
  take_profit_1?: string | null;
  take_profit_2?: string | null;
  liquidation_price?: string | null;
  trailing_stop?: string | null;
  breakeven_price?: string | null;
  size: string;
  leverage?: number | null;
  exposure_usd: string;
  fee_mode?: string | null;
  // perp-specific
  margin_usd?: string | null;
  stop_reference_price?: string | null;
  stop_reference_field?: string | null;
  opening_fee_usd?: string | null;
  taker_fee_usd?: string | null;
  maker_fee_usd?: string | null;
  funding_accrued_usd?: string | null;
  funding_rate_8h?: string | null;
  // spot-specific
  swap_fee_usd?: string | null;
  gas_cost_bnb?: string | null;
  // shared
  slippage_usd?: string | null;
  opened_at: string;
  closed_at?: string | null;
  close_reason?: string | null;
  is_smart_sl?: boolean;
  ssl_action?: 'sell' | 'rebuy';
  ssl_level?: string | null;
  smart_sl_levels?: string[] | null;
  smart_sl_state_summary?: { status: string; reentries: number; fill_price?: string | null; rebuy_fill_price?: string | null }[] | null;
  smart_sl_reentries_exhausted?: boolean;
  smart_sl_original_tp1?: string | null;
  smart_sl_original_tp2?: string | null;
  smart_sl_protection_suspended?: boolean;
  chart?: TradeChart | null;
  is_simulated: boolean;
}

export interface AgentMobileSettings {
  mode: string;
  markets_enabled: string;
  execution_mode: string;
  network: string;
  test_scaling_pct: number;
  operating_hours_utc: string;
  // Globali
  drawdown_alert_enabled: boolean;
  daily_loss_limit_pct: number;
  drawdown_cap_pct: number;
  min_pool_liquidity_usd: number;
  market_reversal_filter_enabled: boolean;
  spot_market_reversal_filter_enabled: boolean;
  perp_market_reversal_filter_enabled: boolean;
  spot_breakeven_enabled: boolean;
  perp_breakeven_enabled: boolean;
  spot_trailing_enabled: boolean;
  perp_trailing_enabled: boolean;
  spot_time_stop_enabled: boolean;
  perp_time_stop_enabled: boolean;
  perp_trend_shock_enabled: boolean;
  perp_trend_shock_adx_threshold: number;
  perp_trend_shock_natr_percentile: number;
  perp_trend_shock_volume_threshold: number;
  perp_trend_shock_recovery_confirmations: number;
  perp_smart_sl_enabled: boolean;
  perp_smart_sl_l1_frac: number;
  perp_smart_sl_l2_frac: number;
  perp_smart_sl_split_l1: number;
  perp_smart_sl_split_l2: number;
  perp_smart_sl_split_l3: number;
  perp_smart_sl_rebuy_mode: string;
  perp_smart_sl_rebuy_above_entry_pct: number;
  perp_smart_sl_split_l1_r2: number;
  perp_smart_sl_split_l2_r2: number;
  perp_smart_sl_split_l3_r2: number;
  perp_smart_sl_delta_l1: number;
  perp_smart_sl_delta_l2: number;
  perp_smart_sl_confirmation_candles: number;
  perp_smart_sl_max_reentries: number;
  perp_smart_sl_tp_adjust_after_rebuy: boolean;
  perp_smart_sl_tp_recovery_delta_pct: number;
  spot_breakeven_mode: string;
  perp_breakeven_mode: string;
  spot_sl_mode: string;
  perp_sl_mode: string;
  perp_min_rr: number;
  perp_tp1_atr_multiplier: number;
  perp_tp2_atr_multiplier: number;
  spot_structural_stop_lookback_candles: number;
  spot_structural_stop_buffer_pct: number;
  perp_structural_stop_lookback_candles: number;
  perp_structural_stop_buffer_pct: number;
  // Spot
  spot_capital_per_trade_pct: number;
  spot_per_trade_pct: number;
  spot_max_open_positions: number;
  spot_max_exposure_pct: number;
  spot_cooldown_minutes: number;
  spot_max_slippage_pct: number;
  // Perp
  perp_capital_per_trade_pct: number;
  perp_per_trade_pct: number;
  perp_max_open_positions: number;
  perp_max_exposure_pct: number;
  perp_cooldown_minutes: number;
  perp_max_slippage_pct: number;
  perp_fixed_margin_enabled: boolean;
  perp_fixed_margin_usd: number;
  // Legacy (backward compat)
  capital_per_trade_pct: number;
  per_trade_pct: number;
  max_open_positions: number;
  max_total_exposure_pct: number;
  max_slippage_pct: number;
  cooldown_minutes: number;
  spot_confidence_threshold: number;
  spot_volatility_trigger_pct: number;
  spot_relative_volume_threshold: number;
  spot_atr_stop_multiplier: number;
  spot_trailing_distance_pct: number;
  spot_partial_take_profit_pct: number;
  spot_tp1_close_pct: number;
  spot_time_stop_hours: number;
  perp_direction_mode: string;
  perp_min_leverage: number;
  perp_max_leverage: number;
  perp_value_area_pct: number;
  perp_atr_stop_multiplier: number;
  perp_trailing_mode: 'largo' | 'stretto';
  perp_trailing_pnl_pct: number;
  perp_protection_mode: 'off' | 'trailing' | 'profit_lock';
  /** Scalini del ratchet: [punto del tratto TP1→TP2, quota cumulativa del residuo da chiudere]. */
  perp_profit_lock_steps: Array<[number, number]>;
  perp_ratchet_breakeven_pct: number;
  perp_ratchet_breakeven_after_step: number;
  perp_ratchet_run_beyond_tp2: boolean;
  perp_ratchet_trailing_pct: number;
  perp_breakeven_min_profit_usd: number;
  perp_tp1_close_pct: number;
  perp_time_stop_hours: number;
  perp_fee_mode: 'taker' | 'maker' | 'none';
  spot_fee_mode: 'all' | 'none';
  post_close_candles: number;
  chart_pre_open_candles: number;
}

export interface AgentSettingsResponse {
  settings: AgentMobileSettings;
  source: string;
  persisted: boolean;
}

export interface CredentialCheck {
  name: string;
  configured: boolean;
  status: string;
}

export interface CredentialValidationResponse {
  checks: CredentialCheck[];
  lock_expires_at: string;
  lock_ttl_seconds: number;
}

export interface MobileWalletView {
  networks: Array<{
    network: string;
    address: string | null;
    configured: boolean;
    role: string;
    balance_status: string;
    balances: Array<{
      asset: string;
      balance: string;
      decimals: number;
      source: string;
    }>;
  }>;
}

export interface ExecutionWalletAddressView {
  address: string;
  active: boolean;
  network: string;
  balance_bnb?: string | null;
  balance_status: string;
}

export interface ExecutionWalletProviderView {
  provider: string;
  market: 'spot' | 'perp';
  address?: string | null;
  network: string;
  configured: boolean;
  active: boolean;
  balance_bnb?: string | null;
  balance_status: string;
}

export interface ExecutionWalletsResponse {
  network: string;
  chain_id: number;
  bsc_network?: 'testnet' | 'mainnet';
  active_wallet_address?: string | null;
  spot_active_provider: string;
  perp_active_provider: string;
  available_wallets: ExecutionWalletAddressView[];
  wallets: ExecutionWalletProviderView[];
}

function request<T>(
  path: string,
  options: { method?: 'GET' | 'PUT' | 'POST'; body?: unknown; token?: string; timeoutMs?: number } = {},
): Promise<T> {
  return backendRequest<T>(path, { ...options, label: 'Agent API' });
}

/**
 * Verifica il token admin contro un endpoint privilegiato senza effetti
 * collaterali. true = accettato, false = rifiutato (401/403); gli errori di
 * rete vengono rilanciati: "backend irraggiungibile" non e' "token sbagliato".
 */
export async function verifyAdminToken(adminToken: string): Promise<boolean> {
  try {
    await request('/api/v1/notifications/devices', { token: adminToken, timeoutMs: 8000 });
    return true;
  } catch (err) {
    if (err instanceof BackendHttpError && (err.status === 401 || err.status === 403)) return false;
    throw err;
  }
}

export function fetchAgentStatus(): Promise<AgentStatus> {
  return request<AgentStatus>('/api/v1/agent/status');
}

export function fetchEligibleTokens(): Promise<EligibleTokensResponse> {
  return request<EligibleTokensResponse>('/api/v1/agent/eligible-tokens');
}

export function fetchAgentWatchlist(): Promise<AgentWatchlistResponse> {
  return request<AgentWatchlistResponse>('/api/v1/agent/watchlist');
}

export function updateAgentWatchlist(tokens: string[], adminToken: string): Promise<AgentWatchlistResponse> {
  return request<AgentWatchlistResponse>('/api/v1/agent/watchlist', {
    method: 'PUT',
    body: { tokens },
    token: adminToken,
  });
}

export function fetchSpotWatchlist(): Promise<AgentMarketWatchlistResponse> {
  return request<AgentMarketWatchlistResponse>('/api/v1/agent/watchlist/spot');
}

export function updateSpotWatchlist(tokens: string[], adminToken: string): Promise<AgentMarketWatchlistResponse> {
  return request<AgentMarketWatchlistResponse>('/api/v1/agent/watchlist/spot', {
    method: 'PUT',
    body: { tokens },
    token: adminToken,
  });
}

export function fetchPerpWatchlist(): Promise<AgentMarketWatchlistResponse> {
  return request<AgentMarketWatchlistResponse>('/api/v1/agent/watchlist/perp');
}

export function updatePerpWatchlist(tokens: string[], adminToken: string): Promise<AgentMarketWatchlistResponse> {
  return request<AgentMarketWatchlistResponse>('/api/v1/agent/watchlist/perp', {
    method: 'PUT',
    body: { tokens },
    token: adminToken,
  });
}

export function fetchSpotView(): Promise<SpotView> {
  return request<SpotView>('/api/v1/views/spot');
}

export function fetchPerpView(): Promise<PerpView> {
  return request<PerpView>('/api/v1/views/perp');
}

export function fetchGlobalView(): Promise<GlobalView> {
  return request<GlobalView>('/api/v1/views/global');
}

export function fetchScannerStatus(): Promise<ScannerStatusResponse> {
  return request<ScannerStatusResponse>('/api/v1/views/scanner-status');
}

export function fetchEquityCurve(range: EquityRange = '24h'): Promise<EquityCurveResponse> {
  return request<EquityCurveResponse>(`/api/v1/views/equity-curve?market=global&range=${range}`);
}

export function fetchAgentDecisions(): Promise<AgentDecisionResponse> {
  return request<AgentDecisionResponse>('/api/v1/agent/decisions?limit=3');
}

export function fetchAssetBreakdown(): Promise<AssetBreakdownResponse> {
  return request<AssetBreakdownResponse>('/api/v1/views/asset-breakdown?market=spot');
}

export function fetchTradeDetail(
  tradeId: string,
  options: { enrichChart?: boolean; timeoutMs?: number; interval?: string } = {},
): Promise<TradeDetail> {
  const q = new URLSearchParams();
  if (options.enrichChart) q.set('enrich_chart', 'true');
  if (options.interval) q.set('interval', options.interval);
  const params = q.toString() ? `?${q}` : '';
  return request<TradeDetail>(
    `/api/v1/views/trade-detail/${encodeURIComponent(tradeId)}${params}`,
    { timeoutMs: options.timeoutMs },
  );
}

export function fetchAgentSettings(): Promise<AgentSettingsResponse> {
  return request<AgentSettingsResponse>('/api/v1/mobile/agent/settings');
}

export function saveAgentSettings(settings: AgentMobileSettings, adminToken: string): Promise<AgentSettingsResponse> {
  return request<AgentSettingsResponse>('/api/v1/mobile/agent/settings', {
    method: 'PUT',
    body: settings,
    token: adminToken,
  });
}

export function validateOnboarding(adminToken: string): Promise<CredentialValidationResponse> {
  return request<CredentialValidationResponse>('/api/v1/mobile/agent/onboarding/validate', {
    method: 'POST',
    token: adminToken,
  });
}

export function fetchMobileWallet(): Promise<MobileWalletView> {
  return request<MobileWalletView>('/api/v1/mobile/agent/wallet');
}

export function fetchExecutionWallets(): Promise<ExecutionWalletsResponse> {
  return request<ExecutionWalletsResponse>('/api/v1/execution/wallets');
}

export interface ClaudeUsageView {
  call_count: number;
  input_tokens: number;
  output_tokens: number;
  total_cost_usd: number;
  budget_usd: number;
  budget_pct: number;
}

export function fetchClaudeUsage(): Promise<ClaudeUsageView> {
  return request<ClaudeUsageView>('/api/v1/agent/claude-usage');
}

export function setKillSwitch(state: KillSwitchState, adminToken: string): Promise<AgentStatus> {
  return request<AgentStatus>('/api/v1/agent/kill-switch', {
    method: 'PUT',
    body: { state },
    token: adminToken,
  });
}

export interface ResetDailyCounterResponse {
  status: string;
  reason?: string;
  resets_today?: number;
  pnl_before_pct?: string;
  reset_at?: string;
}

/**
 * Fa ripartire da adesso il conteggio della perdita giornaliera (NOTE/63).
 * Non cambia il limite e non disarma la protezione: lo stesso limite vale sul
 * nuovo tratto. Il backend conta e registra ogni azzeramento.
 */
export function resetDailyCounter(adminToken: string, note?: string): Promise<ResetDailyCounterResponse> {
  return request<ResetDailyCounterResponse>('/api/v1/agent/risk/reset-daily-counter', {
    method: 'POST',
    body: { note: note ?? null },
    token: adminToken,
  });
}

export interface ResetDrawdownPeakResponse {
  status: string;
  reason?: string;
  reset_at?: string;
  resets_today?: number;
  peak_before_usd?: number;
  drawdown_before_pct?: number;
  drawdown_pct_now?: number | null;
}

/**
 * Riporta il picco del drawdown all'equity attuale (NOTE/83, gemello del reset
 * giornaliero). Il picco storico non scende mai da solo: senza questo, un
 * drawdown_cap_guard scattato può restare agganciato per settimane anche a
 * mercato tranquillo. Il cap in percentuale non cambia, resta pienamente
 * attivo sul nuovo tratto.
 */
export function resetDrawdownPeak(adminToken: string, note?: string): Promise<ResetDrawdownPeakResponse> {
  return request<ResetDrawdownPeakResponse>('/api/v1/agent/risk/reset-drawdown-peak', {
    method: 'POST',
    body: { note: note ?? null },
    token: adminToken,
  });
}

export interface RiskCloseAllResponse extends AgentStatus {
  closed_spot: number;
  closed_perp: number;
}

/** Le sole percentuali che il backend accetta per una chiusura manuale (NOTE/107). */
export type ClosePerpPercentage = 25 | 50 | 75 | 100;

export type ClosePerpOutcome =
  | 'confirmed'
  | 'stale_position'
  | 'already_closed'
  | 'key_reused_with_different_payload'
  | 'in_progress'
  | 'invalid_request'
  | 'not_found'
  | 'execution_failed';

export interface ClosePerpPositionResponse {
  status: string;
  outcome: ClosePerpOutcome;
  position_id: string;
  market?: string;
  asset?: string;
  requested_percentage?: number;
  requested_qty?: string;
  executed_qty?: string;
  executed_price?: string;
  remaining_qty?: string;
  position_status?: string;
  realized_pnl_usd?: string;
  close_reason?: string;
  /** L'utente aveva chiesto una parziale, ma il residuo sarebbe finito sotto la
   * soglia negoziabile: la posizione e' stata chiusa PER INTERO. Va detto in UI. */
  forced_full?: boolean;
  close_trade_id?: string | null;
  venue?: string;
  note?: string | null;
  /** Presente su stale_position: la size vera, da usare per il ritentativo. */
  current_size?: string;
  /** Messaggio leggibile per gli esiti non "confirmed", quando il backend lo manda. */
  detail?: string;
}

/**
 * Chiusura manuale (parziale o totale) di UNA posizione perp aperta (NOTE/107).
 *
 * NON usa backendRequest/request(): quello lancia un'eccezione su ogni stato non-2xx
 * e scarta il corpo, ma qui l'esito preciso sta SEMPRE nel body — anche su 409/422/
 * 404/502 — quindi va sempre letto, mai trattato come un errore generico.
 *
 * Due protezioni obbligatorie per contratto: `idempotencyKey` copre il retry (la
 * stessa chiave replica il primo esito invece di chiudere una seconda fetta);
 * `expectedSize` copre il doppio tap, che genera una chiave NUOVA e che
 * l'idempotenza da sola non può intercettare. Chiave nuova per ogni tentativo
 * nuovo, identica solo sul retry di uno stesso tentativo.
 */
export async function closePerpPosition(
  positionId: string,
  params: { percentage: ClosePerpPercentage; expectedSize: string; note?: string },
  idempotencyKey: string,
  adminToken: string,
): Promise<ClosePerpPositionResponse> {
  const url = `${requireBackend('Close Perp')}/api/v1/agent/positions/perp/${encodeURIComponent(positionId)}/close`;
  const headers = {
    ...authHeaders(adminToken),
    'Content-Type': 'application/json',
    'Idempotency-Key': idempotencyKey,
  };
  const body = {
    percentage: params.percentage,
    expected_size: params.expectedSize,
    note: params.note ?? null,
  };

  if (Capacitor.isNativePlatform()) {
    const response = await CapacitorHttp.request({
      method: 'POST',
      url,
      headers,
      data: body,
      connectTimeout: 12_000,
      readTimeout: 30_000,
    });
    return response.data as ClosePerpPositionResponse;
  }

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 30_000);
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    return await response.json() as ClosePerpPositionResponse;
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('Close Perp: timeout', { cause: err });
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
}

export function riskCloseAll(adminToken: string): Promise<RiskCloseAllResponse> {
  return request<RiskCloseAllResponse>('/api/v1/agent/risk/close-all', {
    method: 'POST',
    token: adminToken,
  });
}

export interface ResetDbResponse {
  status: string;
  archived_run_id: string | null;
  backup_label: string | null;
  deleted: Record<string, number>;
  kill_switch?: string;
}

export function resetDatabase(backupName: string | null, adminToken: string): Promise<ResetDbResponse> {
  return request<ResetDbResponse>('/api/v1/agent/dev/reset-db', {
    method: 'POST',
    body: { backup_name: backupName },
    token: adminToken,
  });
}

export interface EquityAdjustResponse {
  status: string;
  applied: string;
  total_equity_usd: string;
  initial_equity_usd: string;
  adjustment_id: number;
  created_at: string;
}

export function adjustEquity(amount: number, note: string | null, adminToken: string): Promise<EquityAdjustResponse> {
  return request<EquityAdjustResponse>('/api/v1/agent/equity/adjust', {
    method: 'POST',
    body: { amount, note },
    token: adminToken,
  });
}

// ── Diagnostica connessione Aster (sola lettura) ─────────────────────────────
// Il backend esegue solo chiamate informative: non può aprire, modificare o
// chiudere ordini. Le credenziali restano sul server e non transitano mai qui.
export type AsterCheckStatus = 'ok' | 'warning' | 'error' | 'critical';

export interface AsterCheck {
  key: string;
  label: string;
  status: AsterCheckStatus;
  detail: string;
  technical?: string | null;
}

export interface AsterConnectionReport {
  overall: AsterCheckStatus;
  summary: string;
  checks: AsterCheck[];
  started_at: string;
  duration_ms: number;
  account: string | null;
  subaccount_name: string | null;
  blocked: boolean;
}

export function testAsterConnection(adminToken: string): Promise<AsterConnectionReport> {
  return request<AsterConnectionReport>('/api/v1/aster/connection-test', {
    method: 'POST',
    token: adminToken,
  });
}

// ── Wallet Aster (sola lettura) ──────────────────────────────────────────────
export interface AsterAssetBalance {
  asset: string;
  balance: string;
  available: string;
}

export interface AsterWalletView {
  configured: boolean;
  subaccount_name: string | null;
  subaccount_address: string | null;
  api_wallet_address_short: string | null;
  balances: AsterAssetBalance[];
  total_balance_usdt: string | null;
  open_positions: number | null;
  reachable: boolean;
  error: string | null;
}

export function fetchAsterWallet(): Promise<AsterWalletView> {
  return request<AsterWalletView>('/api/v1/aster/wallet');
}
