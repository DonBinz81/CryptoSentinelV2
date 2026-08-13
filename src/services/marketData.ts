import { Capacitor, CapacitorHttp } from '@capacitor/core';
import type { Coin } from '../types';
import { recordMarketDataDiagnostic } from '../utils/marketDataDiagnostics';

export type ProviderName = 'cmc' | 'coingecko';

interface MarketAsset {
  id: string;
  symbol: string;
  name: string;
  image_url: string | null;
  price: number;
  percent_change_1h: number | null;
  percent_change_24h: number | null;
  percent_change_7d: number | null;
  market_cap: number | null;
  market_cap_rank: number | null;
  volume_24h: number | null;
  high_24h: number | null;
  low_24h: number | null;
}

interface MarketListResponse {
  provider: ProviderName;
  currency: string;
  items: MarketAsset[];
}

export interface OHLCVItem {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

interface OHLCVResponse {
  provider: string;
  asset_id: string;
  currency: string;
  interval: string | null;
  items: OHLCVItem[];
}

export interface ProviderRuntimeStatus {
  name: ProviderName;
  configured: boolean;
  cache_entries: number;
  credits_used: number;
  requests_made: number;
  requests_per_minute: number;
}

export interface ProviderSelectionResponse {
  active: ProviderName;
  providers: ProviderRuntimeStatus[];
  cmc_mcp: {
    enabled: boolean;
    configured: boolean;
    server_url: string;
    auth_header: string;
  };
  selection_scope: 'runtime_state';
}

const BACKEND_URL = (import.meta.env.VITE_BACKEND_API_BASE_URL as string | undefined)?.replace(/\/+$/, '');
const READ_TOKEN = import.meta.env.VITE_API_READ_TOKEN as string | undefined;

function requireBackend(): string {
  if (!BACKEND_URL) throw new Error('Backend market data URL is not configured');
  if (!READ_TOKEN) throw new Error('Read-only market data token is not configured');
  return BACKEND_URL;
}

function headers(token = READ_TOKEN): Record<string, string> {
  if (!token) throw new Error('API token is not configured');
  return { Authorization: `Bearer ${token}`, Accept: 'application/json' };
}

function createRequestId(): string {
  if (typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

async function request<T>(
  path: string,
  options: { method?: 'GET' | 'PUT'; body?: unknown; token?: string; signal?: AbortSignal } = {},
): Promise<T> {
  const method = options.method ?? 'GET';
  const requestId = createRequestId();
  const operation = path.split('?')[0];
  const started = performance.now();
  recordMarketDataDiagnostic({
    timestamp: new Date().toISOString(),
    requestId,
    operation,
    status: 'started',
  });
  let url: string;
  try {
    url = `${requireBackend()}${path}`;
    headers(options.token);
  } catch (error) {
    const detail = error instanceof Error ? error.message : 'Market data configuration is invalid';
    recordMarketDataDiagnostic({
      timestamp: new Date().toISOString(),
      requestId,
      operation,
      status: 'failed',
      elapsedMs: Math.round(performance.now() - started),
      detail,
    });
    throw error;
  }
  if (Capacitor.isNativePlatform()) {
    let response;
    try {
      response = await CapacitorHttp.request({
        method,
        url,
        headers: {
          ...headers(options.token),
          'X-Request-ID': requestId,
          ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        },
        data: options.body,
        connectTimeout: 20_000,
        readTimeout: 60_000,
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Native HTTP request failed';
      recordMarketDataDiagnostic({
        timestamp: new Date().toISOString(),
        requestId,
        operation,
        status: 'failed',
        elapsedMs: Math.round(performance.now() - started),
        detail,
      });
      throw new Error(`${detail} [${requestId}]`, { cause: error });
    }
    if (response.status < 200 || response.status >= 300) {
      const detail = typeof response.data?.detail === 'string' ? response.data.detail : undefined;
      recordMarketDataDiagnostic({
        timestamp: new Date().toISOString(),
        requestId,
        operation,
        status: 'failed',
        elapsedMs: Math.round(performance.now() - started),
        httpStatus: response.status,
        detail,
      });
      throw new Error(`Market data API: ${response.status}${detail ? ` - ${detail}` : ''} [${requestId}]`);
    }
    recordMarketDataDiagnostic({
      timestamp: new Date().toISOString(),
      requestId,
      operation,
      status: 'completed',
      elapsedMs: Math.round(performance.now() - started),
      httpStatus: response.status,
    });
    return response.data as T;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        ...headers(options.token),
        'X-Request-ID': requestId,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : 'Browser HTTP request failed';
    recordMarketDataDiagnostic({
      timestamp: new Date().toISOString(),
      requestId,
      operation,
      status: 'failed',
      elapsedMs: Math.round(performance.now() - started),
      detail,
    });
    throw error;
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string };
    recordMarketDataDiagnostic({
      timestamp: new Date().toISOString(),
      requestId,
      operation,
      status: 'failed',
      elapsedMs: Math.round(performance.now() - started),
      httpStatus: response.status,
      detail: payload.detail,
    });
    throw new Error(`Market data API: ${response.status}${payload.detail ? ` - ${payload.detail}` : ''} [${requestId}]`);
  }
  const payload = await response.json() as T;
  recordMarketDataDiagnostic({
    timestamp: new Date().toISOString(),
    requestId,
    operation,
    status: 'completed',
    elapsedMs: Math.round(performance.now() - started),
    httpStatus: response.status,
  });
  return payload;
}

function toCoin(asset: MarketAsset): Coin {
  return {
    id: asset.id,
    symbol: asset.symbol.toLowerCase(),
    name: asset.name,
    image: asset.image_url ?? '',
    current_price: asset.price,
    price_change_percentage_24h: asset.percent_change_24h ?? 0,
    price_change_percentage_1h_in_currency: asset.percent_change_1h ?? undefined,
    price_change_percentage_7d_in_currency: asset.percent_change_7d ?? undefined,
    market_cap: asset.market_cap ?? 0,
    market_cap_rank: asset.market_cap_rank,
    total_volume: asset.volume_24h ?? 0,
    high_24h: asset.high_24h ?? 0,
    low_24h: asset.low_24h ?? 0,
  };
}

export async function fetchMarkets(
  limit: number,
  page: number,
  currency: string,
  signal?: AbortSignal,
  ids?: string[],
): Promise<Coin[]> {
  const params = new URLSearchParams({
    currency,
    limit: String(limit),
    page: String(page),
  });
  if (ids?.length) params.set('ids', ids.join(','));
  const response = await request<MarketListResponse>(`/api/v1/market-data/markets?${params}`, { signal });
  recordMarketDataDiagnostic({
    timestamp: new Date().toISOString(),
    requestId: 'response-summary',
    operation: ids?.length ? 'favorites' : 'market-list',
    status: 'completed',
    requestedCount: ids?.length ?? limit,
    returnedCount: response.items.length,
  });
  return response.items.map(toCoin);
}

export async function searchMarkets(
  query: string,
  currency: string,
  signal?: AbortSignal,
): Promise<Coin[]> {
  const params = new URLSearchParams({ q: query, currency, limit: '25' });
  const response = await request<MarketListResponse>(`/api/v1/market-data/search?${params}`, { signal });
  recordMarketDataDiagnostic({
    timestamp: new Date().toISOString(),
    requestId: 'response-summary',
    operation: 'search',
    status: 'completed',
    requestedCount: 25,
    returnedCount: response.items.length,
    detail: query,
  });
  return response.items.map(toCoin);
}

export async function fetchOHLCV(
  assetId: string,
  currency: string,
  days: number,
  signal?: AbortSignal,
): Promise<OHLCVItem[]> {
  const params = new URLSearchParams({ asset_id: assetId, currency, days: String(days) });
  const response = await request<OHLCVResponse>(`/api/v1/market-data/ohlcv?${params}`, { signal });
  return response.items;
}

export function getProviderStatus(): Promise<ProviderSelectionResponse> {
  return request<ProviderSelectionResponse>('/api/v1/market-data/provider');
}

export function selectProvider(provider: ProviderName, adminToken: string): Promise<ProviderSelectionResponse> {
  return request<ProviderSelectionResponse>('/api/v1/market-data/provider', {
    method: 'PUT',
    body: { provider },
    token: adminToken,
  });
}
