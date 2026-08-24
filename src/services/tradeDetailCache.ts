// Cache in memoria del dettaglio trade (con grafico), condivisa da tutti i punti
// dell'app che lo mostrano: apertura scheda, refresh periodico, prefetch della
// lista. Estratta da AgentTab.tsx perché la logica di freschezza (vedi sotto)
// serviva un posto testabile fuori dal componente gigante.
import { fetchTradeDetail, type TradeDetail } from './agentApi';

const TRADE_DETAIL_CACHE_TTL_MS = 10 * 60_000;
const TRADE_DETAIL_CACHE_MAX = 80;
const TRADE_DETAIL_PREFETCH_RETRY_MS = 60_000;

/**
 * Quanto puo' restare valida in cache la fotografia di un trade ANCORA APERTO
 * prima che valga la pena rifare la richiesta, anche se strutturalmente e' gia'
 * "completa" (candele + stop_reference presenti).
 *
 * Per un trade CHIUSO "completo" e' una fotografia immutabile: non cambiera' mai
 * piu', quindi non serve mai rinnovarla. Per un trade LIVE invece i dati continuano
 * a muoversi — nuove candele, il prezzo corrente, un eventuale Smart SL appena
 * scattato — e "completo" una volta non significa "completo per sempre".
 *
 * Senza questo: un grafico live che aveva gia' soddisfatto hasCompleteTradeChart
 * restava fermo in cache indefinitamente, perche' NESSUNO dei punti che decidono
 * se rifare la richiesta (apertura scheda, refresh ogni 45s, prefetch della lista)
 * guardava mai quanto tempo fosse passato — il controllo di completezza vinceva
 * sempre, a prescindere dall'eta' del dato. E' cosi' che un grafico live poteva
 * non arrivare mai a mostrare un evento successo dopo il primo caricamento
 * "completo" (screenshot di David, 24/08, segnalato dalla chat B — NOTE/93).
 */
const TRADE_DETAIL_LIVE_REFRESH_MS = 60_000;

const tradeDetailCache = new Map<string, { detail: TradeDetail; updatedAt: number }>();
const tradeDetailInflight = new Map<string, Promise<TradeDetail>>();
const tradeDetailPrefetchRetryAt = new Map<string, number>();

const hasBaseTradeChart = (detail: TradeDetail): boolean =>
  (detail.chart?.candles?.length ?? 0) > 1;

const needsPostCloseCandles = (detail: TradeDetail): boolean =>
  Boolean(detail.chart && !detail.chart.live && detail.chart.closed_at);

/** Completezza STRUTTURALE: i campi attesi ci sono. Non dice nulla sull'eta' del
 * dato — per quello vedi isTradeDetailFresh. */
export const hasCompleteTradeChart = (detail: TradeDetail): boolean => {
  if (!hasBaseTradeChart(detail)) return false;
  if (!detail.chart?.stop_reference) return false;
  if (!needsPostCloseCandles(detail)) return true;
  return (detail.chart?.post_close_candles?.length ?? 0) > 0;
};

/** Completo E, se live, abbastanza recente da fidarsi senza rifare la richiesta.
 * `now` e' iniettabile solo per i test — la produzione usa sempre Date.now(). */
export const isTradeDetailFresh = (
  detail: TradeDetail,
  updatedAt: number,
  now: number = Date.now(),
): boolean => {
  if (!hasCompleteTradeChart(detail)) return false;
  if (detail.chart?.live) return now - updatedAt < TRADE_DETAIL_LIVE_REFRESH_MS;
  return true;
};

export const getCachedTradeDetail = (tradeId: string, now: number = Date.now()): TradeDetail | null => {
  const cached = tradeDetailCache.get(tradeId);
  if (!cached) return null;
  if (isTradeDetailFresh(cached.detail, cached.updatedAt, now)) return cached.detail;
  if (now - cached.updatedAt > TRADE_DETAIL_CACHE_TTL_MS) {
    tradeDetailCache.delete(tradeId);
    return null;
  }
  // Ne' abbastanza fresco ne' scaduto: si mostra comunque (niente schermo vuoto
  // mentre arriva il dato nuovo), ma chi decide se rifare la richiesta usa
  // hasCompleteCachedTradeDetail, non questa funzione.
  return cached.detail;
};

export const hasCompleteCachedTradeDetail = (tradeId: string, now: number = Date.now()): boolean => {
  const cached = tradeDetailCache.get(tradeId);
  return cached != null && isTradeDetailFresh(cached.detail, cached.updatedAt, now);
};

export const isTradeDetailInflight = (tradeId: string): boolean =>
  tradeDetailInflight.has(`${tradeId}:base`) || tradeDetailInflight.has(`${tradeId}:chart`);

export const shouldPrefetchTradeDetail = (tradeId: string): boolean => {
  if (hasCompleteCachedTradeDetail(tradeId) || isTradeDetailInflight(tradeId)) return false;
  return Date.now() >= (tradeDetailPrefetchRetryAt.get(tradeId) ?? 0);
};

/** Rimanda il prossimo tentativo di prefetch per questi trade: usato subito prima
 * di avviare i worker, cosi' un secondo giro di prefetch nel frattempo non li
 * rimette in coda. */
export const schedulePrefetchRetry = (tradeIds: string[]): void => {
  const at = Date.now() + TRADE_DETAIL_PREFETCH_RETRY_MS;
  tradeIds.forEach((tradeId) => tradeDetailPrefetchRetryAt.set(tradeId, at));
};

export const cacheTradeDetail = (tradeId: string, detail: TradeDetail): void => {
  const existing = tradeDetailCache.get(tradeId)?.detail;
  if (existing && hasCompleteTradeChart(existing) && !hasCompleteTradeChart(detail)) {
    return;
  }
  if (existing && hasBaseTradeChart(existing) && !hasBaseTradeChart(detail)) {
    return;
  }
  if (tradeDetailCache.has(tradeId)) tradeDetailCache.delete(tradeId);
  tradeDetailCache.set(tradeId, { detail, updatedAt: Date.now() });
  if (hasCompleteTradeChart(detail)) {
    tradeDetailPrefetchRetryAt.delete(tradeId);
  }
  while (tradeDetailCache.size > TRADE_DETAIL_CACHE_MAX) {
    const oldest = tradeDetailCache.keys().next().value;
    if (!oldest) break;
    tradeDetailCache.delete(oldest);
  }
};

export const fetchTradeDetailDeduped = (
  tradeId: string,
  options: { enrichChart?: boolean; timeoutMs?: number } = {},
): Promise<TradeDetail> => {
  const key = `${tradeId}:${options.enrichChart ? 'chart' : 'base'}`;
  const existing = tradeDetailInflight.get(key);
  if (existing) return existing;
  const request = fetchTradeDetail(tradeId, options)
    .then((detail) => {
      cacheTradeDetail(tradeId, detail);
      return detail;
    })
    .finally(() => {
      tradeDetailInflight.delete(key);
    });
  tradeDetailInflight.set(key, request);
  return request;
};
