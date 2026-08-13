import { useState, useEffect } from 'react';
import { type UTCTimestamp } from 'lightweight-charts';
import { fetchOHLCV } from '../services/marketData';

export interface LinePoint { time: UTCTimestamp; value: number }
export interface CandlePoint { time: UTCTimestamp; open: number; high: number; low: number; close: number }

export function useCoinChart(
  coinId: string,
  currency: string,
  days: number,
) {
  const [lineData, setLineData] = useState<LinePoint[]>([]);
  const [candleData, setCandleData] = useState<CandlePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!coinId) return;
    let ctrl: AbortController;

    // Short debounce only to absorb rapid timeframe clicks — not a loading delay.
    const debounce = setTimeout(() => {
      ctrl = new AbortController();
      setLoading(true);
      setError(false);

      (async () => {
        try {
          const bars = await fetchOHLCV(coinId, currency, days, ctrl.signal);
          const seen = new Set<number>();
          const candles: CandlePoint[] = [];
          const line: LinePoint[] = [];
          for (const bar of bars) {
            const time = Math.floor(new Date(bar.timestamp).getTime() / 1000);
            if (seen.has(time)) continue;
            seen.add(time);
            line.push({ time: time as UTCTimestamp, value: bar.close });
            candles.push({
              time: time as UTCTimestamp,
              open: bar.open,
              high: bar.high,
              low: bar.low,
              close: bar.close,
            });
          }
          // Always set both so switching mode is instant with no re-fetch.
          setLineData(line);
          setCandleData(candles);
        } catch (e) {
          if ((e as Error).name !== 'AbortError') setError(true);
        } finally {
          if (!ctrl.signal.aborted) setLoading(false);
        }
      })();
    }, 80);

    return () => {
      clearTimeout(debounce);
      ctrl?.abort();
    };
  }, [coinId, currency, days]); // mode excluded: switching view never re-fetches

  return { lineData, candleData, loading, error };
}
