import { useState, useCallback } from 'react';

const STORAGE_KEY = 'cryptosentinel_favorites';

function loadFavorites(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as string[]);
  } catch {
    return new Set();
  }
}

function saveFavorites(favs: Set<string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...favs]));
  } catch { /* quota */ }
}

export function useFavorites() {
  const [favorites, setFavorites] = useState<Set<string>>(loadFavorites);

  const toggle = useCallback((coinId: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(coinId)) {
        next.delete(coinId);
      } else {
        next.add(coinId);
      }
      saveFavorites(next);
      return next;
    });
  }, []);

  const isFavorite = useCallback((coinId: string) => favorites.has(coinId), [favorites]);

  const clear = useCallback(() => {
    setFavorites(new Set());
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  return { favorites, toggle, isFavorite, clear };
}
