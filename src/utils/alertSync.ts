import { CapacitorHttp } from '@capacitor/core';
import type { PriceAlert, RangeAlert } from '../types';
import { getDeviceId } from './deviceId';

const BACKEND_URL = (import.meta.env.VITE_BACKEND_API_BASE_URL as string | undefined)?.replace(/\/+$/, '');
const ALERTS_TOKEN = import.meta.env.VITE_API_ALERTS_TOKEN as string | undefined;

export interface FavSyncConfig {
  coins: { id: string; name: string; symbol: string }[];
  upPct: number;
  downPct: number;
  currency: string;
  refPrices: Record<string, number>;
}

export async function syncAlertsToBackend(
  priceAlerts: PriceAlert[],
  rangeAlerts: RangeAlert[],
  fav: FavSyncConfig,
): Promise<void> {
  if (!BACKEND_URL || !ALERTS_TOKEN) return;
  try {
    await CapacitorHttp.request({
      method: 'POST',
      url: `${BACKEND_URL}/api/v1/alerts/sync`,
      headers: {
        Authorization: `Bearer ${ALERTS_TOKEN}`,
        'Content-Type': 'application/json',
      },
      data: {
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
  } catch {
    // Sync is best-effort — local alerts still work as fallback
  }
}
