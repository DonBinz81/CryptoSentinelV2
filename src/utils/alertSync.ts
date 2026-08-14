import type { PriceAlert, RangeAlert } from '../types';
import { getDeviceId } from './deviceId';
import { ALERTS_TOKEN, BACKEND_URL, backendRequest } from '../services/http';

export interface FavSyncConfig {
  coins: { id: string; name: string; symbol: string }[];
  upPct: number;
  downPct: number;
  currency: string;
  refPrices: Record<string, number>;
}

// Se un sync fallisce (token errato, backend giu', 5xx) gli alert lato server
// restano stantii e le push arrivano con soglie vecchie: il fallimento va
// loggato e ritentato, non inghiottito. Un solo retry pendente alla volta:
// il piu' recente sostituisce il precedente.
const RETRY_DELAY_MS = 60_000;
let retryTimer: ReturnType<typeof setTimeout> | null = null;

export async function syncAlertsToBackend(
  priceAlerts: PriceAlert[],
  rangeAlerts: RangeAlert[],
  fav: FavSyncConfig,
): Promise<void> {
  if (!BACKEND_URL || !ALERTS_TOKEN) return;
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
  try {
    await backendRequest('/api/v1/alerts/sync', {
      method: 'POST',
      token: ALERTS_TOKEN,
      label: 'Alert sync',
      timeoutMs: 15_000,
      body: {
        device_id: getDeviceId(),
        price_alerts: priceAlerts
          .filter((a) => (!a.triggered || a.keepActiveAfterTrigger) && a.active !== false)
          .map((a) => ({
            coin_id: a.coinId,
            coin_name: a.coinName,
            coin_symbol: a.coinSymbol,
            direction: a.direction,
            threshold: a.threshold,
            note: a.note ?? null,
            crossing_only: a.crossingOnly === true,
            keep_active_after_trigger: a.keepActiveAfterTrigger === true,
            rearm_percent: Math.max(0, Number(a.rearmPercent ?? 0)),
            last_observed_price: a.lastObservedPrice ?? null,
          })),
        range_alerts: rangeAlerts
          .filter((a) => a.active !== false)
          .map((a) => ({
            coin_id: a.coinId,
            coin_name: a.coinName,
            coin_symbol: a.coinSymbol,
            min_price: a.minPrice,
            max_price: a.maxPrice,
            note: a.note ?? null,
          })),
        fav_coins: fav.coins.map((c) => ({ id: c.id, name: c.name, symbol: c.symbol })),
        fav_up_pct: fav.upPct,
        fav_down_pct: fav.downPct,
        fav_currency: fav.currency,
        fav_ref_prices: fav.refPrices,
      },
    });
  } catch (err) {
    console.warn('[alert-sync] sync fallito, retry tra 60s:', (err as Error).message);
    retryTimer = setTimeout(() => {
      retryTimer = null;
      void syncAlertsToBackend(priceAlerts, rangeAlerts, fav);
    }, RETRY_DELAY_MS);
  }
}
