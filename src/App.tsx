import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import type { Coin, PriceAlertTriggerOptions } from './types';
import { useCryptoData, type PerPage } from './hooks/useCryptoData';
import { useFavorites } from './hooks/useFavorites';
import { useFavoriteCoinsData } from './hooks/useFavoriteCoinsData';
import { useAlerts } from './hooks/useAlerts';
import { useRangeAlerts } from './hooks/useRangeAlerts';
import { useCurrency } from './hooks/useCurrency';
import {
  dismissFavoritePushAlert,
  getNotificationPermission,
  initNotifications,
  refreshPendingFavoritePushAlerts,
  subscribeFavoritePushAlerts,
  syncFavAlertsNative,
  type FavAlertData,
} from './utils/notifications';
import { syncAlertsToBackend } from './utils/alertSync';
import { isBatteryBannerDismissed } from './utils/energySaving';
import { onDownloadComplete, checkForUpdates, type UpdateResult } from './utils/update';
import { useSearch } from './hooks/useSearch';
import { usePullToRefresh } from './hooks/usePullToRefresh';
import { hapticLight } from './utils/haptics';
import UpdateNotification from './components/UpdateNotification';
import Navbar, { type Tab } from './components/Navbar';
import LogoLighthouse from './components/LogoLighthouse';
import CoinCard from './components/CoinCard';
import AlertModal from './components/AlertModal';
import AlertsTab from './components/AlertsTab';
import NotificationBanner from './components/NotificationBanner';
import EnergySavingBanner from './components/EnergySavingBanner';
import SettingsTab from './components/SettingsTab';
import FavMovePopup from './components/FavMovePopup';
import CoinChartSheet from './components/CoinChartSheet';
import SplashOverlay, { shouldShowSplash } from './components/SplashOverlay';
import AgentTab from './components/AgentTab';
import { fetchAgentWatchlist, updateAgentWatchlist, fetchSpotView, fetchPerpView, type SpotPositionView, type PerpPositionView } from './services/agentApi';
import {
  adminGetSupportNotifications,
  getSupportNotifications,
  type SupportTicketSummary,
} from './services/supportApi';
import { FALLBACK_ELIGIBLE_SYMBOLS, toEligibleSymbolSet } from './utils/eligibleTokens';

const INTERVAL_KEY = 'cryptosentinel_refresh_interval';
const PERPAGE_KEY = 'cryptosentinel_perpage';
const SLIDER_RANGE_KEY = 'cryptosentinel_alert_slider_range';
const FAV_UP_KEY = 'cs_fav_up_pct';
const FAV_DOWN_KEY = 'cs_fav_down_pct';
const RANK_ANIM_KEY = 'cs_rank_anim_topn';
const ADMIN_TOKEN_KEY = 'cs_agent_admin_token';

type SortBy = 'rank' | 'change' | '7d' | 'volume' | 'price';
type TimeFrame = '1h' | '24h' | '7d';
type SupportMode = 'user' | 'admin';

type SupportHomeNotice = {
  userCount: number;
  adminCount: number;
  latestTicket: SupportTicketSummary | null;
  latestMode: SupportMode;
};

function sortCoins(coins: Coin[], sortBy: SortBy, sortDesc: boolean): Coin[] {
  const sorted = [...coins];
  if (sortBy === 'rank') {
    sorted.sort((a, b) => {
      const ar = a.market_cap_rank ?? 9999;
      const br = b.market_cap_rank ?? 9999;
      return sortDesc ? ar - br : br - ar;
    });
  } else if (sortBy === '7d') {
    sorted.sort((a, b) => {
      const av = a.price_change_percentage_7d_in_currency ?? 0;
      const bv = b.price_change_percentage_7d_in_currency ?? 0;
      return sortDesc ? bv - av : av - bv;
    });
  } else {
    const key = sortBy === 'change' ? 'price_change_percentage_24h'
      : sortBy === 'volume' ? 'total_volume'
      : 'current_price';
    sorted.sort((a, b) => sortDesc ? b[key] - a[key] : a[key] - b[key]);
  }
  return sorted;
}

export default function App() {
  const [showSplash, setShowSplash] = useState(shouldShowSplash);
  const [tab, setTab] = useState<Tab>('dashboard');
  const [search, setSearch] = useState('');
  const [selectedCoin, setSelectedCoin] = useState<Coin | null>(null);
  const [notifPerm, setNotifPerm] = useState<NotificationPermission>('default');
  const [batteryDismissed, setBatteryDismissed] = useState(isBatteryBannerDismissed);
  const [dlState, setDlState] = useState<'idle' | 'downloading' | 'done' | 'error'>('idle');
  const [perPage, setPerPage] = useState<PerPage>(() => {
    const stored = parseInt(localStorage.getItem(PERPAGE_KEY) || '50', 10);
    return ([50, 100, 200, 400, 600].includes(stored) ? stored : 50) as PerPage;
  });
  const [timeFrame, setTimeFrame] = useState<TimeFrame>('24h');
  const [page, setPage] = useState(1);
  const [availableUpdate, setAvailableUpdate] = useState<UpdateResult | null>(null);
  const [sortBy, setSortBy] = useState<SortBy>('rank');
  const [sortDesc, setSortDesc] = useState(true);
  const [favoriteSortBy, setFavoriteSortBy] = useState<SortBy>('rank');
  const [favoriteSortDesc, setFavoriteSortDesc] = useState(true);
  const [favoriteTimeFrame, setFavoriteTimeFrame] = useState<TimeFrame>('24h');
  const lastUpdateCheckRef = useRef<number>(0);
  const favSyncRef = useRef({ coinsJson: '[]', upPct: 0, downPct: 0, refPricesJson: '{}', currency: 'usd' });

  // dismiss è session-only: non si carica da localStorage, così il riavvio mostra sempre la freccia
  const [dismissedBuild, setDismissedBuild] = useState<string | null>(null);
  const [snoozedBuild, setSnoozedBuild] = useState<string | null>(() =>
    localStorage.getItem('cs_snoozed_build')
  );
  const [snoozedUntil, setSnoozedUntil] = useState<number>(() =>
    Number(localStorage.getItem('cs_snoozed_until') ?? 0)
  );

  useEffect(() => {
    if (!snoozedUntil || Date.now() > snoozedUntil) return;
    const t = setTimeout(() => setSnoozedUntil(0), snoozedUntil - Date.now());
    return () => clearTimeout(t);
  }, [snoozedUntil]);

  const isUpdateVisible = useMemo(() =>
    availableUpdate != null &&
    availableUpdate.buildNumber !== dismissedBuild &&
    (snoozedBuild !== availableUpdate.buildNumber || Date.now() > snoozedUntil),
    [availableUpdate, dismissedBuild, snoozedBuild, snoozedUntil]
  );

  const handleIgnoreUpdate = useCallback(() => {
    const build = availableUpdate?.buildNumber ?? '_';
    setDismissedBuild(build); // session-only, non persiste in localStorage
  }, [availableUpdate]);

  const handleSnoozeUpdate = useCallback(() => {
    const build = availableUpdate?.buildNumber ?? '_';
    const until = Date.now() + 4 * 60 * 60 * 1000;
    localStorage.setItem('cs_snoozed_build', build);
    localStorage.setItem('cs_snoozed_until', String(until));
    setSnoozedBuild(build);
    setSnoozedUntil(until);
  }, [availableUpdate]);

  const handleUpdateDone = useCallback(() => {
    setAvailableUpdate(null);
    setDlState('idle');
    localStorage.removeItem('cs_snoozed_build');
    localStorage.removeItem('cs_snoozed_until');
    setDismissedBuild(null);
    setSnoozedBuild(null);
    setSnoozedUntil(0);
  }, []);

  const runUpdateCheck = useCallback(async () => {
    lastUpdateCheckRef.current = Date.now();
    try {
      const result = await checkForUpdates(__APP_BUILD_NUMBER__);
      if (result.available) setAvailableUpdate(result);
    } catch {
      // Rete non ancora pronta (primo avvio post-installazione): riprova dopo 15s
      lastUpdateCheckRef.current = 0;
      setTimeout(async () => {
        try {
          const result = await checkForUpdates(__APP_BUILD_NUMBER__);
          if (result.available) setAvailableUpdate(result);
        } catch { /* silent */ }
      }, 15_000);
    }
  }, []);

  useEffect(() => {
    const unsubscribeFavPush = subscribeFavoritePushAlerts(({ alert, openFavorites }) => {
      setPendingFavAlerts((prev) => new Map(prev).set(alert.coinId, alert));
      if (openFavorites) setTab('favorites');
    });
    initNotifications();
    refreshPendingFavoritePushAlerts();
    getNotificationPermission().then(setNotifPerm);

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        refreshPendingFavoritePushAlerts();
        getNotificationPermission().then(setNotifPerm);
        if (Date.now() - lastUpdateCheckRef.current > 30 * 60 * 1000) {
          runUpdateCheck();
        }
      } else {
        const s = favSyncRef.current;
        syncFavAlertsNative(s.coinsJson, s.upPct, s.downPct, s.refPricesJson, s.currency);
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    let unsubDl: (() => void) | null = null;
    onDownloadComplete((ok) => setDlState(ok ? 'done' : 'error')).then((fn) => { unsubDl = fn; });

    const updateTimer = setTimeout(runUpdateCheck, 3000);
    const updateInterval = setInterval(runUpdateCheck, 30 * 60 * 1000);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      unsubDl?.();
      clearTimeout(updateTimer);
      clearInterval(updateInterval);
      unsubscribeFavPush();
    };
  }, [runUpdateCheck]);

  const [refreshInterval, setRefreshInterval] = useState<number>(() => {
    return parseInt(localStorage.getItem(INTERVAL_KEY) || '30000', 10);
  });

  const [sliderRange, setSliderRange] = useState<number>(() => {
    return parseInt(localStorage.getItem(SLIDER_RANGE_KEY) || '20', 10);
  });

  const handleSliderRangeChange = useCallback((n: number) => {
    setSliderRange(n);
    localStorage.setItem(SLIDER_RANGE_KEY, String(n));
  }, []);

  const [favMoveUpPct, setFavMoveUpPct] = useState<number>(() =>
    Number(localStorage.getItem(FAV_UP_KEY) ?? 0)
  );
  const [favMoveDownPct, setFavMoveDownPct] = useState<number>(() =>
    Number(localStorage.getItem(FAV_DOWN_KEY) ?? 0)
  );

  const handleFavMoveUpPctChange = useCallback((n: number) => {
    setFavMoveUpPct(n);
    localStorage.setItem(FAV_UP_KEY, String(n));
  }, []);

  const handleFavMoveDownPctChange = useCallback((n: number) => {
    setFavMoveDownPct(n);
    localStorage.setItem(FAV_DOWN_KEY, String(n));
  }, []);

  const [rankAnimTopN, setRankAnimTopN] = useState<number>(() =>
    Number(localStorage.getItem(RANK_ANIM_KEY) ?? 100)
  );
  const handleRankAnimTopNChange = useCallback((n: number) => {
    setRankAnimTopN(n);
    localStorage.setItem(RANK_ANIM_KEY, String(n));
  }, []);

  const [pendingFavAlerts, setPendingFavAlerts] = useState<Map<string, FavAlertData>>(new Map());
  const [selectedFavAlert, setSelectedFavAlert] = useState<FavAlertData | null>(null);
  const [chartCoin, setChartCoin] = useState<Coin | null>(null);
  const [adminToken, setAdminToken] = useState(() => localStorage.getItem(ADMIN_TOKEN_KEY) ?? '');
  const [eligibleTokens, setEligibleTokens] = useState<string[]>(() => FALLBACK_ELIGIBLE_SYMBOLS);
  const [selectedAiSymbols, setSelectedAiSymbols] = useState<Set<string>>(() => new Set());
  const [aiWatchlistSaving, setAiWatchlistSaving] = useState(false);
  const [aiWatchlistError, setAiWatchlistError] = useState('');
  const eligibleSymbols = useMemo(() => toEligibleSymbolSet(eligibleTokens), [eligibleTokens]);
  const [openSpotPositions, setOpenSpotPositions] = useState<SpotPositionView[]>([]);
  const [openPerpPositions, setOpenPerpPositions] = useState<PerpPositionView[]>([]);
  const [supportNotice, setSupportNotice] = useState<SupportHomeNotice>({
    userCount: 0,
    adminCount: 0,
    latestTicket: null,
    latestMode: 'user',
  });
  const [supportModeRequest, setSupportModeRequest] = useState<SupportMode>('user');
  const supportNoticeRef = useRef(supportNotice);
  supportNoticeRef.current = supportNotice;

  // Mappa symbol → aiState: spot (blu) > perp long (verde) > perp short (rosso) > analysis (giallo) > inactive
  const aiStateMap = useMemo<Map<string, 'spot' | 'long' | 'short' | 'analysis' | 'inactive'>>(() => {
    const map = new Map<string, 'spot' | 'long' | 'short' | 'analysis' | 'inactive'>();
    for (const p of openSpotPositions) {
      const sym = p.asset.replace(/USDT$/i, '').toUpperCase();
      map.set(sym, 'spot');
    }
    for (const p of openPerpPositions) {
      const sym = p.asset.replace(/USDT$/i, '').toUpperCase();
      if (!map.has(sym)) map.set(sym, p.side === 'short' ? 'short' : 'long');
    }
    for (const sym of selectedAiSymbols) {
      if (!map.has(sym)) map.set(sym, 'analysis');
    }
    return map;
  }, [openSpotPositions, openPerpPositions, selectedAiSymbols]);

  const handleChartTap = useCallback((coin: Coin) => {
    setChartCoin(coin);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchAgentWatchlist()
      .then((response) => {
        if (cancelled) return;
        setEligibleTokens(response.eligible_tokens.length > 0 ? response.eligible_tokens : FALLBACK_ELIGIBLE_SYMBOLS);
        setSelectedAiSymbols(toEligibleSymbolSet(response.selected_tokens));
      })
      .catch(() => {
        if (!cancelled) {
          setEligibleTokens(FALLBACK_ELIGIBLE_SYMBOLS);
          setSelectedAiSymbols(new Set());
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Fetch posizioni aperte ogni 45s per aggiornare le icone AI
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      Promise.all([fetchSpotView(), fetchPerpView()])
        .then(([sv, pv]) => {
          if (cancelled) return;
          setOpenSpotPositions(sv.open_positions);
          setOpenPerpPositions(pv.open_positions);
        })
        .catch(() => {});
    };
    load();
    const timer = window.setInterval(load, 45_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  const refreshSupportNotice = useCallback(async () => {
    try {
      const user = await getSupportNotifications();
      let adminCount = 0;
      let adminLatest: SupportTicketSummary | null = null;
      if (adminToken) {
        try {
          const admin = await adminGetSupportNotifications(adminToken);
          adminCount = admin.unread_count;
          adminLatest = admin.latest_ticket;
        } catch {
          adminCount = 0;
          adminLatest = null;
        }
      }
      setSupportNotice({
        userCount: user.unread_count,
        adminCount,
        latestTicket: adminLatest ?? user.latest_ticket,
        latestMode: adminLatest ? 'admin' : 'user',
      });
    } catch {
      setSupportNotice({
        userCount: 0,
        adminCount: 0,
        latestTicket: null,
        latestMode: 'user',
      });
    }
  }, [adminToken]);

  useEffect(() => {
    void refreshSupportNotice();
    const timer = window.setInterval(() => void refreshSupportNotice(), 60_000);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void refreshSupportNotice();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [refreshSupportNotice]);

  const handleDismissFavAlert = useCallback((coinId: string) => {
    dismissFavoritePushAlert(coinId);
    setPendingFavAlerts((prev) => {
      const next = new Map(prev);
      next.delete(coinId);
      return next;
    });
    setSelectedFavAlert(null);
  }, []);

  // "Ho capito" globale: azzera tutti gli avvisi pendenti e ricalibra i riferimenti
  // al prezzo attuale (svuotando la cache: il prossimo sync li reimposta da ora).
  const handleAckAllFavAlerts = useCallback(() => {
    setPendingFavAlerts((prev) => {
      prev.forEach((_, coinId) => dismissFavoritePushAlert(coinId));
      return new Map();
    });
    setSelectedFavAlert(null);
    try { localStorage.setItem('cs_fav_ref_prices', '{}'); } catch { /* ignore */ }
  }, []);

  // Mute per-coin nei preferiti: la coin resta nei preferiti ma non genera avvisi di movimento.
  const [mutedFavorites, setMutedFavorites] = useState<Set<string>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem('cs_muted_favorites') ?? '[]') as string[]); }
    catch { return new Set(); }
  });
  const handleToggleMuteFavorite = useCallback((coin: Coin) => {
    setMutedFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(coin.id)) next.delete(coin.id);
      else next.add(coin.id);
      try { localStorage.setItem('cs_muted_favorites', JSON.stringify([...next])); } catch { /* ignore */ }
      return next;
    });
  }, []);

  const handleToggleAiSymbol = useCallback(async (symbol: string) => {
    const normalized = symbol.toUpperCase();
    if (!eligibleSymbols.has(normalized)) return;
    if (!adminToken) {
      setAiWatchlistError('Admin token richiesto nella tab Agente.');
      setTab('agent');
      return;
    }
    const previous = new Set(selectedAiSymbols);
    const next = new Set(selectedAiSymbols);
    if (next.has(normalized)) next.delete(normalized);
    else next.add(normalized);
    setSelectedAiSymbols(next);
    setAiWatchlistSaving(true);
    setAiWatchlistError('');
    try {
      const response = await updateAgentWatchlist(Array.from(next), adminToken);
      setEligibleTokens(response.eligible_tokens.length > 0 ? response.eligible_tokens : FALLBACK_ELIGIBLE_SYMBOLS);
      setSelectedAiSymbols(toEligibleSymbolSet(response.selected_tokens));
    } catch (err) {
      setSelectedAiSymbols(previous);
      setAiWatchlistError(err instanceof Error ? err.message : 'Watchlist update failed');
    } finally {
      setAiWatchlistSaving(false);
    }
  }, [adminToken, eligibleSymbols, selectedAiSymbols]);

  const handleToggleAiCoin = useCallback((coin: Coin) => {
    void handleToggleAiSymbol(coin.symbol);
  }, [handleToggleAiSymbol]);

  const handleAdminTokenChange = useCallback((value: string) => {
    setAdminToken(value);
    if (value) {
      localStorage.setItem(ADMIN_TOKEN_KEY, value);
    } else {
      localStorage.removeItem(ADMIN_TOKEN_KEY);
    }
  }, []);

  const { currency, changeCurrency } = useCurrency();
  const { coins, loading, error, lastUpdated, refresh } = useCryptoData(refreshInterval, perPage, page, currency);

  const prevRanksRef = useRef<Map<string, number>>(new Map());
  const [rankDeltas, setRankDeltas] = useState<Map<string, number>>(new Map());

  useEffect(() => {
    prevRanksRef.current = new Map();
  }, [currency, perPage, page]);

  useEffect(() => {
    if (coins.length === 0) return;

    if (prevRanksRef.current.size === 0) {
      for (const coin of coins) {
        if (coin.market_cap_rank != null) prevRanksRef.current.set(coin.id, coin.market_cap_rank);
      }
      return;
    }

    const newDeltas = new Map<string, number>();
    if (rankAnimTopN > 0) {
      for (const coin of coins) {
        const prev = prevRanksRef.current.get(coin.id);
        const curr = coin.market_cap_rank;
        if (prev != null && curr != null && prev !== curr && curr <= rankAnimTopN) {
          newDeltas.set(coin.id, prev - curr);
        }
      }
    }

    for (const coin of coins) {
      if (coin.market_cap_rank != null) prevRanksRef.current.set(coin.id, coin.market_cap_rank);
    }

    if (newDeltas.size === 0) {
      setRankDeltas(new Map());
      return;
    }
    setRankDeltas(newDeltas);
    const t = setTimeout(() => setRankDeltas(new Map()), 4000);
    return () => clearTimeout(t);
  }, [coins, rankAnimTopN]);

  const { results: searchResults, searching, error: searchError } = useSearch(search, currency);
  const { favorites, toggle: toggleFavorite, isFavorite, clear: clearFavorites } = useFavorites();
  const { alerts, addAlert, removeAlert, resetAlert, editAlert, toggleAlert, clearAlerts, evaluateAlerts, history, clearHistory } = useAlerts();
  const { rangeAlerts, addRangeAlert, removeRangeAlert, editRangeAlert, toggleRangeAlert } = useRangeAlerts();

  const [refreshFlash, setRefreshFlash] = useState(false);

  const handleRefresh = useCallback(async () => {
    await refresh();
    setRefreshFlash(true);
    setTimeout(() => setRefreshFlash(false), 1500);
  }, [refresh]);

  const { containerRef: mainRef, indicatorRef: ptrRef, isRefreshing: ptrRefreshing } = usePullToRefresh(handleRefresh, isUpdateVisible);

  // Foreground resume: aggiorna i prezzi quando l'app torna visibile.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      refresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [refresh]);

  const handleIntervalChange = useCallback((ms: number) => {
    setRefreshInterval(ms);
    localStorage.setItem(INTERVAL_KEY, String(ms));
  }, []);

  const handlePerPageChange = useCallback((n: PerPage) => {
    setPerPage(n);
    setPage(1);
    localStorage.setItem(PERPAGE_KEY, String(n));
  }, []);

  const handleSort = useCallback((key: SortBy) => {
    if (key === '7d') setTimeFrame('7d');
    else if (key === 'change') setTimeFrame('24h');
    setSortBy((prev) => {
      if (prev === key) { setSortDesc((d) => !d); return key; }
      setSortDesc(true);
      return key;
    });
  }, []);

  const handleFavoriteSort = useCallback((key: SortBy) => {
    if (key === '7d') setFavoriteTimeFrame('7d');
    else if (key === 'change') setFavoriteTimeFrame('24h');
    setFavoriteSortBy((prev) => {
      if (prev === key) {
        setFavoriteSortDesc((desc) => !desc);
        return key;
      }
      setFavoriteSortDesc(true);
      return key;
    });
  }, []);

  const isSearching = search.trim().length > 0;
  const displayLoading = isSearching ? searching : loading;

  // Filtro locale sulle coin gia' caricate (per nome E simbolo): garantisce che le
  // coin presenti nell'elenco mercati (incluse quelle marcate AI) siano sempre
  // trovabili anche se la search del provider non le indicizza per nome.
  const localSearchMatches = useMemo(() => {
    if (!isSearching) return [];
    const q = search.trim().toLowerCase();
    return coins.filter(
      (c) => c.name.toLowerCase().includes(q) || c.symbol.toLowerCase().includes(q),
    );
  }, [isSearching, search, coins]);

  const rawDisplayCoins = useMemo(() => {
    if (!isSearching) return coins;
    // Unione: prima le coin locali (con stato AI gia' risolto), poi i risultati
    // del backend non gia' presenti, deduplicati per id.
    const seen = new Set(localSearchMatches.map((c) => c.id));
    return [...localSearchMatches, ...searchResults.filter((c) => !seen.has(c.id))];
  }, [isSearching, coins, localSearchMatches, searchResults]);

  const displayCoins = useMemo(() => {
    return sortCoins(rawDisplayCoins, sortBy, sortDesc);
  }, [rawDisplayCoins, sortBy, sortDesc]);

  const favoriteCoins = useFavoriteCoinsData(favorites, refreshInterval, currency);
  const sortedFavoriteCoins = useMemo(
    () => sortCoins(favoriteCoins, favoriteSortBy, favoriteSortDesc),
    [favoriteCoins, favoriteSortBy, favoriteSortDesc],
  );

  useEffect(() => {
    const prices = new Map<string, number>();
    for (const coin of coins) prices.set(coin.id, coin.current_price);
    for (const coin of favoriteCoins) prices.set(coin.id, coin.current_price);
    if (prices.size > 0) evaluateAlerts(prices);
  }, [coins, favoriteCoins, evaluateAlerts]);
  const syncedFavoriteCoins = useMemo(() => {
    const resolvedFavorites = new Map(
      favoriteCoins.map(c => [c.id, { id: c.id, name: c.name, symbol: c.symbol }]),
    );
    return [...favorites]
      .filter(id => !mutedFavorites.has(id))  // le coin mutate non vengono monitorate per gli avvisi
      .map(id => (
        resolvedFavorites.get(id) ?? { id, name: id, symbol: '' }
      ));
  }, [favoriteCoins, favorites, mutedFavorites]);

  // Keep favSyncRef up-to-date on every render so the background handler always has fresh data
  useEffect(() => {
    favSyncRef.current = {
      coinsJson: JSON.stringify(syncedFavoriteCoins),
      upPct: favMoveUpPct,
      downPct: favMoveDownPct,
      refPricesJson: localStorage.getItem('cs_fav_ref_prices') ?? '{}',
      currency,
    };
  }, [syncedFavoriteCoins, favMoveUpPct, favMoveDownPct, currency]);

  // Sync alert config to backend (FCM) and native SharedPreferences whenever it changes
  useEffect(() => {
    const refPricesJson = localStorage.getItem('cs_fav_ref_prices') ?? '{}';
    const refPrices: Record<string, number> = (() => { try { return JSON.parse(refPricesJson); } catch { return {}; } })();
    syncFavAlertsNative(JSON.stringify(syncedFavoriteCoins), favMoveUpPct, favMoveDownPct, refPricesJson, currency);
    syncAlertsToBackend(alerts, rangeAlerts, {
      coins: syncedFavoriteCoins,
      upPct: favMoveUpPct,
      downPct: favMoveDownPct,
      currency,
      refPrices,
    });
  }, [alerts, rangeAlerts, syncedFavoriteCoins, favMoveUpPct, favMoveDownPct, currency]);

  const handleAddAlert = useCallback((coin: Coin) => {
    setSelectedCoin(coin);
  }, []);

  const handleConfirmAlert = useCallback(
    (
      direction: 'above' | 'below',
      threshold: number,
      percentChange?: number,
      note?: string,
      triggerOptions?: PriceAlertTriggerOptions,
    ) => {
      if (!selectedCoin) return;
      addAlert({
        coinId: selectedCoin.id,
        coinName: selectedCoin.name,
        coinSymbol: selectedCoin.symbol,
        coinImage: selectedCoin.image,
        direction,
        threshold,
        percentChange,
        note,
        ...triggerOptions,
      });
    },
    [selectedCoin, addAlert]
  );

  const handleConfirmRange = useCallback(
    (minPrice: number, maxPrice: number, note?: string) => {
      if (!selectedCoin) return;
      addRangeAlert({
        coinId: selectedCoin.id,
        coinName: selectedCoin.name,
        coinSymbol: selectedCoin.symbol,
        coinImage: selectedCoin.image,
        minPrice,
        maxPrice,
        note,
      });
    },
    [selectedCoin, addRangeAlert]
  );

  const triggeredCount = alerts.filter((a) => a.triggered).length;

  return (
    <>
    {showSplash && <SplashOverlay onDone={() => setShowSplash(false)} />}
    <div className="flex flex-col h-full bg-dark-900">
      <div
        className="fixed inset-x-0 top-0 bg-dark-900 z-50 pointer-events-none"
        style={{ height: 'env(safe-area-inset-top)' }}
      />
      <header
        className="px-4 pt-safe sticky top-0 z-40"
        style={{
          background: 'linear-gradient(180deg, #07101F 0%, #0A1628 70%, #0D1A2E 100%)',
          borderBottom: '1px solid rgba(59,130,246,0.18)',
        }}
      >
        <div className="max-w-lg mx-auto">
          <div className="flex items-center justify-between py-2.5">
            <div className="flex items-center gap-2">
              <LogoLighthouse />
              <h1
                className="text-white font-bold text-xl tracking-tight"
                style={{ textShadow: '0 0 22px rgba(96,165,250,0.38), 0 0 48px rgba(59,130,246,0.12)' }}
              >
                CryptoSentinelAI
              </h1>
            </div>
            <div className="flex items-center gap-2">
              {lastUpdated && (
                <div className="flex items-center gap-1.5">
                  <span
                    className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                    style={{ background: '#3B82F6', boxShadow: '0 0 6px rgba(59,130,246,0.9)' }}
                  />
                  <span className={`text-xs tabular-nums transition-colors ${refreshFlash ? 'text-accent-green font-medium' : 'text-gray-500'}`}>
                    {refreshFlash ? '✓ OK' : lastUpdated.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </div>
              )}
            </div>
          </div>

          {tab === 'dashboard' && (
            <div className="pb-3">
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Cerca criptovaluta…"
                  className="w-full bg-dark-700 border border-dark-600 rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-accent-blue transition-colors"
                />
              </div>
            </div>
          )}
        </div>
      </header>

      <main ref={mainRef} className="flex-1 overflow-y-auto overscroll-y-none pb-20">
        <div ref={ptrRef} className="h-0 flex items-center justify-center overflow-hidden">
          {ptrRefreshing ? (
            <svg className="w-5 h-5 text-accent-blue animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg
              data-ptr-arrow=""
              style={{ transition: 'transform 150ms, color 150ms' }}
              className="w-5 h-5 text-gray-400"
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </div>

        <div className="max-w-lg mx-auto px-4 py-3">
          <NotificationBanner permission={notifPerm} onPermissionChange={setNotifPerm} />
          <EnergySavingBanner dismissed={batteryDismissed} onDismiss={() => setBatteryDismissed(true)} />

          {error && (
            <div className="bg-accent-red/10 border border-accent-red/30 rounded-xl px-4 py-2 text-xs text-accent-red mb-3">
              {error}
            </div>
          )}

          {availableUpdate && isUpdateVisible && (
            <UpdateNotification
              update={availableUpdate}
              dlState={dlState}
              onIgnore={handleIgnoreUpdate}
              onSnooze={handleSnoozeUpdate}
              onDismiss={handleUpdateDone}
              onDownloadStart={() => setDlState('downloading')}
            />
          )}

          {supportNotice.userCount + supportNotice.adminCount > 0 && (
            <SupportTicketNotification
              notice={supportNotice}
              offset={availableUpdate && isUpdateVisible ? 'stacked' : 'normal'}
              onOpen={() => {
                const mode = supportNoticeRef.current.latestMode;
                setSupportModeRequest(mode);
                setTab('settings');
              }}
            />
          )}

          {tab === 'dashboard' && (
            <div>
              {!isSearching && (
                <>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex gap-1">
                      {([50, 100, 200, 400, 600] as const).map((n) => (
                        <button
                          key={n}
                          onClick={() => handlePerPageChange(n)}
                          className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                            perPage === n ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
                          }`}
                        >
                          {n}
                        </button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page === 1}
                        className="px-2.5 py-1 rounded-lg bg-dark-700 text-gray-400 hover:text-white disabled:opacity-30 text-sm transition-colors"
                      >
                        ←
                      </button>
                      <span className="text-xs text-gray-500 tabular-nums">Pag. {page}</span>
                      <button
                        onClick={() => setPage((p) => p + 1)}
                        disabled={coins.length < perPage}
                        className="px-2.5 py-1 rounded-lg bg-dark-700 text-gray-400 hover:text-white disabled:opacity-30 text-sm transition-colors"
                      >
                        →
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 mb-2">
                    <span className="text-gray-600 text-xs flex-shrink-0">Periodo:</span>
                    {([
                      { key: '1h' as TimeFrame, label: '1h' },
                      { key: '24h' as TimeFrame, label: '24h' },
                      { key: '7d' as TimeFrame, label: '7g' },
                    ]).map(({ key, label }) => (
                      <button
                        key={key}
                        onClick={() => setTimeFrame(key)}
                        className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                          timeFrame === key ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-1.5 mb-3 overflow-x-auto pb-0.5 scrollbar-none">
                    {([
                      { key: 'rank' as SortBy, label: 'Rank' },
                      { key: 'change' as SortBy, label: '24h %' },
                      { key: '7d' as SortBy, label: '7g %' },
                      { key: 'volume' as SortBy, label: 'Volume' },
                      { key: 'price' as SortBy, label: 'Prezzo' },
                    ]).map(({ key, label }) => (
                      <button
                        key={key}
                        onClick={() => { hapticLight(); handleSort(key); }}
                        className={`flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                          sortBy === key ? 'bg-accent-blue/20 text-accent-blue border border-accent-blue/30' : 'bg-dark-700 text-gray-400 hover:text-white border border-transparent'
                        }`}
                      >
                        {label}
                        {sortBy === key && <span className="text-xs">{sortDesc ? '↓' : '↑'}</span>}
                      </button>
                    ))}
                  </div>
                </>
              )}

              {displayLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="h-16 bg-dark-800 rounded-xl animate-pulse" />
                  ))}
                </div>
              ) : displayCoins.length === 0 ? (
                <div className="text-center py-12">
                  <div className="text-4xl mb-3">🔍</div>
                  <p className="text-gray-500 text-sm">
                    {isSearching && searchError
                      ? searchError
                      : isSearching
                      ? `Nessuna criptovaluta trovata per "${search}"`
                      : error ?? 'Nessuna criptovaluta disponibile'}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {displayCoins.map((coin) => {
                    const isTradable = eligibleSymbols.has(coin.symbol.toUpperCase());
                    return (
                      <CoinCard
                        key={coin.id}
                        coin={coin}
                        isFavorite={isFavorite(coin.id)}
                        onToggleFavorite={toggleFavorite}
                        onAddAlert={handleAddAlert}
                        onChartTap={handleChartTap}
                        currency={currency}
                        showVolume={sortBy === 'volume'}
                        timeFrame={timeFrame}
                        rankDelta={rankDeltas.get(coin.id)}
                        aiState={isTradable ? (aiStateMap.get(coin.symbol.toUpperCase()) ?? 'inactive') : undefined}
                        onToggleAi={isTradable ? handleToggleAiCoin : undefined}
                      />
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {tab === 'favorites' && (
            <div>
              {favoriteCoins.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center px-8">
                  <div className="text-5xl mb-4">⭐</div>
                  <h3 className="text-white font-semibold text-lg mb-2">Nessun preferito</h3>
                  <p className="text-gray-500 text-sm">
                    Premi la ★ accanto a una criptovaluta per aggiungerla ai tuoi preferiti.
                  </p>
                </div>
              ) : (
                <>
                  <div className="flex gap-1.5 mb-3 overflow-x-auto pb-0.5 scrollbar-none">
                    {([
                      { key: 'rank' as SortBy, label: 'Rank' },
                      { key: 'change' as SortBy, label: '24h %' },
                      { key: '7d' as SortBy, label: '7g %' },
                      { key: 'volume' as SortBy, label: 'Volume' },
                      { key: 'price' as SortBy, label: 'Prezzo' },
                    ]).map(({ key, label }) => (
                      <button
                        key={key}
                        onClick={() => { hapticLight(); handleFavoriteSort(key); }}
                        className={`flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                          favoriteSortBy === key ? 'bg-accent-blue/20 text-accent-blue border border-accent-blue/30' : 'bg-dark-700 text-gray-400 hover:text-white border border-transparent'
                        }`}
                      >
                        {label}
                        {favoriteSortBy === key && <span className="text-xs">{favoriteSortDesc ? '↓' : '↑'}</span>}
                      </button>
                    ))}
                    <button
                      onClick={() => { hapticLight(); handleAckAllFavAlerts(); }}
                      className="flex-shrink-0 ml-auto flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-dark-700 text-gray-400 hover:text-white border border-transparent transition-colors"
                      title="Azzera tutti gli avvisi e ricalibra i riferimenti"
                    >
                      ✓ Ho capito
                    </button>
                  </div>
                  <div className="space-y-2">
                    {sortedFavoriteCoins.map((coin) => {
                      const isTradable = eligibleSymbols.has(coin.symbol.toUpperCase());
                      return (
                        <CoinCard
                          key={coin.id}
                          coin={coin}
                          isFavorite={true}
                          onToggleFavorite={toggleFavorite}
                          onAddAlert={handleAddAlert}
                          onChartTap={handleChartTap}
                          currency={currency}
                          showVolume={favoriteSortBy === 'volume'}
                          timeFrame={favoriteTimeFrame}
                          alertPending={pendingFavAlerts.get(coin.id)}
                          onAlertTap={() => setSelectedFavAlert(pendingFavAlerts.get(coin.id) ?? null)}
                          aiState={isTradable ? (aiStateMap.get(coin.symbol.toUpperCase()) ?? 'inactive') : undefined}
                          onToggleAi={isTradable ? handleToggleAiCoin : undefined}
                          muted={mutedFavorites.has(coin.id)}
                          onToggleMute={handleToggleMuteFavorite}
                        />
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}

          {tab === 'alerts' && (
            <AlertsTab alerts={alerts} onRemove={removeAlert} onReset={resetAlert} coins={coins} onEdit={editAlert} history={history} onClearHistory={clearHistory} sliderRange={sliderRange} rangeAlerts={rangeAlerts} onRemoveRange={removeRangeAlert} onEditRange={editRangeAlert} />
          )}

          {tab === 'agent' && (
            <AgentTab
              adminToken={adminToken}
              onAdminToken={handleAdminTokenChange}
              eligibleTokens={eligibleTokens}
              selectedAiSymbols={selectedAiSymbols}
              watchlistSaving={aiWatchlistSaving}
              watchlistError={aiWatchlistError}
              onToggleAiSymbol={handleToggleAiSymbol}
            />
          )}

          {tab === 'settings' && (
            <SettingsTab
              adminToken={adminToken}
              onAdminToken={handleAdminTokenChange}
              refreshInterval={refreshInterval}
              onIntervalChange={handleIntervalChange}
              favoritesCount={favorites.size}
              alertsCount={alerts.length}
              onClearFavorites={clearFavorites}
              onClearAlerts={clearAlerts}
              notifPerm={notifPerm}
              onPermissionChange={setNotifPerm}
              batteryDismissed={batteryDismissed}
              dlState={dlState}
              onDownloadStart={() => setDlState('downloading')}
              onDownloadDone={() => setDlState('done')}
              currency={currency}
              onCurrencyChange={changeCurrency}
              sliderRange={sliderRange}
              onSliderRangeChange={handleSliderRangeChange}
              favMoveUpPct={favMoveUpPct}
              onFavMoveUpPctChange={handleFavMoveUpPctChange}
              favMoveDownPct={favMoveDownPct}
              onFavMoveDownPctChange={handleFavMoveDownPctChange}
              rankAnimTopN={rankAnimTopN}
              onRankAnimTopNChange={handleRankAnimTopNChange}
              supportModeRequest={supportModeRequest}
              onSupportNotificationsChanged={refreshSupportNotice}
            />
          )}
        </div>
      </main>

      <Navbar
        activeTab={tab}
        onTabChange={setTab}
        alertCount={triggeredCount}
        favoriteCount={favorites.size}
      />

      {selectedCoin && (
        <AlertModal
          coin={selectedCoin}
          onConfirm={handleConfirmAlert}
          onConfirmRange={handleConfirmRange}
          onClose={() => setSelectedCoin(null)}
        />
      )}

      {chartCoin && (
        <CoinChartSheet
          coin={chartCoin}
          alerts={alerts}
          rangeAlerts={rangeAlerts}
          currency={currency}
          onClose={() => setChartCoin(null)}
          onToggleAlert={toggleAlert}
          onToggleRangeAlert={toggleRangeAlert}
          onAddAlert={(coin) => { setChartCoin(null); setSelectedCoin(coin); }}
        />
      )}

      {selectedFavAlert && (
        <FavMovePopup
          alert={selectedFavAlert}
          currency={currency}
          onClose={() => setSelectedFavAlert(null)}
          onDismiss={() => handleDismissFavAlert(selectedFavAlert.coinId)}
        />
      )}

    </div>
    </>
  );
}

function SupportTicketNotification({
  notice,
  offset,
  onOpen,
}: {
  notice: SupportHomeNotice;
  offset: 'normal' | 'stacked';
  onOpen: () => void;
}) {
  const total = notice.userCount + notice.adminCount;
  const bottomClass = offset === 'stacked' ? 'bottom-40' : 'bottom-24';
  const label = notice.adminCount > 0
    ? `${notice.adminCount} messaggi admin`
    : `${notice.userCount} messaggi supporto`;

  return (
    <button
      onClick={onOpen}
      className={`fixed ${bottomClass} left-4 z-30 w-12 h-12 flex items-center justify-center`}
      aria-label="Messaggi supporto"
      title={notice.latestTicket ? `${label}: ${notice.latestTicket.subject}` : label}
    >
      <span className="absolute w-full h-full rounded-full bg-accent-blue/25 animate-ping" />
      <span className="absolute w-full h-full rounded-full bg-accent-blue/15 border border-accent-blue/40" />
      <svg className="relative z-10 w-5 h-5 text-accent-blue drop-shadow" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M8 10h8M8 14h5m8-2a8 8 0 01-8 8H7l-4 3v-7a8 8 0 1118-4z" />
      </svg>
      <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-accent-red text-white text-[10px] font-bold flex items-center justify-center">
        {total > 99 ? '99+' : total}
      </span>
    </button>
  );
}
