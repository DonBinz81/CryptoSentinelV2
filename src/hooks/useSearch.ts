import { useState, useEffect, useRef } from 'react';
import type { Coin } from '../types';
import { searchMarkets } from '../services/marketData';

export function useSearch(query: string, currency = 'usd') {
  const [results, setResults] = useState<Coin[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestVersionRef = useRef(0);

  useEffect(() => {
    const requestVersion = ++requestVersionRef.current;
    if (timerRef.current) clearTimeout(timerRef.current);
    abortRef.current?.abort();

    if (!query.trim()) {
      setResults([]);
      setSearching(false);
      setError(null);
      return;
    }

    setSearching(true);

    timerRef.current = setTimeout(async () => {
      abortRef.current = new AbortController();
      const { signal } = abortRef.current;

      try {
        const nextResults = await searchMarkets(query.trim(), currency, signal);
        if (requestVersion !== requestVersionRef.current) return;
        setResults(nextResults);
        setError(null);
      } catch (err) {
        if (requestVersion !== requestVersionRef.current) return;
        if ((err as Error).name !== 'AbortError') {
          setResults([]);
          setError((err as Error).message || 'Market data search failed');
        }
      } finally {
        if (requestVersion === requestVersionRef.current) setSearching(false);
      }
    }, 400);

    return () => {
      requestVersionRef.current += 1;
      if (timerRef.current) clearTimeout(timerRef.current);
      abortRef.current?.abort();
    };
  }, [query, currency]);

  return { results, searching, error };
}
