import { Capacitor, CapacitorHttp } from '@capacitor/core';

const BACKEND_URL = (import.meta.env.VITE_BACKEND_API_BASE_URL as string | undefined)?.replace(/\/+$/, '');
const READ_TOKEN = import.meta.env.VITE_API_READ_TOKEN as string | undefined;

export type KillSwitchState = 'running' | 'soft_stop' | 'hard_stop' | 'degraded';

export interface AgentStatus {
  mode: string;
  markets_enabled: string;
  execution_mode: string;
  kill_switch: KillSwitchState;
  fast_loop_last_tick: string | null;
  slow_loop_last_tick: string | null;
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
}

export interface AgentMarketWatchlistResponse {
  master_tokens: string[];
  selected_tokens: string[];
  selected_count: number;
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
  perp_tp1_close_pct: number;
  perp_time_stop_hours: number;
  perp_fee_mode: 'taker' | 'maker' | 'none';
  spot_fee_mode: 'all' | 'none';
  post_close_candles: number;
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

function requireBackend(): string {
  if (!BACKEND_URL) throw new Error('Backend URL is not configured');
  if (!READ_TOKEN) throw new Error('Read token is not configured');
  return BACKEND_URL;
}

function authHeaders(token = READ_TOKEN): Record<string, string> {
  if (!token) throw new Error('API token is not configured');
  return { Authorization: `Bearer ${token}`, Accept: 'application/json' };
}

async function request<T>(
  path: string,
  options: { method?: 'GET' | 'PUT' | 'POST'; body?: unknown; token?: string; timeoutMs?: number } = {},
): Promise<T> {
  const method = options.method ?? 'GET';
  const url = `${requireBackend()}${path}`;
  const timeoutMs = options.timeoutMs ?? 30_000;
  const headers = {
    ...authHeaders(options.token),
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
  };

  if (Capacitor.isNativePlatform()) {
    const response = await CapacitorHttp.request({
      method,
      url,
      headers,
      data: options.body,
      connectTimeout: Math.min(12_000, timeoutMs),
      readTimeout: timeoutMs,
    });
    if (response.status < 200 || response.status >= 300) {
      throw new Error(`Agent API: ${response.status}`);
    }
    return response.data as T;
  }

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method,
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Agent API: ${response.status}`);
    return await response.json() as T;
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('Agent API: timeout');
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
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
  options: { enrichChart?: boolean; timeoutMs?: number } = {},
): Promise<TradeDetail> {
  const params = options.enrichChart ? '?enrich_chart=true' : '';
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

export interface RiskCloseAllResponse extends AgentStatus {
  closed_spot: number;
  closed_perp: number;
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
