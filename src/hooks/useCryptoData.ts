import { useState, useEffect, useCallback, useRef } from 'react';
import type { Coin } from '../types';
import { fetchMarkets } from '../services/marketData';

export type PerPage = 50 | 100 | 200 | 400 | 600;

const CACHE_KEY = 'cryptosentinelv2_coins_cache';
// La cache serve solo all'avvio a freddo: riscriverla a ogni poll significa
// serializzare centinaia di KB sul main thread ogni 30s. Basta ogni 2 minuti.
const CACHE_WRITE_MIN_INTERVAL_MS = 120_000;
async function fetchCoinsAll(perPage: PerPage, page: number, currency: string, signal: AbortSignal): Promise<Coin[]> {
  return fetchMarkets(perPage, page, currency, signal);
}

function loadCachedCoins(): Coin[] {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as Coin[];
  } catch {
    return [];
  }
}

export function useCryptoData(intervalMs = 30_000, perPage: PerPage = 50, page = 1, currency = 'usd') {
  const [coins, setCoins] = useState<Coin[]>(() => page === 1 ? loadCachedCoins() : []);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchRef = useRef<() => Promise<void>>(async () => {});
  const coinsRef = useRef<Coin[]>(page === 1 ? loadCachedCoins() : []);
  const requestVersionRef = useRef(0);
  const lastCacheWriteRef = useRef(0);

  const fetchCoins = useCallback(async () => {
    const requestVersion = ++requestVersionRef.current;
    if (retryRef.current) { clearTimeout(retryRef.current); retryRef.current = null; }
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      const data = await fetchCoinsAll(perPage, page, currency, abortRef.current.signal);
      if (requestVersion !== requestVersionRef.current) return;
      coinsRef.current = data;
      setCoins(data);
      setError(null);
      setLastUpdated(new Date());
      if (page === 1 && Date.now() - lastCacheWriteRef.current > CACHE_WRITE_MIN_INTERVAL_MS) {
        try {
          localStorage.setItem(CACHE_KEY, JSON.stringify(data));
          lastCacheWriteRef.current = Date.now();
        } catch { /* quota */ }
      }
    } catch (err) {
      if (requestVersion !== requestVersionRef.current) return;
      if ((err as Error).name === 'AbortError') return;
      const msg = (err as Error).message ?? '';
      const isConfigurationError = msg.includes('not configured');
      const isRateLimit = msg.includes('429');
      if (isConfigurationError) {
        setError(msg);
        return;
      }
      // Retry silently if rate-limited or if we already have data to display
      if (isRateLimit || coinsRef.current.length > 0) {
        retryRef.current = setTimeout(() => fetchRef.current(), isRateLimit ? 15_000 : 10_000);
        return;
      }
      setError('Unable to load prices. Showing cached data.');
    } finally {
      if (requestVersion === requestVersionRef.current) setLoading(false);
    }
  }, [perPage, page, currency]);

  fetchRef.current = fetchCoins;

  const refresh = useCallback(async () => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = setInterval(() => { if (!document.hidden) void fetchCoins(); }, intervalMs);
    }
    await fetchCoins();
  }, [fetchCoins, intervalMs]);

  useEffect(() => {
    setLoading(true);
    fetchCoins();
    // App in background: il tick e' sprecato (nessuno guarda i prezzi) e tiene
    // accesa la radio. Al rientro in foreground App.tsx chiama gia' refresh().
    timerRef.current = setInterval(() => { if (!document.hidden) void fetchCoins(); }, intervalMs);
    return () => {
      requestVersionRef.current += 1;
      if (timerRef.current !== null) clearInterval(timerRef.current);
      timerRef.current = null;
      if (retryRef.current !== null) clearTimeout(retryRef.current);
      retryRef.current = null;
      abortRef.current?.abort();
    };
  }, [fetchCoins, intervalMs]);

  return { coins, loading, error, lastUpdated, refresh };
}
