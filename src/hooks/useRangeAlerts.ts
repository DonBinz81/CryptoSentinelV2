import { useCallback, useState } from 'react';
import type { RangeAlert } from '../types';

const STORAGE_KEY = 'cryptosentinel_range_alerts';

function loadRangeAlerts(): RangeAlert[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as RangeAlert[] : [];
  } catch {
    return [];
  }
}

function saveRangeAlerts(alerts: RangeAlert[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
  } catch {
    // Keep runtime state when browser storage is unavailable.
  }
}

export function useRangeAlerts() {
  const [rangeAlerts, setRangeAlerts] = useState<RangeAlert[]>(loadRangeAlerts);

  const addRangeAlert = useCallback((
    alert: Omit<RangeAlert, 'id' | 'isInsideRange' | 'lastNotifiedAt' | 'createdAt'>,
  ) => {
    const newAlert: RangeAlert = {
      ...alert,
      id: `range-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      isInsideRange: null,
      lastNotifiedAt: null,
      createdAt: Date.now(),
    };
    setRangeAlerts((prev) => {
      const next = [...prev, newAlert];
      saveRangeAlerts(next);
      return next;
    });
  }, []);

  const removeRangeAlert = useCallback((id: string) => {
    setRangeAlerts((prev) => {
      const next = prev.filter((alert) => alert.id !== id);
      saveRangeAlerts(next);
      return next;
    });
  }, []);

  const editRangeAlert = useCallback((id: string, minPrice: number, maxPrice: number, note?: string) => {
    setRangeAlerts((prev) => {
      const next = prev.map((alert) =>
        alert.id === id
          ? {
              ...alert,
              minPrice,
              maxPrice,
              note: note !== undefined ? note : alert.note,
              isInsideRange: null,
              lastNotifiedAt: null,
            }
          : alert
      );
      saveRangeAlerts(next);
      return next;
    });
  }, []);

  const toggleRangeAlert = useCallback((id: string) => {
    setRangeAlerts((prev) => {
      const next = prev.map((alert) =>
        alert.id === id ? { ...alert, active: !(alert.active ?? true) } : alert
      );
      saveRangeAlerts(next);
      return next;
    });
  }, []);

  const clearRangeAlerts = useCallback(() => {
    setRangeAlerts([]);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  return {
    rangeAlerts,
    addRangeAlert,
    removeRangeAlert,
    editRangeAlert,
    toggleRangeAlert,
    clearRangeAlerts,
  };
}
