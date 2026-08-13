import { useState, useEffect, useRef } from 'react';
import type { Coin } from '../types';
import { fetchMarkets } from '../services/marketData';

function unresolvedFavorite(id: string): Coin {
  return {
    id,
    symbol: id,
    name: id
      .split('-')
      .map(part => part ? part[0].toUpperCase() + part.slice(1) : part)
      .join(' '),
    image: '/crypto-icon.svg',
    current_price: 0,
    price_change_percentage_24h: 0,
    market_cap: 0,
    market_cap_rank: null,
    total_volume: 0,
    high_24h: 0,
    low_24h: 0,
  };
}

export function useFavoriteCoinsData(
  favorites: Set<string>,
  intervalMs: number,
  currency: string
): Coin[] {
  const [favoriteData, setFavoriteData] = useState<Map<string, Coin>>(new Map());
  const abortRef = useRef<AbortController | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestVersionRef = useRef(0);

  const favoriteIds = [...favorites];
  const favoritesKey = [...favoriteIds].sort().join(',');

  useEffect(() => {
    if (favoriteIds.length === 0) {
      setFavoriteData(new Map());
      return;
    }

    const doFetch = async () => {
      const requestVersion = ++requestVersionRef.current;
      if (retryRef.current !== null) {
        clearTimeout(retryRef.current);
        retryRef.current = null;
      }
      abortRef.current?.abort();
      abortRef.current = new AbortController();
      try {
        const data = await fetchMarkets(
          favoriteIds.length,
          1,
          currency,
          abortRef.current.signal,
          favoriteIds,
        );
        if (requestVersion !== requestVersionRef.current) return;
        setFavoriteData((previous) => {
          const next = new Map(
            [...previous].filter(([id]) => favorites.has(id)),
          );
          for (const coin of data) next.set(coin.id, coin);
          return next;
        });
      } catch (err) {
        if (requestVersion !== requestVersionRef.current) return;
        if ((err as Error).name !== 'AbortError') {
          retryRef.current = setTimeout(doFetch, 5_000);
        }
      }
    };

    doFetch();
    const timer = setInterval(doFetch, intervalMs);
    return () => {
      requestVersionRef.current += 1;
      clearInterval(timer);
      if (retryRef.current !== null) clearTimeout(retryRef.current);
      retryRef.current = null;
      abortRef.current?.abort();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [favoritesKey, currency, intervalMs]);

  return favoriteIds.map(id => favoriteData.get(id) ?? unresolvedFavorite(id));
}
