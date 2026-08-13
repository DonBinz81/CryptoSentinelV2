import type {
  AgentSettings,
  AgentStatus,
  AgentDecisionResponse,
  AssetBreakdownResponse,
  CredentialValidationResponse,
  DataCoverageResponse,
  EquityCurveResponse,
  ExecutionProviderSelectionResponse,
  ExecutionStatus,
  ExecutionWalletsResponse,
  GlobalView,
  HealthPayload,
  KillSwitchState,
  LogResponse,
  MarketListResponse,
  NotificationPreferences,
  NotificationPreferencesResponse,
  OperationalStats,
  PerpView,
  SettingsResponse,
  SpotView,
  SupportTicketDetail,
  SupportTicketListResponse,
  SupportNotificationResponse,
  SupportTicketStatus,
  TradeDetail,
} from './types';

export type DashboardSession = {
  baseUrl: string;
  readToken: string;
  adminToken: string;
};

const DASHBOARD_PORT = '5176';
const BACKEND_PORT = '8001';
const LEGACY_BACKEND_URL = 'http://127.0.0.1:8000';
const LOCAL_BACKEND_URL = 'http://127.0.0.1:8001';

type TokenKind = 'read' | 'admin' | 'none';

export function defaultBackendBaseUrl(): string {
  if (typeof window === 'undefined') return LOCAL_BACKEND_URL;
  const { protocol, hostname } = window.location;
  if (!hostname || hostname === 'localhost' || hostname === '127.0.0.1') return LOCAL_BACKEND_URL;
  return `${protocol}//${hostname}:${BACKEND_PORT}`;
}

export function normalizeBackendBaseUrl(baseUrl: string): string {
  const fallback = defaultBackendBaseUrl();
  const value = baseUrl.trim();
  if (!value || value === LEGACY_BACKEND_URL) return fallback;
  try {
    const url = new URL(value);
    if (url.port === DASHBOARD_PORT) {
      url.port = BACKEND_PORT;
    }
    url.pathname = url.pathname.replace(/\/+$/, '');
    url.search = '';
    url.hash = '';
    return url.toString().replace(/\/$/, '');
  } catch {
    return value.replace(/\/+$/, '');
  }
}

async function requestJson<T>(
  session: DashboardSession,
  path: string,
  tokenKind: TokenKind = 'read',
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const token = tokenKind === 'admin' ? session.adminToken : tokenKind === 'read' ? session.readToken : '';
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const url = `${normalizeBackendBaseUrl(session.baseUrl)}${path}`;
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}${body ? ` - ${body.slice(0, 180)}` : ''}`);
  }
  return (await response.json()) as T;
}

export function fetchSpot(session: DashboardSession) {
  return requestJson<SpotView>(session, '/api/v1/views/spot');
}

export function fetchPerp(session: DashboardSession) {
  return requestJson<PerpView>(session, '/api/v1/views/perp');
}

export function fetchGlobal(session: DashboardSession) {
  return requestJson<GlobalView>(session, '/api/v1/views/global');
}

export function fetchEquityCurve(session: DashboardSession, market: 'spot' | 'perp' | 'global', range = '24h') {
  return requestJson<EquityCurveResponse>(session, `/api/v1/views/equity-curve?market=${market}&range=${range}`);
}

export function fetchAssetBreakdown(session: DashboardSession, market: 'spot' | 'perp') {
  return requestJson<AssetBreakdownResponse>(session, `/api/v1/views/asset-breakdown?market=${market}`);
}

export function fetchTradeDetail(session: DashboardSession, tradeId: string) {
  return requestJson<TradeDetail>(session, `/api/v1/views/trade-detail/${encodeURIComponent(tradeId)}?enrich_chart=true`);
}

export function fetchOperationalStats(session: DashboardSession) {
  return requestJson<OperationalStats>(session, '/api/v1/views/operational-stats');
}

export function fetchAgentDecisions(session: DashboardSession, market?: 'spot' | 'perp', offset = 0) {
  const params = new URLSearchParams({ limit: '200', offset: String(offset) });
  if (market) params.set('market', market);
  return requestJson<AgentDecisionResponse>(session, `/api/v1/agent/decisions?${params.toString()}`);
}

export function fetchAgentStatus(session: DashboardSession) {
  return requestJson<AgentStatus>(session, '/api/v1/agent/status');
}

export function fetchReady(session: DashboardSession) {
  return requestJson<HealthPayload>(session, '/health/ready');
}

export function fetchLive(session: DashboardSession) {
  return requestJson<HealthPayload>(session, '/health/live', 'none');
}

export function fetchHeartbeat(session: DashboardSession) {
  return requestJson<HealthPayload>(session, '/health/heartbeat');
}

export function fetchExecutionStatus(session: DashboardSession) {
  return requestJson<ExecutionStatus>(session, '/api/v1/execution/status');
}

export function fetchExecutionWallets(session: DashboardSession) {
  return requestJson<ExecutionWalletsResponse>(session, '/api/v1/execution/wallets');
}

export function setSpotExecutionProvider(session: DashboardSession, provider: string) {
  return requestJson<ExecutionProviderSelectionResponse>(session, '/api/v1/execution/provider', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ provider }),
  });
}

export function setPerpExecutionProvider(session: DashboardSession, provider: string) {
  return requestJson<ExecutionProviderSelectionResponse>(session, '/api/v1/execution/perp-provider', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ provider }),
  });
}

export function setRpcEndpoint(session: DashboardSession, index: number) {
  return requestJson<ExecutionWalletsResponse>(session, '/api/v1/execution/rpc-endpoint', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ index }),
  });
}

export function setExecutionNetwork(session: DashboardSession, network: 'testnet' | 'mainnet') {
  return requestJson<ExecutionWalletsResponse>(session, '/api/v1/execution/network', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ network }),
  });
}

export function setExecutionWallet(session: DashboardSession, address: string) {
  return requestJson<ExecutionWalletsResponse>(session, '/api/v1/execution/wallet', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ address }),
  });
}

export function addExecutionWallet(session: DashboardSession, address: string) {
  return requestJson<ExecutionWalletsResponse>(session, '/api/v1/execution/wallets', 'admin', {
    method: 'POST',
    body: JSON.stringify({ address }),
  });
}

export function sendToken(
  session: DashboardSession,
  payload: { to_address: string; amount: string; token: string; wallet_password: string },
) {
  return requestJson<{ status: string; tx_hash?: string; error?: string; detail?: unknown }>(
    session,
    '/api/v1/execution/send',
    'admin',
    { method: 'POST', body: JSON.stringify(payload) },
  );
}

export function fetchDataCoverage(session: DashboardSession) {
  return requestJson<DataCoverageResponse>(session, '/api/v1/agent/data-coverage');
}

export function setKillSwitch(session: DashboardSession, state: KillSwitchState) {
  return requestJson<AgentStatus>(session, '/api/v1/agent/kill-switch', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ state }),
  });
}

export function fetchLogs(session: DashboardSession, params: { level?: string; search?: string; limit?: number }) {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 200));
  if (params.level) search.set('level', params.level);
  if (params.search) search.set('search', params.search);
  return requestJson<LogResponse>(session, `/api/v1/observability/logs?${search.toString()}`, 'admin');
}

export function fetchSupportTickets(session: DashboardSession, params: { archived?: boolean } = {}) {
  const search = new URLSearchParams();
  if (params.archived) search.set('ticket_status', 'archived');
  const suffix = search.toString() ? `?${search.toString()}` : '';
  return requestJson<SupportTicketListResponse>(session, `/api/v1/support/admin/tickets${suffix}`, 'admin');
}

export function fetchSupportNotifications(session: DashboardSession) {
  return requestJson<SupportNotificationResponse>(session, '/api/v1/support/admin/notifications', 'admin');
}

export function fetchSupportTicket(session: DashboardSession, ticketId: string) {
  return requestJson<SupportTicketDetail>(session, `/api/v1/support/admin/tickets/${encodeURIComponent(ticketId)}`, 'admin');
}

export function markSupportTicketRead(session: DashboardSession, ticketId: string) {
  return requestJson<SupportTicketDetail>(session, `/api/v1/support/admin/tickets/${encodeURIComponent(ticketId)}/read`, 'admin', {
    method: 'POST',
  });
}

export function markAllSupportTicketsRead(session: DashboardSession) {
  return requestJson<{ updated: number }>(session, '/api/v1/support/admin/tickets/read-all', 'admin', {
    method: 'POST',
  });
}

export function replySupportTicket(session: DashboardSession, ticketId: string, message: string) {
  return requestJson<SupportTicketDetail>(session, `/api/v1/support/admin/tickets/${encodeURIComponent(ticketId)}/messages`, 'admin', {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

export function updateSupportTicketStatus(session: DashboardSession, ticketId: string, status: SupportTicketStatus) {
  return requestJson<SupportTicketDetail>(session, `/api/v1/support/admin/tickets/${encodeURIComponent(ticketId)}/status`, 'admin', {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

export function fetchSettings(session: DashboardSession) {
  return requestJson<SettingsResponse>(session, '/api/v1/mobile/agent/settings');
}

export function saveSettings(session: DashboardSession, settings: AgentSettings) {
  return requestJson<SettingsResponse>(session, '/api/v1/mobile/agent/settings', 'admin', {
    method: 'PUT',
    body: JSON.stringify(settings),
  });
}

export function validateOnboarding(session: DashboardSession) {
  return requestJson<CredentialValidationResponse>(session, '/api/v1/mobile/agent/onboarding/validate', 'admin', {
    method: 'POST',
  });
}

export type ResetDbResponse = {
  status: string;
  archived_run_id: string | null;
  backup_label: string | null;
  deleted: Record<string, number>;
  kill_switch?: string;
};

export function resetDatabase(session: DashboardSession, backupName: string | null) {
  return requestJson<ResetDbResponse>(session, '/api/v1/agent/dev/reset-db', 'admin', {
    method: 'POST',
    body: JSON.stringify({ backup_name: backupName }),
  });
}

export type EquityAdjustResponse = {
  status: string;
  applied: string;
  total_equity_usd: string;
  initial_equity_usd: string;
  adjustment_id: number;
  created_at: string;
};

export type EquityAdjustment = {
  id: number;
  amount: string;
  balance_after: string;
  note: string | null;
  created_at: string;
};

export function adjustEquity(session: DashboardSession, amount: number, note: string | null) {
  return requestJson<EquityAdjustResponse>(session, '/api/v1/agent/equity/adjust', 'admin', {
    method: 'POST',
    body: JSON.stringify({ amount, note }),
  });
}

export function fetchEquityAdjustments(session: DashboardSession) {
  return requestJson<{ items: EquityAdjustment[]; count: number }>(session, '/api/v1/agent/equity/adjustments');
}

export function fetchMarkets(session: DashboardSession, limit = 50) {
  return requestJson<MarketListResponse>(session, `/api/v1/market-data/markets?currency=usd&limit=${limit}&page=1`);
}

export function fetchNotificationPrefs(session: DashboardSession) {
  return requestJson<NotificationPreferencesResponse>(session, '/api/v1/notifications/preferences');
}

export function saveNotificationPrefs(session: DashboardSession, prefs: NotificationPreferences) {
  return requestJson<NotificationPreferencesResponse>(session, '/api/v1/notifications/preferences', 'admin', {
    method: 'PUT',
    body: JSON.stringify(prefs),
  });
}

export type AgentMarketWatchlistResponse = {
  master_tokens: string[];
  selected_tokens: string[];
  selected_count: number;
};

export function fetchSpotWatchlist(session: DashboardSession) {
  return requestJson<AgentMarketWatchlistResponse>(session, '/api/v1/agent/watchlist/spot');
}

export function updateSpotWatchlist(session: DashboardSession, tokens: string[]) {
  return requestJson<AgentMarketWatchlistResponse>(session, '/api/v1/agent/watchlist/spot', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ tokens }),
  });
}

export function fetchPerpWatchlist(session: DashboardSession) {
  return requestJson<AgentMarketWatchlistResponse>(session, '/api/v1/agent/watchlist/perp');
}

export function updatePerpWatchlist(session: DashboardSession, tokens: string[]) {
  return requestJson<AgentMarketWatchlistResponse>(session, '/api/v1/agent/watchlist/perp', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ tokens }),
  });
}
