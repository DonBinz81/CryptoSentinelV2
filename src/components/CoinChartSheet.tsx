import { type FC, useEffect, useRef, useState, useMemo } from 'react';
import { createChart, ColorType, LineStyle, CrosshairMode, LineSeries, CandlestickSeries } from 'lightweight-charts';
import type { ISeriesApi, SeriesType, UTCTimestamp } from 'lightweight-charts';
import type { Coin, PriceAlert, RangeAlert } from '../types';
import type { Currency } from '../hooks/useCurrency';
import { useCoinChart, type LinePoint, type CandlePoint } from '../hooks/useCoinChart';
import { openExternalUrl } from '../utils/notifications';
import { fetchMarkets } from '../services/marketData';

// The backend OHLCV is historical closed candles, so the last bar lags the live
// price. This builds the "current/forming" bar from the live price so the chart
// ends at the displayed price (update the last bar, or append a new period).
function buildLiveBar(
  line: LinePoint[],
  candle: CandlePoint[],
  mode: 'line' | 'candle',
  price: number,
  fallbackStep: number,
): LinePoint | CandlePoint | null {
  const arr = mode === 'line' ? line : candle;
  if (arr.length === 0 || !isFinite(price) || price <= 0) return null;
  const last = arr[arr.length - 1];
  const lastTime = last.time as number;
  const step = arr.length >= 2 ? lastTime - (arr[arr.length - 2].time as number) : fallbackStep;
  const nowSec = Math.floor(Date.now() / 1000);
  const startNew = step > 0 && nowSec - lastTime >= step;
  const time = (startNew ? lastTime + step : lastTime) as UTCTimestamp;
  if (mode === 'line') {
    return { time, value: price };
  }
  const c = last as CandlePoint;
  if (startNew) {
    const open = c.close;
    return { time, open, high: Math.max(open, price), low: Math.min(open, price), close: price };
  }
  return { time, open: c.open, high: Math.max(c.high, price), low: Math.min(c.low, price), close: price };
}

interface Props {
  coin: Coin;
  alerts: PriceAlert[];
  rangeAlerts: RangeAlert[];
  currency: Currency;
  onClose: () => void;
  onToggleAlert: (id: string) => void;
  onToggleRangeAlert: (id: string) => void;
  onAddAlert: (coin: Coin) => void;
}

const DAYS: Record<string, number> = { '1g': 1, '7g': 7, '30g': 30, '1a': 365 };
type TF = '1g' | '7g' | '30g' | '1a';

const SYMBOL: Record<Currency, string> = { usd: '$', eur: '€', btc: '₿' };

function fmt(v: number | null | undefined, currency: Currency): string {
  if (v == null || !isFinite(v)) return '—';
  if (currency === 'btc') return v.toFixed(8);
  if (v >= 1000) return v.toLocaleString('it-IT', { maximumFractionDigits: 0 });
  if (v >= 1) return v.toFixed(2);
  return v.toFixed(6);
}

const CoinChartSheet: FC<Props> = ({
  coin, alerts, rangeAlerts, currency,
  onClose, onToggleAlert, onToggleRangeAlert, onAddAlert,
}) => {
  const [tf, setTf] = useState<TF>('7g');
  const [mode, setMode] = useState<'line' | 'candle'>(
    () => (localStorage.getItem('chart_mode') as 'line' | 'candle' | null) ?? 'line'
  );

  const handleModeChange = (m: 'line' | 'candle') => {
    localStorage.setItem('chart_mode', m);
    setMode(m);
  };
  const [showAlerts, setShowAlerts] = useState(true);

  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const seriesRef = useRef<ISeriesApi<SeriesType> | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const touchStartY = useRef(0);
  const [crosshairPrice, setCrosshairPrice] = useState<number | null>(null);

  const { lineData, candleData, loading, error } = useCoinChart(coin.id, currency, DAYS[tf]);

  const [livePrice, setLivePrice] = useState<number>(coin.current_price);
  const [livePct24h, setLivePct24h] = useState<number>(coin.price_change_percentage_24h ?? 0);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const coins = await fetchMarkets(1, 1, currency, undefined, [coin.id]);
        if (!cancelled && coins.length > 0) {
          setLivePrice(coins[0].current_price);
          setLivePct24h(coins[0].price_change_percentage_24h ?? 0);
        }
      } catch { /* silent — keep last known price */ }
    };
    refresh();
    const id = setInterval(refresh, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [coin.id, currency]);

  const sym = SYMBOL[currency];
  const isPositive = livePct24h >= 0;

  const coinAlerts = useMemo(() => alerts.filter(a => a.coinId === coin.id), [alerts, coin.id]);
  const coinRangeAlerts = useMemo(() => rangeAlerts.filter(a => a.coinId === coin.id), [rangeAlerts, coin.id]);
  const activeCount = coinAlerts.filter(a => a.active ?? true).length + coinRangeAlerts.filter(a => a.active ?? true).length;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    if (loading || error) return;
    const data = mode === 'line' ? lineData : candleData;
    if (data.length === 0) return;

    let chart: ReturnType<typeof createChart> | null = null;

    const init = () => {
      if (!containerRef.current) return;
      const w = containerRef.current.clientWidth;
      const h = containerRef.current.clientHeight;
      if (w === 0 || h === 0) return;

      chart = createChart(containerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: '#0f1929' },
          textColor: '#6b7280',
          fontSize: 11,
        },
        grid: {
          vertLines: { color: '#1f2937' },
          horzLines: { color: '#1f2937' },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#1f2937', minimumWidth: 60 },
        timeScale: {
          borderColor: '#1f2937',
          timeVisible: DAYS[tf] <= 7,
          secondsVisible: false,
        },
        handleScroll: false,
        handleScale: false,
        width: w,
        height: h,
      });
      chartRef.current = chart;

      const fallbackStep = DAYS[tf] <= 30 ? 3600 : 86400;

      if (mode === 'line') {
        const series = chart.addSeries(LineSeries, { color: '#3b82f6', lineWidth: 2, lastValueVisible: true, priceLineVisible: false });
        series.setData(lineData);
        seriesRef.current = series;
        const live = buildLiveBar(lineData, candleData, 'line', livePrice, fallbackStep);
        if (live) series.update(live as never);
        if (showAlerts) {
          coinAlerts.filter(a => a.active ?? true).forEach(a => {
            series.createPriceLine({
              price: a.threshold,
              color: a.direction === 'above' ? '#10b981' : '#ef4444',
              lineWidth: 1,
              lineStyle: LineStyle.LargeDashed,
              axisLabelVisible: true,
              title: a.direction === 'above' ? '▲' : '▼',
            });
          });
          coinRangeAlerts.filter(a => a.active ?? true).forEach(a => {
            series.createPriceLine({ price: a.maxPrice, color: '#3b82f6', lineWidth: 1, lineStyle: LineStyle.LargeDashed, axisLabelVisible: true, title: '▲' });
            series.createPriceLine({ price: a.minPrice, color: '#3b82f6', lineWidth: 1, lineStyle: LineStyle.LargeDashed, axisLabelVisible: true, title: '▼' });
          });
        }
      } else {
        const series = chart.addSeries(CandlestickSeries, {
          upColor: '#10b981',
          downColor: '#ef4444',
          borderUpColor: '#10b981',
          borderDownColor: '#ef4444',
          wickUpColor: '#10b981',
          wickDownColor: '#ef4444',
        });
        series.setData(candleData);
        seriesRef.current = series;
        const live = buildLiveBar(lineData, candleData, 'candle', livePrice, fallbackStep);
        if (live) series.update(live as never);
        if (showAlerts) {
          coinAlerts.filter(a => a.active ?? true).forEach(a => {
            series.createPriceLine({
              price: a.threshold,
              color: a.direction === 'above' ? '#10b981' : '#ef4444',
              lineWidth: 1,
              lineStyle: LineStyle.LargeDashed,
              axisLabelVisible: true,
              title: a.direction === 'above' ? '▲' : '▼',
            });
          });
          coinRangeAlerts.filter(a => a.active ?? true).forEach(a => {
            series.createPriceLine({ price: a.maxPrice, color: '#3b82f6', lineWidth: 1, lineStyle: LineStyle.LargeDashed, axisLabelVisible: true, title: '▲' });
            series.createPriceLine({ price: a.minPrice, color: '#3b82f6', lineWidth: 1, lineStyle: LineStyle.LargeDashed, axisLabelVisible: true, title: '▼' });
          });
        }
      }

      chart.timeScale().fitContent();

      chart.subscribeCrosshairMove((param) => {
        if (!param.point || !param.time || param.seriesData.size === 0) {
          setCrosshairPrice(null);
          return;
        }
        const entry = param.seriesData.values().next().value as { value?: number; close?: number } | undefined;
        const price = entry?.value ?? entry?.close ?? null;
        setCrosshairPrice(price ?? null);
      });
    };

    const raf = requestAnimationFrame(init);
    return () => {
      cancelAnimationFrame(raf);
      chart?.remove();
      chartRef.current = null;
      seriesRef.current = null;
      setCrosshairPrice(null);
    };
    // livePrice intentionally excluded: the dedicated effect below applies live
    // updates via series.update() so the chart is not rebuilt every refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lineData, candleData, mode, showAlerts, coinAlerts, coinRangeAlerts, loading, error, tf]);

  // Keep the last bar aligned with the live price as it refreshes (every 30s),
  // updating only the forming bar so the chart is never rebuilt (no flicker).
  useEffect(() => {
    const series = seriesRef.current;
    if (!series || loading || error) return;
    const data = mode === 'line' ? lineData : candleData;
    if (data.length === 0) return;
    const live = buildLiveBar(lineData, candleData, mode, livePrice, DAYS[tf] <= 30 ? 3600 : 86400);
    if (!live) return;
    try {
      series.update(live as never);
    } catch {
      // lightweight-charts rejects out-of-order times; ignore until next rebuild.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [livePrice]);

  return (
    <div
      className="fixed inset-0 bg-black/70 z-50 flex flex-col justify-end"
      onClick={onClose}
    >
      <div
        className="bg-dark-800 rounded-t-3xl border-t border-dark-600 h-[92vh] flex flex-col"
        onClick={e => e.stopPropagation()}
        onTouchStart={e => { touchStartY.current = e.touches[0].clientY; }}
        onTouchEnd={e => {
          const deltaY = e.changedTouches[0].clientY - touchStartY.current;
          if (deltaY > 80 && (scrollRef.current?.scrollTop ?? 0) <= 0) onClose();
        }}
      >
        {/* Handle */}
        <div className="flex justify-center pt-3 pb-1 flex-shrink-0">
          <div className="w-9 h-1 bg-dark-600 rounded-full" />
        </div>

        {/* Scrollable body */}
        <div ref={scrollRef} className="overflow-y-auto flex-1 pb-6">

          {/* Header */}
          <div className="flex items-center justify-between px-5 py-3">
            <div className="flex items-center gap-3">
              <img src={coin.image} alt={coin.name} className="w-10 h-10 rounded-full flex-shrink-0" loading="lazy" />
              <div>
                <button
                  className="flex items-center gap-1.5 text-white font-bold text-lg leading-tight hover:text-accent-blue transition-colors active:opacity-70"
                  onClick={() => openExternalUrl(`https://coinmarketcap.com/currencies/${coin.id}`)}
                >
                  {coin.name}
                  <svg className="w-3.5 h-3.5 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </button>
                <p className="text-xs text-gray-500 uppercase">{coin.symbol} · #{coin.market_cap_rank ?? '—'}</p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-white font-bold text-xl tabular-nums">
                {sym}{fmt(crosshairPrice ?? livePrice, currency)}
              </p>
              {crosshairPrice == null ? (
                <p className={`text-xs font-semibold mt-0.5 ${isPositive ? 'text-accent-green' : 'text-red-400'}`}>
                  {isPositive ? '▲' : '▼'} {Math.abs(livePct24h).toFixed(2)}%
                </p>
              ) : (
                <p className="text-xs font-semibold mt-0.5 text-gray-500">storico</p>
              )}
            </div>
          </div>

          {/* Timeframe + mode switch */}
          <div className="flex items-center justify-between px-5 pb-3">
            <div className="flex gap-1.5">
              {(['1g', '7g', '30g', '1a'] as TF[]).map(t => (
                <button
                  key={t}
                  onClick={() => setTf(t)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${
                    tf === t
                      ? 'bg-accent-blue/20 text-accent-blue border border-accent-blue/35'
                      : 'bg-dark-700 text-gray-400'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
            <div className="flex items-center bg-dark-700 rounded-xl p-1 gap-0.5">
              <button
                onClick={() => handleModeChange('line')}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${mode === 'line' ? 'bg-dark-600 text-white' : 'text-gray-500'}`}
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M3 17l6-6 4 4 8-8" />
                </svg>
                Linea
              </button>
              <button
                onClick={() => handleModeChange('candle')}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${mode === 'candle' ? 'bg-dark-600 text-white' : 'text-gray-500'}`}
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <rect x="4" y="8" width="4" height="8" rx="0.5" strokeWidth="2" />
                  <line x1="6" y1="4" x2="6" y2="8" strokeWidth="2" />
                  <line x1="6" y1="16" x2="6" y2="20" strokeWidth="2" />
                  <rect x="16" y="10" width="4" height="6" rx="0.5" strokeWidth="2" />
                  <line x1="18" y1="6" x2="18" y2="10" strokeWidth="2" />
                  <line x1="18" y1="16" x2="18" y2="20" strokeWidth="2" />
                </svg>
                Candele
              </button>
            </div>
          </div>

          {/* Chart container */}
          <div className="mx-5 rounded-xl overflow-hidden bg-[#0f1929] relative" style={{ height: 220 }}>
            <div ref={containerRef} className="w-full h-full" />
            {(loading || error) && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-[#0f1929]">
                {loading ? (
                  <>
                    <svg className="w-6 h-6 text-accent-blue animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <p className="text-gray-500 text-xs">Caricamento dati in corso…</p>
                  </>
                ) : (
                  <p className="text-gray-500 text-sm">Dati non disponibili</p>
                )}
              </div>
            )}
          </div>

          {/* Toggle mostra alert sul grafico */}
          <div className="flex items-center justify-between px-5 py-3">
            <span className="text-xs text-gray-400">
              Mostra alert sul grafico
              {activeCount > 0 && <span className="text-gray-600 ml-1">({activeCount} attivi)</span>}
            </span>
            <button
              onClick={() => setShowAlerts(v => !v)}
              className={`w-10 h-6 rounded-full relative flex-shrink-0 transition-colors ${showAlerts ? 'bg-accent-blue' : 'bg-dark-700'}`}
            >
              <span className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-all ${showAlerts ? 'right-1' : 'left-1'}`} />
            </button>
          </div>

          {/* Divider */}
          <div className="h-px bg-dark-700 mx-5 mb-3" />

          {/* Alert list */}
          {(coinAlerts.length > 0 || coinRangeAlerts.length > 0) && (
            <>
              <p className="px-5 pb-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">I tuoi alert</p>
              <div className="px-3 space-y-2">
                {coinAlerts.map(a => {
                  const isActive = a.active ?? true;
                  return (
                    <div key={a.id} className={`flex items-center gap-3 bg-dark-700 rounded-xl px-4 py-3 transition-opacity ${isActive ? 'opacity-100' : 'opacity-45'}`}>
                      <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${a.direction === 'above' ? 'bg-accent-green' : 'bg-red-400'}`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-gray-500">{a.direction === 'above' ? 'Soglia rialzo' : 'Soglia ribasso'}</p>
                        <p className="text-sm font-semibold text-white">{sym}{fmt(a.threshold, currency)}</p>
                      </div>
                      <button
                        onClick={() => onToggleAlert(a.id)}
                        className={`w-9 h-5 rounded-full relative flex-shrink-0 transition-colors ${isActive ? 'bg-accent-green' : 'bg-dark-600'}`}
                      >
                        <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${isActive ? 'right-0.5' : 'left-0.5'}`} />
                      </button>
                    </div>
                  );
                })}
                {coinRangeAlerts.map(a => {
                  const isActive = a.active ?? true;
                  return (
                    <div key={a.id} className={`flex items-center gap-3 bg-dark-700 rounded-xl px-4 py-3 transition-opacity ${isActive ? 'opacity-100' : 'opacity-45'}`}>
                      <span className="w-2.5 h-2.5 rounded-full border-2 border-accent-blue flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-gray-500">Range</p>
                        <p className="text-sm font-semibold text-white">{sym}{fmt(a.minPrice, currency)} – {sym}{fmt(a.maxPrice, currency)}</p>
                      </div>
                      <button
                        onClick={() => onToggleRangeAlert(a.id)}
                        className={`w-9 h-5 rounded-full relative flex-shrink-0 transition-colors ${isActive ? 'bg-accent-blue' : 'bg-dark-600'}`}
                      >
                        <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${isActive ? 'right-0.5' : 'left-0.5'}`} />
                      </button>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* Aggiungi alert */}
          <button
            onClick={() => { onClose(); onAddAlert(coin); }}
            className="flex items-center justify-center gap-2 mx-3 mt-3 py-3 rounded-xl border border-dashed border-dark-600 text-gray-500 text-sm font-medium hover:border-accent-blue hover:text-accent-blue transition-colors"
            style={{ width: 'calc(100% - 24px)' }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Aggiungi alert
          </button>
        </div>
      </div>
    </div>
  );
};

export default CoinChartSheet;
