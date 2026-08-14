import type { Currency } from '../hooks/useCurrency';

/**
 * Formattazione prezzi condivisa (locale it-IT in tutta l'app).
 *
 * Prima questa funzione esisteva in 4 copie identiche (AlertsTab, AlertModal,
 * CoinChartSheet, FavMovePopup): un fix di visualizzazione andava replicato a
 * mano in ognuna. Restano intenzionalmente locali i formatter di CoinCard
 * (tier di precisione piu' ricchi per la lista di mercato) e di AgentTab
 * (gestione micro-prezzi sub-dollaro fino a 18 decimali).
 */
export const CURRENCY_SYMBOL: Record<Currency, string> = { usd: '$', eur: '€', btc: '₿' };

export function formatPrice(v: number | null | undefined, currency: Currency = 'usd'): string {
  if (v == null || !isFinite(v)) return '—';
  if (currency === 'btc') return v.toFixed(8);
  if (v >= 1000) return v.toLocaleString('it-IT', { maximumFractionDigits: 0 });
  if (v >= 1) return v.toFixed(2);
  return v.toFixed(6);
}
