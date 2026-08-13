import { useCallback, useState } from 'react';
import type { AlertDirection, AlertHistoryEntry, PriceAlert, PriceAlertTriggerOptions } from '../types';

const STORAGE_KEY = 'cryptosentinel_alerts';
const HISTORY_KEY = 'cryptosentinel_alert_history';

function normalizeAlert(alert: PriceAlert): PriceAlert {
  return {
    ...alert,
    rearmPercent: Math.max(0, Number(alert.rearmPercent ?? 0)),
    keepActiveAfterTrigger: alert.keepActiveAfterTrigger === true,
    crossingOnly: alert.crossingOnly === true,
  };
}

function loadAlerts(): PriceAlert[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PriceAlert[]).map(normalizeAlert) : [];
  } catch {
    return [];
  }
}

function saveAlerts(alerts: PriceAlert[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
  } catch {
    // Keep runtime state when browser storage is unavailable.
  }
}

function loadHistory(): AlertHistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) as AlertHistoryEntry[] : [];
  } catch {
    return [];
  }
}

export function useAlerts() {
  const [alerts, setAlerts] = useState<PriceAlert[]>(loadAlerts);
  const [history, setHistory] = useState<AlertHistoryEntry[]>(loadHistory);

  const addAlert = useCallback((alertData: Omit<PriceAlert, 'id' | 'triggered' | 'createdAt'>) => {
    const newAlert: PriceAlert = {
      ...alertData,
      rearmPercent: Math.max(0, Number(alertData.rearmPercent ?? 0)),
      keepActiveAfterTrigger: alertData.keepActiveAfterTrigger === true,
      crossingOnly: alertData.crossingOnly === true,
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      triggered: false,
      createdAt: Date.now(),
    };
    setAlerts((prev) => {
      const next = [...prev, newAlert];
      saveAlerts(next);
      return next;
    });
  }, []);

  const removeAlert = useCallback((id: string) => {
    setAlerts((prev) => {
      const next = prev.filter((alert) => alert.id !== id);
      saveAlerts(next);
      return next;
    });
  }, []);

  const resetAlert = useCallback((id: string) => {
    setAlerts((prev) => {
      const next = prev.map((alert) =>
        alert.id === id
          ? {
              ...alert,
              triggered: false,
              triggeredAt: undefined,
              lastTriggeredPrice: undefined,
              lastCrossDirection: undefined,
              waitingForRearm: false,
            }
          : alert
      );
      saveAlerts(next);
      return next;
    });
  }, []);

  const editAlert = useCallback((
    id: string,
    threshold: number,
    direction: AlertDirection,
    percentChange?: number,
    note?: string,
    triggerOptions?: PriceAlertTriggerOptions,
  ) => {
    setAlerts((prev) => {
      const next = prev.map((alert) =>
        alert.id === id
          ? {
              ...alert,
              threshold,
              direction,
              percentChange,
              note: note !== undefined ? note : alert.note,
              crossingOnly: triggerOptions?.crossingOnly ?? alert.crossingOnly,
              keepActiveAfterTrigger: triggerOptions?.keepActiveAfterTrigger ?? alert.keepActiveAfterTrigger,
              rearmPercent: Math.max(0, Number(triggerOptions?.rearmPercent ?? alert.rearmPercent ?? 0)),
              triggered: false,
              triggeredAt: undefined,
              lastTriggeredPrice: undefined,
              lastCrossDirection: undefined,
              waitingForRearm: false,
              lastObservedPrice: undefined,
            }
          : alert
      );
      saveAlerts(next);
      return next;
    });
  }, []);

  const toggleAlert = useCallback((id: string) => {
    setAlerts((prev) => {
      const next = prev.map((alert) =>
        alert.id === id ? { ...alert, active: !(alert.active ?? true) } : alert
      );
      saveAlerts(next);
      return next;
    });
  }, []);

  const clearAlerts = useCallback(() => {
    setAlerts([]);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
    localStorage.removeItem(HISTORY_KEY);
  }, []);

  const evaluateAlerts = useCallback((pricesByCoinId: Map<string, number>) => {
    const firedEntries: AlertHistoryEntry[] = [];
    let changed = false;

    setAlerts((prev) => {
      const now = Date.now();
      const next = prev.map((alert) => {
        const price = pricesByCoinId.get(alert.coinId);
        if (price == null || price <= 0 || alert.active === false) return alert;
        if (alert.triggered && !alert.keepActiveAfterTrigger) return alert;

        const previousPrice = alert.lastObservedPrice;
        let updated: PriceAlert = alert;

        if (alert.crossingOnly) {
          if (previousPrice == null || previousPrice <= 0) {
            changed = true;
            return { ...alert, lastObservedPrice: price };
          }

          const rearmPercent = Math.max(0, Number(alert.rearmPercent ?? 0));
          const rearmBand = alert.threshold * (rearmPercent / 100);
          const insideRearmBand = price >= alert.threshold - rearmBand && price <= alert.threshold + rearmBand;

          if (alert.waitingForRearm && rearmPercent > 0 && insideRearmBand) {
            changed = true;
            return { ...alert, lastObservedPrice: price };
          }

          const rearmed = alert.waitingForRearm && (rearmPercent === 0 || !insideRearmBand);
          if (rearmed) {
            changed = true;
            return { ...alert, waitingForRearm: false, lastObservedPrice: price };
          }
          const baseAlert = rearmed ? { ...alert, waitingForRearm: false } : alert;
          const crossedUp = previousPrice < alert.threshold && price >= alert.threshold;
          const crossedDown = previousPrice > alert.threshold && price <= alert.threshold;
          const crossDirection = crossedUp ? 'up' : crossedDown ? 'down' : undefined;

          if (!crossDirection) {
            changed = changed || rearmed || previousPrice !== price;
            return { ...baseAlert, lastObservedPrice: price };
          }

          firedEntries.push({
            id: `${now}-${alert.id}`,
            coinId: alert.coinId,
            coinName: alert.coinName,
            coinSymbol: alert.coinSymbol,
            coinImage: alert.coinImage,
            direction: crossDirection === 'up' ? 'above' : 'below',
            crossDirection,
            threshold: alert.threshold,
            triggeredPrice: price,
            triggeredAt: now,
          });

          updated = {
            ...baseAlert,
            triggered: !alert.keepActiveAfterTrigger,
            triggeredAt: now,
            lastTriggeredPrice: price,
            lastCrossDirection: crossDirection,
            waitingForRearm: alert.keepActiveAfterTrigger && rearmPercent > 0,
            lastObservedPrice: price,
          };
          changed = true;
          return updated;
        }

        const fire = (alert.direction === 'above' && price >= alert.threshold) ||
          (alert.direction === 'below' && price <= alert.threshold);

        if (!fire) {
          if (previousPrice !== price) {
            changed = true;
            return { ...alert, lastObservedPrice: price };
          }
          return alert;
        }

        firedEntries.push({
          id: `${now}-${alert.id}`,
          coinId: alert.coinId,
          coinName: alert.coinName,
          coinSymbol: alert.coinSymbol,
          coinImage: alert.coinImage,
          direction: alert.direction,
          threshold: alert.threshold,
          triggeredPrice: price,
          triggeredAt: now,
        });

        changed = true;
        return {
          ...alert,
          triggered: true,
          triggeredAt: now,
          lastTriggeredPrice: price,
          lastObservedPrice: price,
        };
      });

      if (changed) saveAlerts(next);
      return changed ? next : prev;
    });

    if (firedEntries.length > 0) {
      setHistory((prev) => {
        const next = [...firedEntries, ...prev].slice(0, 50);
        localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
        return next;
      });
    }
  }, []);

  return {
    alerts,
    addAlert,
    removeAlert,
    resetAlert,
    editAlert,
    toggleAlert,
    clearAlerts,
    evaluateAlerts,
    history,
    clearHistory,
  };
}
