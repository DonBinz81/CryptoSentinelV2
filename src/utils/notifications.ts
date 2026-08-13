import { Capacitor, CapacitorHttp, registerPlugin } from '@capacitor/core';
import { LocalNotifications } from '@capacitor/local-notifications';
import { PushNotifications } from '@capacitor/push-notifications';
import { getDeviceId } from './deviceId';

interface AppSettingsPlugin {
  openNotifications(): Promise<void>;
  openWithChooser(options: { url: string; title?: string }): Promise<void>;
  syncFavAlerts(options: { coinsJson: string; upPct: number; downPct: number; refPricesJson: string; currency: string }): Promise<void>;
  getAndClearPendingFavAlerts(): Promise<{ json: string }>;
}

const AppSettings = registerPlugin<AppSettingsPlugin>('AppSettings');
const BACKEND_API_BASE_URL = import.meta.env.VITE_BACKEND_API_BASE_URL as string | undefined;
const API_DEVICE_TOKEN = import.meta.env.VITE_API_DEVICE_TOKEN as string | undefined;
const API_ALERTS_TOKEN = import.meta.env.VITE_API_ALERTS_TOKEN as string | undefined;

const PENDING_TOKEN_KEY = 'cs_push_token_pending';
const LAST_VERIFIED_KEY = 'cs_push_last_verified';
const REG_LOG_KEY = 'cs_push_reg_log';
const DAILY_MS = 24 * 60 * 60 * 1000;
const RETRY_DELAYS_MS = [30_000, 2 * 60_000, 10 * 60_000, 30 * 60_000];

const PENDING_FAV_ALERTS_KEY = 'cs_pending_fcm_fav_alerts';
const SUPPORT_DISPLAY_NAME_KEY = 'cs_support_display_name';

let pushRegistrationStarted = false;

// Genera un ID numerico stabile dalla chiave della notifica.
// Stesso tipo+coin/asset → stesso ID → la notifica precedente viene sostituita
// invece di accumularsi. Risolve il limite Android di 50 notifiche per app.
function stableNotifId(data: Record<string, string>): number {
  let key: string;
  const t = data?.type ?? '';
  if (t === 'price_alert') {
    // coin_id + direction (above/below) → una slot per ogni soglia per coin
    key = `price_${data.coin_id ?? ''}_${data.cross_direction || ''}`;
  } else if (t === 'range_alert') {
    key = `range_${data.coin_id ?? ''}`;
  } else if (t === 'fav_alert') {
    key = `fav_${data.coin_id ?? ''}_${data.direction ?? ''}`;
  } else {
    // Trade / risk / altri: usa asset+market+tipo chiusura/apertura
    const asset = data?.asset ?? '';
    const market = data?.market ?? '';
    const topic = data?.topic ?? '';
    const kind = 'pnl_usd' in data ? 'close' : 'alert_type' in data ? 'risk' : 'open';
    key = `${kind}_${topic}_${asset}_${market}`;
  }
  let h = 5381;
  for (let i = 0; i < key.length; i++) h = ((h << 5) + h) ^ key.charCodeAt(i);
  return (Math.abs(h) % 1_800_000) + 1;
}
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let dailyTimer: ReturnType<typeof setInterval> | null = null;

export interface FavAlertData {
  coinId: string;
  coinName: string;
  coinSymbol: string;
  direction: 'up' | 'down';
  pct: number;
  currentPrice: number;
  refPrice: number;
}

interface FavPushEvent {
  alert: FavAlertData;
  openFavorites: boolean;
}

const favPushSubscribers = new Set<(event: FavPushEvent) => void>();

// ── Registration log ──────────────────────────────────────────────────────────

function logReg(msg: string): void {
  try {
    const logs: string[] = JSON.parse(localStorage.getItem(REG_LOG_KEY) ?? '[]');
    const ts = new Date().toISOString().replace('T', ' ').slice(0, 19);
    logs.push(`${ts} ${msg}`);
    if (logs.length > 60) logs.splice(0, logs.length - 60);
    localStorage.setItem(REG_LOG_KEY, JSON.stringify(logs));
  } catch { /* storage not available */ }
}

export function getRegistrationLogs(): string[] {
  try {
    return JSON.parse(localStorage.getItem(REG_LOG_KEY) ?? '[]') as string[];
  } catch {
    return [];
  }
}

// ── Fav push alert helpers ────────────────────────────────────────────────────

function loadPendingFavAlerts(): Record<string, FavAlertData> {
  try {
    return JSON.parse(localStorage.getItem(PENDING_FAV_ALERTS_KEY) ?? '{}') as Record<string, FavAlertData>;
  } catch {
    return {};
  }
}

function savePendingFavAlert(alert: FavAlertData): void {
  const pending = loadPendingFavAlerts();
  pending[alert.coinId] = alert;
  localStorage.setItem(PENDING_FAV_ALERTS_KEY, JSON.stringify(pending));
}

function parseFavAlert(data: Record<string, unknown> | undefined): FavAlertData | null {
  if (!data || data.type !== 'fav_alert' || typeof data.coin_id !== 'string') return null;
  return {
    coinId: data.coin_id,
    coinName: typeof data.coin_name === 'string' ? data.coin_name : data.coin_id,
    coinSymbol: typeof data.coin_symbol === 'string' ? data.coin_symbol : '',
    direction: data.direction === 'down' ? 'down' : 'up',
    pct: Number(data.pct ?? 0),
    currentPrice: Number(data.current_price ?? 0),
    refPrice: Number(data.ref_price ?? 0),
  };
}

function emitFavPush(data: Record<string, unknown> | undefined, openFavorites: boolean): void {
  const alert = parseFavAlert(data);
  if (!alert) return;
  savePendingFavAlert(alert);
  favPushSubscribers.forEach((subscriber) => subscriber({ alert, openFavorites }));
}

export function subscribeFavoritePushAlerts(
  subscriber: (event: FavPushEvent) => void,
): () => void {
  favPushSubscribers.add(subscriber);
  Object.values(loadPendingFavAlerts()).forEach((alert) => {
    subscriber({ alert, openFavorites: false });
  });
  return () => favPushSubscribers.delete(subscriber);
}

export function dismissFavoritePushAlert(coinId: string): void {
  const pending = loadPendingFavAlerts();
  delete pending[coinId];
  localStorage.setItem(PENDING_FAV_ALERTS_KEY, JSON.stringify(pending));
  dismissFavoritePushAlertOnBackend(coinId);
}

export async function refreshPendingFavoritePushAlerts(): Promise<void> {
  const baseUrl = BACKEND_API_BASE_URL?.replace(/\/+$/, '');
  if (!baseUrl || !API_ALERTS_TOKEN) return;
  try {
    const response = await CapacitorHttp.request({
      method: 'GET',
      url: `${baseUrl}/api/v1/alerts/pending-favorites?device_id=${encodeURIComponent(getDeviceId())}`,
      headers: { Authorization: `Bearer ${API_ALERTS_TOKEN}` },
      connectTimeout: 6000,
      readTimeout: 6000,
    });
    if (response.status < 200 || response.status >= 300) return;
    const items = (response.data as { items?: Record<string, unknown>[] })?.items ?? [];
    for (const item of items) emitFavPush({ ...item, type: 'fav_alert' }, false);
  } catch {
    // The local persisted badge remains available while the backend is unreachable.
  }
}

async function dismissFavoritePushAlertOnBackend(coinId: string): Promise<void> {
  const baseUrl = BACKEND_API_BASE_URL?.replace(/\/+$/, '');
  if (!baseUrl || !API_ALERTS_TOKEN) return;
  try {
    await CapacitorHttp.request({
      method: 'DELETE',
      url: `${baseUrl}/api/v1/alerts/pending-favorites/${encodeURIComponent(coinId)}?device_id=${encodeURIComponent(getDeviceId())}`,
      headers: { Authorization: `Bearer ${API_ALERTS_TOKEN}` },
      connectTimeout: 6000,
      readTimeout: 6000,
    });
  } catch {
    // Best effort: a later backend refresh may restore the badge until acknowledgement succeeds.
  }
}

// ── Push token registration ───────────────────────────────────────────────────

async function sendPushTokenToBackend(token: string): Promise<boolean> {
  const baseUrl = BACKEND_API_BASE_URL?.replace(/\/+$/, '');
  if (!baseUrl || !API_DEVICE_TOKEN) {
    logReg('⚠️ env non configurato, skip registrazione');
    return false;
  }
  try {
    const r = await CapacitorHttp.request({
      method: 'POST',
      url: `${baseUrl}/api/v1/notifications/devices`,
      headers: {
        Authorization: `Bearer ${API_DEVICE_TOKEN}`,
        'Content-Type': 'application/json',
      },
      data: {
        token,
        platform: 'android',
        device_id: getDeviceId(),
        app_version: __APP_VERSION__,
        build_number: String(__APP_BUILD_NUMBER__),
        display_name: localStorage.getItem(SUPPORT_DISPLAY_NAME_KEY) ?? undefined,
        locale: navigator.language,
      },
      connectTimeout: 8000,
      readTimeout: 8000,
    });
    if (r.status >= 200 && r.status < 300) {
      localStorage.removeItem(PENDING_TOKEN_KEY);
      localStorage.setItem(LAST_VERIFIED_KEY, String(Date.now()));
      logReg(`✓ token registrato (status ${r.status})`);
      return true;
    }
    logReg(`✗ backend ha risposto ${r.status}, token salvato per retry`);
    localStorage.setItem(PENDING_TOKEN_KEY, token);
    return false;
  } catch (e) {
    const msg = (e as Error).message ?? 'errore sconosciuto';
    logReg(`✗ errore rete — ${msg} — token salvato per retry`);
    localStorage.setItem(PENDING_TOKEN_KEY, token);
    return false;
  }
}

function scheduleRetry(token: string, attempt = 0): void {
  if (retryTimer) clearTimeout(retryTimer);
  const delay = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
  logReg(`⏳ prossimo retry in ${delay / 1000}s (tentativo ${attempt + 1})`);
  retryTimer = setTimeout(async () => {
    logReg(`🔄 retry #${attempt + 1}`);
    const ok = await sendPushTokenToBackend(token);
    if (!ok) scheduleRetry(token, attempt + 1);
  }, delay);
}

async function registerRemotePushToken(): Promise<void> {
  if (pushRegistrationStarted || !BACKEND_API_BASE_URL || !API_DEVICE_TOKEN) return;
  pushRegistrationStarted = true;
  logReg('🚀 bootstrap push avviato');

  try {
    // Retry any token that failed in a previous session
    const pendingToken = localStorage.getItem(PENDING_TOKEN_KEY);
    if (pendingToken) {
      logReg('🔄 token pending trovato, retry immediato');
      const ok = await sendPushTokenToBackend(pendingToken);
      if (!ok) scheduleRetry(pendingToken, 0);
    }

    await PushNotifications.addListener('registration', async (token) => {
      logReg('📨 FCM token ricevuto');
      // Cancel any in-flight retry — the new token supersedes it
      if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
      const ok = await sendPushTokenToBackend(token.value);
      if (!ok) scheduleRetry(token.value, 0);
    });

    await PushNotifications.addListener('registrationError', (err) => {
      logReg(`✗ FCM registrationError — ${JSON.stringify(err)}`);
    });

    await PushNotifications.addListener('pushNotificationReceived', async (notification) => {
      emitFavPush(notification.data, false);
      const d = notification.data ?? {};
      const topic = typeof d.topic === 'string' ? d.topic : '';
      const isTrade = topic === 'cryptosentinel-spot' || topic === 'cryptosentinel-perp';
      await LocalNotifications.schedule({
        notifications: [{
          id: stableNotifId(d),
          channelId: isTrade ? 'trade_alerts' : 'price_alerts',
          title: notification.title ?? 'CryptoSentinel',
          body: notification.body ?? '',
          sound: 'default',
          smallIcon: 'ic_notification',
          autoCancel: true,
        }],
      });
    });

    await PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
      emitFavPush(action.notification.data, true);
    });

    const permission = await PushNotifications.requestPermissions();
    if (permission.receive !== 'granted') {
      logReg('⚠️ permesso notifiche non concesso');
      return;
    }

    await PushNotifications.register();
    logReg('📡 PushNotifications.register() chiamato');

    // Daily re-registration while the app stays open in background
    if (dailyTimer) clearInterval(dailyTimer);
    dailyTimer = setInterval(async () => {
      logReg('📅 verifica giornaliera — forzo re-registrazione');
      try {
        await PushNotifications.register();
      } catch (e) {
        logReg(`✗ errore verifica giornaliera — ${(e as Error).message ?? 'sconosciuto'}`);
      }
    }, DAILY_MS);

  } catch (e) {
    logReg(`✗ eccezione bootstrap — ${(e as Error).message ?? 'sconosciuto'}`);
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

export async function initNotifications(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  await LocalNotifications.createChannel({
    id: 'price_alerts',
    name: 'Allarmi Prezzi',
    description: 'Notifiche per gli allarmi di prezzo crypto',
    importance: 5,
    vibration: true,
    sound: 'default',
    visibility: 1,
  });
  await LocalNotifications.createChannel({
    id: 'trade_alerts',
    name: 'Trade Spot & Perp',
    description: 'Aperture e chiusure di posizioni spot e perpetual',
    importance: 5,
    vibration: true,
    sound: 'default',
    visibility: 1,
  });
  await registerRemotePushToken();
}

export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!Capacitor.isNativePlatform()) {
    if (!('Notification' in window)) return 'denied';
    if (Notification.permission !== 'default') return Notification.permission;
    return await Notification.requestPermission();
  }
  const result = await LocalNotifications.requestPermissions();
  return result.display === 'granted' ? 'granted' : 'denied';
}

export async function getNotificationPermission(): Promise<NotificationPermission> {
  if (!Capacitor.isNativePlatform()) {
    if (!('Notification' in window)) return 'denied';
    return Notification.permission;
  }
  const status = await LocalNotifications.checkPermissions();
  return status.display === 'granted' ? 'granted' : 'denied';
}

export function openExternalUrl(url: string): void {
  if (Capacitor.isNativePlatform()) {
    AppSettings.openWithChooser({ url, title: 'Apri con' }).catch(() => {
      window.open(url, '_blank');
    });
  } else {
    window.open(url, '_blank');
  }
}

export function openNotificationSettings(): void {
  if (Capacitor.isNativePlatform()) {
    AppSettings.openNotifications().catch(() => {
      window.open('app-settings:', '_system');
    });
  }
}

export async function syncFavAlertsNative(
  coinsJson: string,
  upPct: number,
  downPct: number,
  refPricesJson = '{}',
  currency = 'usd',
): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  try {
    await AppSettings.syncFavAlerts({ coinsJson, upPct, downPct, refPricesJson, currency });
  } catch { /* ignore */ }
}

export async function getAndClearPendingFavAlerts(): Promise<string> {
  if (!Capacitor.isNativePlatform()) return '[]';
  try {
    const result = await AppSettings.getAndClearPendingFavAlerts();
    return result.json ?? '[]';
  } catch {
    return '[]';
  }
}
