export interface Coin {
  id: string;
  symbol: string;
  name: string;
  image: string;
  current_price: number;
  price_change_percentage_24h: number;
  price_change_percentage_1h_in_currency?: number;
  price_change_percentage_7d_in_currency?: number;
  market_cap: number;
  market_cap_rank: number | null;
  total_volume: number;
  high_24h: number;
  low_24h: number;
}

export type AlertDirection = 'above' | 'below';
export type AlertCrossDirection = 'up' | 'down';

export interface PriceAlertTriggerOptions {
  crossingOnly?: boolean;
  keepActiveAfterTrigger?: boolean;
  rearmPercent?: number;
}

export interface PriceAlert {
  id: string;
  coinId: string;
  coinName: string;
  coinSymbol: string;
  coinImage: string;
  direction: AlertDirection;
  threshold: number;
  percentChange?: number;
  note?: string;
  triggered: boolean;
  triggeredAt?: number;
  lastTriggeredPrice?: number;
  lastCrossDirection?: AlertCrossDirection;
  crossingOnly?: boolean;
  keepActiveAfterTrigger?: boolean;
  rearmPercent?: number;
  lastObservedPrice?: number;
  waitingForRearm?: boolean;
  active?: boolean;
  createdAt: number;
}

export interface AlertHistoryEntry {
  id: string;
  coinId: string;
  coinName: string;
  coinSymbol: string;
  coinImage: string;
  direction: AlertDirection;
  crossDirection?: AlertCrossDirection;
  threshold: number;
  triggeredPrice: number;
  triggeredAt: number;
}

export interface RangeAlert {
  id: string;
  coinId: string;
  coinName: string;
  coinSymbol: string;
  coinImage: string;
  minPrice: number;
  maxPrice: number;
  note?: string;
  active?: boolean;
  isInsideRange: boolean | null;
  lastNotifiedAt: number | null;
  createdAt: number;
}
