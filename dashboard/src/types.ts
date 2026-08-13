export type KillSwitchState = 'running' | 'soft_stop' | 'hard_stop' | 'degraded';
export type SupportTicketStatus = 'open' | 'in_progress' | 'waiting_user' | 'resolved' | 'closed' | 'archived';

export type SupportMessage = {
  message_id: string;
  ticket_id: string;
  sender_type: 'user' | 'admin';
  sender_id?: string | null;
  body: string;
  diagnostics?: Record<string, unknown> | null;
  created_at: string;
};

export type SupportTicketSummary = {
  ticket_id: string;
  user_id: string;
  device_id?: string | null;
  display_name: string;
  category: string;
  priority: string;
  status: SupportTicketStatus;
  subject: string;
  created_at: string;
  updated_at: string;
  last_message_at: string;
  resolved_at?: string | null;
  closed_at?: string | null;
  closed_by?: string | null;
  message_count: number;
};

export type SupportTicketDetail = SupportTicketSummary & {
  messages: SupportMessage[];
};

export type SupportTicketListResponse = {
  items: SupportTicketSummary[];
  total: number;
};

export type SupportNotificationResponse = {
  unread_count: number;
  latest_ticket?: SupportTicketSummary | null;
};

export type SpotPosition = {
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
  status: string;
  opened_at: string;
};

export type SpotTrade = {
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
  timestamp_utc: string;
  is_simulated?: boolean;
};

export type SpotView = {
  open_positions: SpotPosition[];
  history: SpotTrade[];
  realized_pnl_usd: string;
  unrealized_pnl_usd: string;
  win_rate_pct: number;
  trade_count: number;
  trade_count_today: number;
  bot_active_days: number;
};

export type PnlPoint = {
  timestamp_utc: string;
  total_equity_usd: string;
  drawdown_pct: string;
};

export type PerpPosition = {
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
  status: string;
  opened_at: string;
};

export type PerpTrade = {
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
  timestamp_utc: string;
  is_simulated?: boolean;
};

export type PerpView = {
  open_positions: PerpPosition[];
  history: PerpTrade[];
  realized_pnl_usd: string;
  unrealized_pnl_usd: string;
  win_rate_pct: number;
  trade_count: number;
  trade_count_today: number;
  bot_active_days: number;
};

export type GlobalView = {
  total_equity_usd: string;
  initial_equity_usd: string;
  pnl_total_usd: string;
  pnl_total_pct: number;
  realized_pnl_usd: string;
  unrealized_pnl_usd: string;
  drawdown_pct: string;
  max_drawdown_pct: string;
  sharpe_status?: string;
  sharpe_ratio?: string | null;
  drawdown_cap_pct: number;
  exposure_pct: string;
  spot_exposure_usd: string;
  perp_exposure_usd: string;
  total_fees_usd: string;
  daily_pnl_usd: string;
  daily_pnl_net_pct: number;
  pnl_total_net_pct: number;
  agent_status: string;
  trades_today: number;
  open_spot_positions: number;
  open_perp_positions: number;
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
};

export type EquityCurvePoint = {
  timestamp_utc: string;
  equity_usd: string;
  pnl_usd: string;
  pnl_pct: string;
  drawdown_pct: string;
  btc_pct?: string;
};

export type EquityRange = '24h' | '7d' | 'all';

export type EquityCurveResponse = {
  market: 'spot' | 'perp' | 'global';
  range: EquityRange;
  initial_equity_usd: string;
  benchmark_available?: boolean;
  items: EquityCurvePoint[];
};

export type AgentDecisionItem = {
  decision_id: string;
  timestamp_utc: string;
  asset?: string | null;
  market: string;
  signal_quality: string;
  confidence: string;
  action: string;
  reasoning?: string | null;
  execution_result?: string | null;
  trade_id?: string | null;
};

export type AgentDecisionResponse = {
  items: AgentDecisionItem[];
  limit: number;
  offset: number;
};

export type AssetBreakdownItem = {
  asset: string;
  trade_count: number;
  win_rate_pct: string;
  pnl_usd: string;
  pnl_pct: string;
  allocation_pct: string;
};

export type AssetBreakdownResponse = {
  market: 'spot' | 'perp';
  items: AssetBreakdownItem[];
};

export type TradeDetail = {
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
  margin_usd?: string | null;
  stop_reference_price?: string | null;
  stop_reference_field?: string | null;
  opened_at: string;
  closed_at?: string | null;
  duration_seconds?: number | null;
  close_reason?: string | null;
  decision?: {
    decision_id: string;
    signal_quality: string;
    confidence: string;
    action: string;
    reasoning?: string | null;
  } | null;
  events: Array<Record<string, unknown>>;
  chart?: TradeChart | null;
  is_smart_sl?: boolean;
  ssl_action?: 'sell' | 'rebuy';
  ssl_level?: string | null;
  smart_sl_levels?: string[] | null;
  smart_sl_state_summary?: Array<Record<string, unknown>> | null;
  is_simulated: boolean;
};

export type TradeChartCandle = {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
};

export type TradeChart = {
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
  stop_reference?: {
    t: string;
    price?: string | null;
    field?: string | null;
    pre_candles?: number;
    inferred?: boolean;
  } | null;
  candles: TradeChartCandle[];
  post_close_candles?: TradeChartCandle[];
};

export type OperationalStats = {
  uptime_pct: string;
  heartbeat: Record<string, unknown>;
  degraded_count: number;
  degraded_reasons: string[];
  last_kill_switch?: string | null;
};

export type AgentStatus = {
  kill_switch?: KillSwitchState;
  mode?: string;
  execution_mode?: string;
  markets_enabled?: string;
  minimum_trade_frequency?: string;
  [key: string]: unknown;
};

export type HealthPayload = {
  status?: string;
  checks?: Record<string, unknown>;
  [key: string]: unknown;
};

export type ExecutionStatus = {
  mode?: string;
  network?: string;
  provider?: string;
  spot?: {
    active_provider?: string;
    providers?: unknown[];
  };
  perp?: {
    active_provider?: string;
    providers?: unknown[];
  };
  enabled?: boolean;
  [key: string]: unknown;
};

export type ExecutionProviderSelectionResponse = {
  active: string;
  providers: unknown[];
  selection_scope: string;
};

export type ExecutionWalletProviderView = {
  provider: string;
  market: 'spot' | 'perp';
  address?: string | null;
  network: string;
  configured: boolean;
  active: boolean;
  balance_bnb?: string | null;
  balance_status: string;
};

export type ExecutionWalletAddressView = {
  address: string;
  active: boolean;
  network: string;
  balance_bnb?: string | null;
  balance_status: string;
};

export type RpcEndpointView = {
  index: number;
  label: string;
  active: boolean;
  reachable: boolean;
  latency_ms?: number | null;
  chain_id?: number | null;
  status: 'reachable' | 'unreachable' | 'chain_mismatch';
};

export type ExecutionWalletsResponse = {
  network: string;
  chain_id: number;
  bsc_network?: 'testnet' | 'mainnet';
  active_wallet_address?: string | null;
  spot_active_provider: string;
  perp_active_provider: string;
  available_wallets: ExecutionWalletAddressView[];
  active_rpc_endpoint_index?: number | null;
  wallets: ExecutionWalletProviderView[];
  rpc_endpoints: RpcEndpointView[];
};

export type DataCoverageStatus = 'insufficient' | 'warming_up' | 'ready';

export type DataCoverageItem = {
  asset: string;
  market: 'spot' | 'perp';
  symbol: string;
  available_candles: number;
  required_candles: number;
  status: DataCoverageStatus;
  first_candle_at?: string | null;
  last_candle_at?: string | null;
  updated_at?: string | null;
  age_seconds?: number | null;
  source: string;
};

export type DataCoverageResponse = {
  generated_at: string;
  active_markets: string[];
  items: DataCoverageItem[];
};

export type LogEntry = {
  timestamp?: string | null;
  level?: string | null;
  logger?: string | null;
  message: string;
};

export type LogResponse = {
  available: boolean;
  source: string;
  entries: LogEntry[];
  truncated: boolean;
};

export type AgentSettings = Record<string, string | number | boolean>;

export type SettingsResponse = {
  settings: AgentSettings;
  source: string;
  persisted: boolean;
};

export type CredentialCheck = {
  name: string;
  configured: boolean;
  status: string;
};

export type CredentialValidationResponse = {
  checks: CredentialCheck[];
  lock_expires_at: string;
  lock_ttl_seconds: number;
};

export type MarketAsset = {
  id: string;
  symbol: string;
  name: string;
  current_price?: number | null;
  price_change_percentage_24h?: number | null;
  market_cap?: number | null;
  total_volume?: number | null;
};

export type MarketListResponse = {
  provider: string;
  currency: string;
  items: MarketAsset[];
};

export type NotificationPreferences = {
  spot_trades: boolean;
  perp_trades: boolean;
  risk_alerts: boolean;
  daily_summary: boolean;
  critical: boolean;
};

export type NotificationPreferencesResponse = {
  preferences: NotificationPreferences;
  source: 'default' | 'persisted';
};
