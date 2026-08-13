import { useRef, useState, useCallback, useEffect } from 'react';
import { hapticMedium } from '../utils/haptics';

const TRIGGER = 60;   // px visibili per scattare il refresh
const MAX = 88;       // altezza massima indicatore
const DAMPING = 0.45; // resistenza al drag

// Manipola il DOM direttamente per evitare re-render durante il pull
function setH(el: HTMLElement | null, h: number, animate = false) {
  if (!el) return;
  el.style.transition = animate ? 'height 220ms cubic-bezier(.25,.46,.45,.94)' : 'none';
  el.style.height = `${h}px`;
}

export function usePullToRefresh(onRefresh: () => Promise<void> | void, disabled = false) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const indicatorRef = useRef<HTMLDivElement | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const s = useRef({ startY: null as number | null, pullY: 0, refreshing: false });
  const disabledRef = useRef(disabled);
  disabledRef.current = disabled;

  const onTouchStart = useCallback((e: TouchEvent) => {
    const el = containerRef.current;
    if (!el || el.scrollTop > 0 || s.current.refreshing || disabledRef.current) return;
    s.current.startY = e.touches[0].clientY;
    s.current.pullY = 0;
  }, []);

  const onTouchMove = useCallback((e: TouchEvent) => {
    const el = containerRef.current;
    if (!el || s.current.startY === null || disabledRef.current) return;
    if (el.scrollTop > 0) {
      s.current.startY = null;
      s.current.pullY = 0;
      setH(indicatorRef.current, 0, true);
      return;
    }
    const dy = e.touches[0].clientY - s.current.startY;
    if (dy <= 0) return;
    e.preventDefault();
    const v = Math.min(dy * DAMPING, MAX);
    s.current.pullY = v;
    setH(indicatorRef.current, v);
    // ruota la freccia quando si supera la soglia
    const arrow = indicatorRef.current?.querySelector<HTMLElement>('[data-ptr-arrow]');
    if (arrow) {
      arrow.style.transform = v >= TRIGGER ? 'rotate(180deg)' : 'rotate(0deg)';
      arrow.style.color = v >= TRIGGER ? 'rgb(59 130 246)' : 'rgb(156 163 175)';
    }
  }, []);

  const onTouchEnd = useCallback(async () => {
    const dist = s.current.pullY;
    s.current.startY = null;
    s.current.pullY = 0;

    if (dist >= TRIGGER && !s.current.refreshing) {
      hapticMedium();
      setH(indicatorRef.current, 48, true);
      s.current.refreshing = true;
      setIsRefreshing(true);
      try { await onRefresh(); } finally {
        s.current.refreshing = false;
        setIsRefreshing(false);
        setH(indicatorRef.current, 0, true);
      }
    } else {
      setH(indicatorRef.current, 0, true);
    }
  }, [onRefresh]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener('touchstart', onTouchStart, { passive: true });
    el.addEventListener('touchmove', onTouchMove, { passive: false });
    el.addEventListener('touchend', onTouchEnd);
    el.addEventListener('touchcancel', onTouchEnd);
    return () => {
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchmove', onTouchMove);
      el.removeEventListener('touchend', onTouchEnd);
      el.removeEventListener('touchcancel', onTouchEnd);
    };
  }, [onTouchStart, onTouchMove, onTouchEnd]);

  return { containerRef, indicatorRef, isRefreshing };
}
