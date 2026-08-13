import { useState, useCallback } from 'react';

export type Currency = 'usd' | 'eur' | 'btc';

const STORAGE_KEY = 'cryptosentinel_currency';

export function useCurrency() {
  const [currency, setCurrency] = useState<Currency>(() => {
    const s = localStorage.getItem(STORAGE_KEY);
    if (s === 'eur' || s === 'btc') return s;
    return 'usd';
  });

  const changeCurrency = useCallback((c: Currency) => {
    setCurrency(c);
    localStorage.setItem(STORAGE_KEY, c);
  }, []);

  return { currency, changeCurrency };
}
