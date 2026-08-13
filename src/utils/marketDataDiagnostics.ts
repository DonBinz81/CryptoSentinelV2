const STORAGE_KEY = 'cs_market_data_diagnostics';
const MAX_EVENTS = 100;

export interface MarketDataDiagnostic {
  timestamp: string;
  requestId: string;
  operation: string;
  status: 'started' | 'completed' | 'failed';
  elapsedMs?: number;
  httpStatus?: number;
  requestedCount?: number;
  returnedCount?: number;
  detail?: string;
}

export function recordMarketDataDiagnostic(event: MarketDataDiagnostic): void {
  try {
    const current = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]') as MarketDataDiagnostic[];
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([...current.slice(-(MAX_EVENTS - 1)), event]),
    );
  } catch {
    // Diagnostics must never affect market data behavior.
  }

  const method = event.status === 'failed' ? 'error' : 'info';
  console[method]('[market-data]', event);
}
