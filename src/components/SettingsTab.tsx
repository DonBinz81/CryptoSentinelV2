import { useState, useEffect, useRef, type FC } from 'react';
import QRCode from 'qrcode';
import { Capacitor, CapacitorHttp } from '@capacitor/core';
import { openNotificationSettings, getRegistrationLogs } from '../utils/notifications';
import { openBatterySettings } from '../utils/energySaving';
import { checkForUpdates, downloadAndInstall, openDownloadsFolder, getDevBuildInfo, mergeToMain, APK_PAGES_URL, type UpdateResult, type DevBuildInfo } from '../utils/update';
import type { Currency } from '../hooks/useCurrency';
import {
  getProviderStatus,
  selectProvider as updateMarketDataProvider,
  type ProviderName,
  type ProviderSelectionResponse,
} from '../services/marketData';
import { resetDatabase } from '../services/agentApi';
import {
  adminListSupportTickets,
  adminGetSupportTicket,
  adminMarkSupportTicketRead,
  adminReplySupportTicket,
  adminUpdateSupportStatus,
  closeSupportTicket,
  createSupportTicket,
  getSupportTicket,
  listSupportTickets,
  markSupportTicketRead,
  replySupportTicket,
  syncDeviceProfile,
  type SupportTicketDetail,
  type SupportTicketSummary,
  type TicketCategory,
  type TicketPriority,
  type TicketStatus,
} from '../services/supportApi';

const DONATION_OPTIONS = [
  {
    icon: '⚡',
    label: 'Lightning Network',
    subtitle: 'Bitcoin istantaneo · zero commissioni',
    address: 'eifel@getalby.com',
    appUri: 'lightning:eifel@getalby.com',
  },
  {
    icon: '₿',
    label: 'Bitcoin',
    subtitle: 'On-chain · Taproot',
    address: 'bc1pfzyjm5759qv0rjfsxld4jcejqv7elkuw6j9w2dxcsyrdf4vsw6yq6lexdg',
    appUri: 'bitcoin:bc1pfzyjm5759qv0rjfsxld4jcejqv7elkuw6j9w2dxcsyrdf4vsw6yq6lexdg',
  },
  {
    icon: '💎',
    label: 'USDT / USDC',
    subtitle: 'EVM · Ethereum, Polygon, BSC, Arbitrum…',
    address: '0x80f8Fc375bCf1a7BC38394d6048e8364628Bd6C0',
    appUri: 'ethereum:0x80f8Fc375bCf1a7BC38394d6048e8364628Bd6C0',
  },
] as const;

const QRModal: FC<{ address: string; label: string; icon: string; onClose: () => void }> = ({ address, label, icon, onClose }) => {
  const [qrUrl, setQrUrl] = useState('');

  useEffect(() => {
    QRCode.toDataURL(address, { width: 240, margin: 2, color: { dark: '#000000', light: '#ffffff' } })
      .then(setQrUrl)
      .catch(() => {});
  }, [address]);

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-dark-800 rounded-2xl w-full max-w-xs p-5 shadow-2xl border border-dark-600 flex flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between w-full mb-4">
          <div className="flex items-center gap-2">
            <span className="text-xl">{icon}</span>
            <span className="text-white font-bold text-base">{label}</span>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl leading-none">&times;</button>
        </div>

        {qrUrl ? (
          <div className="bg-white rounded-xl p-3 mb-4">
            <img src={qrUrl} alt="QR code" className="w-48 h-48 block" />
          </div>
        ) : (
          <div className="w-48 h-48 bg-dark-700 rounded-xl mb-4 flex items-center justify-center">
            <svg className="w-6 h-6 text-gray-500 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
        )}

        <p className="text-xs text-gray-500 font-mono text-center break-all leading-relaxed">{address}</p>
      </div>
    </div>
  );
};

const DonationRow: FC<{ icon: string; label: string; subtitle: string; address: string; appUri?: string | null; last?: boolean }> = ({
  icon, label, subtitle, address, appUri, last,
}) => {
  const [copied, setCopied] = useState(false);
  const [showQR, setShowQR] = useState(false);

  const truncated = address.length > 20
    ? `${address.slice(0, 10)}…${address.slice(-6)}`
    : address;

  const handleOpen = () => {
    if (appUri) window.open(appUri, '_system');
  };

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(address);
    } catch {
      const el = document.createElement('textarea');
      el.value = address;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <>
      {showQR && <QRModal address={address} label={label} icon={icon} onClose={() => setShowQR(false)} />}
      <div
        className={`px-4 py-3 flex items-center gap-3 transition-colors ${last ? 'rounded-b-xl' : ''} ${appUri ? 'cursor-pointer hover:bg-dark-700 active:bg-dark-600' : ''}`}
        onClick={appUri ? handleOpen : undefined}
      >
        <span className="text-xl w-7 text-center flex-shrink-0">{icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white font-medium">{label}</p>
          <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>
          <p className="text-xs text-gray-600 font-mono mt-0.5 truncate">{truncated}</p>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            onClick={handleCopy}
            className={`text-xs px-3 py-1.5 rounded-lg font-semibold transition-all ${
              copied ? 'bg-accent-green/20 text-accent-green' : 'bg-dark-700 text-gray-400 hover:text-white'
            }`}
          >
            {copied ? '✓' : 'Copia'}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); setShowQR(true); }}
            className="text-xs px-3 py-1.5 rounded-lg font-semibold bg-dark-700 text-gray-400 hover:text-white transition-all"
            aria-label="Mostra QR code"
          >
            QR
          </button>
        </div>
      </div>
    </>
  );
};

const INTERVALS = [
  { label: '30 sec', ms: 30_000 },
  { label: '1 min', ms: 60_000 },
  { label: '5 min', ms: 300_000 },
];

const SUPPORT_CATEGORIES: Array<{ value: TicketCategory; label: string }> = [
  { value: 'bug', label: 'Bug' },
  { value: 'alert', label: 'Alert' },
  { value: 'market', label: 'Mercato' },
  { value: 'agent', label: 'Agente' },
  { value: 'wallet', label: 'Wallet' },
  { value: 'other', label: 'Altro' },
];

const SUPPORT_PRIORITIES: Array<{ value: TicketPriority; label: string }> = [
  { value: 'low', label: 'Bassa' },
  { value: 'medium', label: 'Media' },
  { value: 'high', label: 'Alta' },
  { value: 'critical', label: 'Critica' },
];

const SUPPORT_STATUSES: Array<{ value: TicketStatus; label: string }> = [
  { value: 'open', label: 'Aperto' },
  { value: 'in_progress', label: 'In lavorazione' },
  { value: 'waiting_user', label: 'Attesa utente' },
  { value: 'resolved', label: 'Risolto' },
  { value: 'closed', label: 'Chiuso' },
  { value: 'archived', label: 'Archiviato' },
];

const DEV_PIN = '6878';
const SUPPORT_DISPLAY_NAME_KEY = 'cs_support_display_name';

type UpdateState = 'idle' | 'checking' | 'up-to-date' | 'available' | 'error';
type DevState = 'locked' | 'pin-entry' | 'unlocked';
type DevLoadState = 'idle' | 'loading' | 'loaded' | 'error';
type SupportMode = 'user' | 'admin';

interface Props {
  adminToken: string;
  onAdminToken: (value: string) => void;
  refreshInterval: number;
  onIntervalChange: (ms: number) => void;
  favoritesCount: number;
  alertsCount: number;
  onClearFavorites: () => void;
  onClearAlerts: () => void;
  notifPerm: NotificationPermission;
  onPermissionChange: (p: NotificationPermission) => void;
  batteryDismissed: boolean;
  dlState: 'idle' | 'downloading' | 'done' | 'error';
  onDownloadStart: () => void;
  onDownloadDone: () => void;
  currency: Currency;
  onCurrencyChange: (c: Currency) => void;
  sliderRange: number;
  onSliderRangeChange: (n: number) => void;
  favMoveUpPct: number;
  onFavMoveUpPctChange: (n: number) => void;
  favMoveDownPct: number;
  onFavMoveDownPctChange: (n: number) => void;
  rankAnimTopN: number;
  onRankAnimTopNChange: (n: number) => void;
  supportModeRequest?: SupportMode;
  onSupportNotificationsChanged?: () => void;
}

const SettingsTab: FC<Props> = ({
  adminToken,
  onAdminToken,
  refreshInterval,
  onIntervalChange,
  favoritesCount,
  alertsCount,
  onClearFavorites,
  onClearAlerts,
  notifPerm,
  batteryDismissed,
  dlState,
  onDownloadStart,
  onDownloadDone,
  currency,
  onCurrencyChange,
  sliderRange,
  onSliderRangeChange,
  favMoveUpPct,
  onFavMoveUpPctChange,
  favMoveDownPct,
  onFavMoveDownPctChange,
  rankAnimTopN,
  onRankAnimTopNChange,
  supportModeRequest,
  onSupportNotificationsChanged,
}) => {
  const [updateState, setUpdateState] = useState<UpdateState>('idle');
  const [updateInfo, setUpdateInfo] = useState<UpdateResult | null>(null);
  const [devState, setDevState] = useState<DevState>('locked');
  const [pinInput, setPinInput] = useState('');
  const [pinError, setPinError] = useState(false);
  const [devLoadState, setDevLoadState] = useState<DevLoadState>('idle');
  const [devBuildInfo, setDevBuildInfo] = useState<DevBuildInfo | null>(null);
  const [ghToken, setGhToken] = useState(() => localStorage.getItem('cryptosentinel_dev_token') ?? '');
  const [showToken, setShowToken] = useState(false);
  const [mergeState, setMergeState] = useState<'idle' | 'merging' | 'done' | 'error'>('idle');
  const [mergeError, setMergeError] = useState('');
  const [providerState, setProviderState] = useState<ProviderSelectionResponse | null>(null);
  const [providerLoadState, setProviderLoadState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [resetState, setResetState] = useState<'idle' | 'working' | 'done' | 'error'>('idle');
  const [resetMsg, setResetMsg] = useState('');
  const [supportDisplayName, setSupportDisplayName] = useState(() => localStorage.getItem(SUPPORT_DISPLAY_NAME_KEY) ?? '');
  const [supportMode, setSupportMode] = useState<SupportMode>('user');
  const [supportTickets, setSupportTickets] = useState<SupportTicketSummary[]>([]);
  const [supportDetail, setSupportDetail] = useState<SupportTicketDetail | null>(null);
  const [supportState, setSupportState] = useState<'idle' | 'loading' | 'saving' | 'error'>('idle');
  const [supportError, setSupportError] = useState('');
  const [supportCategory, setSupportCategory] = useState<TicketCategory>('bug');
  const [supportPriority, setSupportPriority] = useState<TicketPriority>('medium');
  const [supportSubject, setSupportSubject] = useState('');
  const [supportMessage, setSupportMessage] = useState('');
  const [supportReply, setSupportReply] = useState('');
  const [supportDiagnostics, setSupportDiagnostics] = useState(true);
  const supportLongPressTimer = useRef<number | null>(null);
  const supportLongPressHandled = useRef(false);

  type DiagState = 'idle' | 'checking' | 'done';
  interface DiagResult {
    backendUrl: string | null;
    deviceTokenSet: boolean;
    alertsTokenSet: boolean;
    readTokenSet: boolean;
    backendReachable: boolean;
    backendLatencyMs: number | null;
    deviceCount: number | null;
    registrationLog: string[];
    checkedAt: string;
    error?: string;
  }
  const [diagState, setDiagState] = useState<DiagState>('idle');
  const [diagResult, setDiagResult] = useState<DiagResult | null>(null);

  const handleCheckUpdate = async () => {
    setUpdateState('checking');
    try {
      const result = await checkForUpdates(__APP_BUILD_NUMBER__);
      setUpdateInfo(result);
      setUpdateState(result.available ? 'available' : 'up-to-date');
    } catch {
      setUpdateState('error');
    }
  };

  const handlePinSubmit = () => {
    if (pinInput === DEV_PIN) {
      setDevState('unlocked');
      setPinError(false);
      setPinInput('');
    } else {
      setPinError(true);
      setPinInput('');
    }
  };

  const handleSaveToken = (val: string) => {
    setGhToken(val);
    localStorage.setItem('cryptosentinel_dev_token', val);
  };

  const handleMerge = async () => {
    if (!devBuildInfo?.branch || !ghToken) return;
    setMergeState('merging');
    setMergeError('');
    try {
      await mergeToMain(devBuildInfo.branch, ghToken);
      setMergeState('done');
    } catch (e) {
      setMergeError((e as Error).message);
      setMergeState('error');
    }
  };

  const handleDiagnostic = async () => {
    setDiagState('checking');
    const rawUrl = (import.meta.env.VITE_BACKEND_API_BASE_URL as string | undefined)?.replace(/\/+$/, '') ?? null;
    const deviceTokenSet = !!(import.meta.env.VITE_API_DEVICE_TOKEN as string | undefined);
    const alertsTokenSet = !!(import.meta.env.VITE_API_ALERTS_TOKEN as string | undefined);
    const readTokenSet = !!(import.meta.env.VITE_API_READ_TOKEN as string | undefined);
    let backendReachable = false;
    let backendLatencyMs: number | null = null;
    let deviceCount: number | null = null;
    let error: string | undefined;
    if (rawUrl) {
      try {
        const t0 = Date.now();
        const r = await CapacitorHttp.request({
          method: 'GET',
          url: `${rawUrl}/health/live`,
          headers: { 'Cache-Control': 'no-store' },
          connectTimeout: 6000,
          readTimeout: 6000,
        });
        backendLatencyMs = Date.now() - t0;
        backendReachable = r.status >= 200 && r.status < 300;
        if (!backendReachable) error = `HTTP ${r.status}`;
      } catch (e) {
        const msg = (e as Error).message ?? String(e);
        if (msg.toLowerCase().includes('timeout') || msg.toLowerCase().includes('timed out')) {
          error = 'Timeout (6s) — backend lento o non raggiungibile';
        } else if (msg.toLowerCase().includes('connection refused') || msg.toLowerCase().includes('refused')) {
          error = 'Connessione rifiutata — backend non avviato';
        } else if (msg.toLowerCase().includes('network') || msg.toLowerCase().includes('unable to resolve')) {
          error = 'Rete non raggiungibile — controlla Tailscale/VPN';
        } else {
          error = msg;
        }
      }
      const readToken = (import.meta.env.VITE_API_READ_TOKEN as string | undefined) ?? '';
      if (backendReachable && readToken) {
        try {
          const rs = await CapacitorHttp.request({
            method: 'GET',
            url: `${rawUrl}/api/v1/notifications/status`,
            headers: { Authorization: `Bearer ${readToken}` },
            connectTimeout: 4000,
            readTimeout: 4000,
          });
          if (rs.status === 200 && rs.data?.token_count != null) {
            deviceCount = rs.data.token_count as number;
          }
        } catch { /* non bloccante */ }
      }
    }
    setDiagResult({
      backendUrl: rawUrl,
      deviceTokenSet,
      alertsTokenSet,
      readTokenSet,
      backendReachable,
      backendLatencyMs,
      deviceCount,
      registrationLog: getRegistrationLogs().slice(-10).reverse(),
      checkedAt: new Date().toLocaleTimeString('it-IT'),
      error,
    });
    setDiagState('done');
  };

  const handleLoadProvider = async () => {
    setProviderLoadState('loading');
    try {
      setProviderState(await getProviderStatus());
      setProviderLoadState('idle');
    } catch {
      setProviderLoadState('error');
    }
  };

  const handleProviderChange = async (provider: ProviderName) => {
    if (!adminToken || provider === providerState?.active) return;
    setProviderLoadState('loading');
    try {
      setProviderState(await updateMarketDataProvider(provider, adminToken));
      setProviderLoadState('idle');
    } catch {
      setProviderLoadState('error');
    }
  };

  const handleResetDb = async () => {
    if (!adminToken) return;
    const wantsBackup = window.confirm('Salvare un backup prima di azzerare il database?\n\nOK = salva backup · Annulla = niente backup');
    let backupName: string | null = null;
    if (wantsBackup) {
      const input = window.prompt('Nome del backup:', `backup_${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}`);
      if (input === null) return; // prompt annullato: interrompe tutto
      backupName = input.trim() || null;
    }
    const warn = backupName
      ? `Azzerare TUTTO il database? Verrà prima salvato il backup "${backupName}".`
      : 'Azzerare TUTTO il database SENZA backup? Operazione irreversibile.';
    if (!window.confirm(warn)) return;
    setResetState('working');
    setResetMsg('');
    try {
      const result = await resetDatabase(backupName, adminToken);
      const total = Object.values(result.deleted).reduce((a, b) => a + b, 0);
      const agente = result.kill_switch ? ` · agente: ${result.kill_switch}` : '';
      setResetState('done');
      setResetMsg(result.archived_run_id
        ? `Azzerato (${total} record) · backup "${result.backup_label}"${agente}`
        : `Azzerato (${total} record) · nessun backup${agente}`);
    } catch (err) {
      setResetState('error');
      setResetMsg(err instanceof Error ? err.message : 'Reset fallito');
    }
  };

  const loadSupportTickets = async (mode: SupportMode = supportMode) => {
    setSupportState('loading');
    setSupportError('');
    try {
      const response = mode === 'admin' && adminToken
        ? await adminListSupportTickets(adminToken)
        : await listSupportTickets();
      setSupportTickets(response.items);
      setSupportState('idle');
    } catch (err) {
      setSupportState('error');
      setSupportError(err instanceof Error ? err.message : 'Supporto non disponibile');
    }
  };

  const saveSupportDisplayName = async () => {
    const normalized = supportDisplayName.trim();
    localStorage.setItem(SUPPORT_DISPLAY_NAME_KEY, normalized);
    setSupportState('saving');
    setSupportError('');
    try {
      await syncDeviceProfile(normalized);
      setSupportState('idle');
    } catch (err) {
      setSupportState('error');
      setSupportError(err instanceof Error ? err.message : 'Nome non sincronizzato');
    }
  };

  const createTicket = async () => {
    if (!supportSubject.trim() || !supportMessage.trim()) return;
    setSupportState('saving');
    setSupportError('');
    try {
      const detail = await createSupportTicket({
        displayName: supportDisplayName.trim(),
        category: supportCategory,
        priority: supportPriority,
        subject: supportSubject.trim(),
        message: supportMessage.trim(),
        includeDiagnostics: supportDiagnostics,
      });
      setSupportDetail(detail);
      setSupportSubject('');
      setSupportMessage('');
      await loadSupportTickets('user');
      setSupportState('idle');
    } catch (err) {
      setSupportState('error');
      setSupportError(err instanceof Error ? err.message : 'Ticket non creato');
    }
  };

  const openTicket = async (ticket: SupportTicketSummary) => {
    setSupportState('loading');
    setSupportError('');
    try {
      const detail = supportMode === 'admin' && adminToken
        ? await adminGetSupportTicket(ticket.ticket_id, adminToken)
        : await getSupportTicket(ticket.ticket_id);
      setSupportDetail(detail);
      if (supportMode === 'admin' && adminToken) {
        await adminMarkSupportTicketRead(ticket.ticket_id, adminToken);
      } else {
        await markSupportTicketRead(ticket.ticket_id);
      }
      onSupportNotificationsChanged?.();
      setSupportTickets((prev) =>
        prev.map((t) => (t.ticket_id === ticket.ticket_id ? { ...t, has_unread: false } : t)),
      );
      setSupportState('idle');
    } catch (err) {
      setSupportState('error');
      setSupportError(err instanceof Error ? err.message : 'Ticket non caricato');
    }
  };

  const sendTicketReply = async () => {
    if (!supportDetail || !supportReply.trim()) return;
    setSupportState('saving');
    setSupportError('');
    try {
      const detail = supportMode === 'admin' && adminToken
        ? await adminReplySupportTicket(supportDetail.ticket_id, supportReply.trim(), adminToken)
        : await replySupportTicket(supportDetail.ticket_id, supportReply.trim());
      setSupportDetail(detail);
      setSupportReply('');
      await loadSupportTickets(supportMode);
      setSupportState('idle');
    } catch (err) {
      setSupportState('error');
      setSupportError(err instanceof Error ? err.message : 'Risposta non inviata');
    }
  };

  const updateTicketStatus = async (status: TicketStatus) => {
    if (!supportDetail || !adminToken) return;
    setSupportState('saving');
    setSupportError('');
    try {
      const detail = await adminUpdateSupportStatus(supportDetail.ticket_id, status, adminToken);
      setSupportDetail(detail);
      await loadSupportTickets('admin');
      setSupportState('idle');
    } catch (err) {
      setSupportState('error');
      setSupportError(err instanceof Error ? err.message : 'Stato non aggiornato');
    }
  };

  const archiveTicket = async (ticket: SupportTicketSummary | SupportTicketDetail) => {
    if (supportMode !== 'admin' || !adminToken || ticket.status === 'archived') return;
    const confirmed = window.confirm(`Archivia il ticket "${ticket.subject}"?`);
    if (!confirmed) return;
    setSupportState('saving');
    setSupportError('');
    try {
      await adminUpdateSupportStatus(ticket.ticket_id, 'archived', adminToken);
      setSupportTickets((items) => items.filter((item) => item.ticket_id !== ticket.ticket_id));
      if (supportDetail?.ticket_id === ticket.ticket_id) setSupportDetail(null);
      setSupportState('idle');
    } catch (err) {
      setSupportState('error');
      setSupportError(err instanceof Error ? err.message : 'Ticket non archiviato');
    }
  };

  const startSupportLongPress = (ticket: SupportTicketSummary) => {
    if (supportMode !== 'admin') return;
    if (supportLongPressTimer.current !== null) window.clearTimeout(supportLongPressTimer.current);
    supportLongPressTimer.current = window.setTimeout(() => {
      supportLongPressTimer.current = null;
      supportLongPressHandled.current = true;
      void archiveTicket(ticket);
    }, 650);
  };

  const cancelSupportLongPress = () => {
    if (supportLongPressTimer.current === null) return;
    window.clearTimeout(supportLongPressTimer.current);
    supportLongPressTimer.current = null;
  };

  const closeCurrentTicket = async () => {
    if (!supportDetail) return;
    setSupportState('saving');
    setSupportError('');
    try {
      const detail = supportMode === 'admin' && adminToken
        ? await adminUpdateSupportStatus(supportDetail.ticket_id, 'closed', adminToken)
        : await closeSupportTicket(supportDetail.ticket_id);
      setSupportDetail(detail);
      await loadSupportTickets(supportMode);
      setSupportState('idle');
    } catch (err) {
      setSupportState('error');
      setSupportError(err instanceof Error ? err.message : 'Ticket non chiuso');
    }
  };

  const handleLoadDevBuild = async () => {
    setDevLoadState('loading');
    try {
      const info = await getDevBuildInfo();
      setDevBuildInfo(info);
      setDevLoadState('loaded');
    } catch {
      setDevLoadState('error');
    }
  };

  const statusLabel = (status: TicketStatus) =>
    SUPPORT_STATUSES.find((item) => item.value === status)?.label ?? status;
  const categoryLabel = (category: TicketCategory) =>
    SUPPORT_CATEGORIES.find((item) => item.value === category)?.label ?? category;
  const priorityLabel = (priority: TicketPriority) =>
    SUPPORT_PRIORITIES.find((item) => item.value === priority)?.label ?? priority;

  useEffect(() => {
    void loadSupportTickets('user');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!supportModeRequest || supportModeRequest === supportMode) return;
    if (supportModeRequest === 'admin' && !adminToken) return;
    setSupportMode(supportModeRequest);
    void loadSupportTickets(supportModeRequest);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supportModeRequest, adminToken]);

  useEffect(() => () => {
    if (supportLongPressTimer.current !== null) {
      window.clearTimeout(supportLongPressTimer.current);
    }
  }, []);

  const handleDownload = async (url: string) => {
    onDownloadStart();
    await downloadAndInstall(url);
    onDownloadDone();
  };

  const handleClearFavorites = () => {
    if (favoritesCount === 0) return;
    if (confirm(`Rimuovere tutti i ${favoritesCount} preferiti?`)) onClearFavorites();
  };

  const handleClearAlerts = () => {
    if (alertsCount === 0) return;
    if (confirm(`Eliminare tutti i ${alertsCount} allarmi?`)) onClearAlerts();
  };

  return (
    <div className="space-y-5">

      {/* Aggiornamento app */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Aggiornamento app</h2>
        <div className="bg-dark-800 rounded-xl px-4 py-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-white font-medium">CryptoSentinelAI</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Build #{__APP_BUILD_NUMBER__} · {new Date(__APP_BUILD_DATE__).toLocaleDateString('it-IT', {
                  day: '2-digit', month: '2-digit', year: 'numeric',
                })}
              </p>
            </div>
            {updateState === 'up-to-date' && (
              <span className="text-xs font-semibold text-accent-green bg-accent-green/10 px-2.5 py-1 rounded-full">
                Aggiornata
              </span>
            )}
            {updateState === 'available' && (
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-accent-blue bg-accent-blue/10 px-2.5 py-1 rounded-full">
                  Disponibile
                </span>
                <button
                  onClick={handleCheckUpdate}
                  title="Ricontrolla"
                  className="text-gray-500 hover:text-gray-300 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                </button>
              </div>
            )}
          </div>

          {updateState === 'available' && updateInfo && (
            <div className="bg-accent-blue/10 border border-accent-blue/20 rounded-lg px-3 py-2 flex items-center justify-between">
              <p className="text-xs text-gray-300">
                Aggiornamento del <span className="text-white font-medium">{updateInfo.releaseDate}</span>
              </p>
              {updateInfo.buildNumber && (
                <span className="text-xs text-gray-400 font-mono ml-2">#{updateInfo.buildNumber}</span>
              )}
            </div>
          )}

          {updateState === 'error' && (
            <p className="text-xs text-accent-red">Impossibile verificare. Controlla la connessione.</p>
          )}

          {updateState === 'available' ? (
            <button
              onClick={() => handleDownload(APK_PAGES_URL)}
              disabled={dlState === 'downloading'}
              className="w-full py-2.5 bg-accent-blue text-white text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity disabled:opacity-60"
            >
              {dlState === 'downloading' ? 'Download in corso…' : 'Scarica e installa'}
            </button>
          ) : (
            <button
              onClick={handleCheckUpdate}
              disabled={updateState === 'checking'}
              className="w-full py-2.5 bg-dark-700 text-gray-300 text-sm font-medium rounded-lg hover:bg-dark-600 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {updateState === 'checking' ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Verifica in corso…
                </>
              ) : (
                'Controlla aggiornamenti'
              )}
            </button>
          )}

          {updateState === 'available' && dlState !== 'idle' && (
            <div className={`rounded-lg px-3 py-2.5 flex items-center justify-between gap-3 ${
              dlState === 'done' ? 'bg-accent-green/10 border border-accent-green/20'
              : dlState === 'error' ? 'bg-accent-red/10 border border-accent-red/20'
              : 'bg-accent-blue/10 border border-accent-blue/20'
            }`}>
              <div className="flex items-center gap-2">
                {dlState === 'downloading' ? (
                  <svg className="w-4 h-4 text-accent-blue animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                ) : dlState === 'error' ? (
                  <span className="text-accent-red text-sm">✗</span>
                ) : (
                  <span className="text-accent-green text-sm">✓</span>
                )}
                <p className="text-xs text-gray-300">
                  {dlState === 'downloading' ? 'Download in corso…' : dlState === 'error' ? 'Download fallito — controlla connessione' : 'Download completato'}
                </p>
              </div>
              <button
                onClick={openDownloadsFolder}
                className="text-xs text-accent-blue underline underline-offset-2 whitespace-nowrap"
              >
                📁 Apri Download
              </button>
            </div>
          )}
        </div>
      </section>

      {/* Notifiche */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Notifiche</h2>
        <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
          <div className="px-4 py-3 flex items-center justify-between">
            <div>
              <p className="text-sm text-white">Stato permesso</p>
              <p className="text-xs text-gray-500 mt-0.5">
                {notifPerm === 'granted' ? 'Notifiche attive' : 'Notifiche bloccate'}
              </p>
            </div>
            {notifPerm === 'granted' ? (
              <span className="text-xs font-semibold text-accent-green bg-accent-green/10 px-2.5 py-1 rounded-full">Attive</span>
            ) : (
              <span className="text-xs font-semibold text-accent-red bg-accent-red/10 px-2.5 py-1 rounded-full">Bloccate</span>
            )}
          </div>
          <button
            onClick={openNotificationSettings}
            className="w-full px-4 py-3 flex items-center justify-between text-accent-blue hover:bg-dark-700 transition-colors rounded-b-xl"
          >
            <span className="text-sm">Apri impostazioni notifiche</span>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </section>

      {/* Risparmio energetico */}
      {Capacitor.isNativePlatform() && (
        <section>
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Risparmio energetico</h2>
          <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
            <div className="px-4 py-3 flex items-center justify-between">
              <div>
                <p className="text-sm text-white">Ottimizzazione batteria</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {batteryDismissed ? 'Impostazione verificata' : 'Potrebbe bloccare gli aggiornamenti'}
                </p>
              </div>
              {batteryDismissed ? (
                <span className="text-xs font-semibold text-accent-green bg-accent-green/10 px-2.5 py-1 rounded-full">OK</span>
              ) : (
                <span className="text-xs font-semibold text-accent-yellow bg-accent-yellow/10 px-2.5 py-1 rounded-full">Attenzione</span>
              )}
            </div>
            <button
              onClick={openBatterySettings}
              className="w-full px-4 py-3 flex items-center justify-between text-accent-yellow hover:bg-dark-700 transition-colors rounded-b-xl"
            >
              <span className="text-sm">Apri impostazioni batteria</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </section>
      )}

      {/* Personalizzazione */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Personalizzazione</h2>
        <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
          <div className="px-4 py-3">
            <p className="text-sm text-white mb-1">Valuta di visualizzazione</p>
            <p className="text-xs text-gray-500 mb-3">Cambia la valuta con cui vengono mostrati prezzi e capitalizzazione</p>
            <div className="flex gap-2">
              {([['usd', '$ USD'], ['eur', '€ EUR'], ['btc', '₿ BTC']] as const).map(([c, label]) => (
                <button
                  key={c}
                  onClick={() => onCurrencyChange(c)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    currency === c ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="px-4 py-3">
            <p className="text-sm text-white mb-1">Range slider allarmi</p>
            <p className="text-xs text-gray-500 mb-3">Variazione massima gestibile dallo slider nella modifica di un allarme</p>
            <div className="flex gap-2">
              {([5, 10, 20, 30, 50] as const).map((pct) => (
                <button
                  key={pct}
                  onClick={() => onSliderRangeChange(pct)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    sliderRange === pct ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
                  }`}
                >
                  ±{pct}%
                </button>
              ))}
            </div>
          </div>
          <div className="px-4 py-3">
            <p className="text-sm text-white mb-1">Allarme variazione preferiti</p>
            <p className="text-xs text-gray-500 mb-3">Ricevi una notifica quando il prezzo di un preferito si muove della percentuale impostata</p>
            <div className="space-y-2">
              <div>
                <p className="text-xs text-gray-400 mb-1.5">↑ Rialzo</p>
                <div className="flex gap-2">
                  {([0, 2, 4, 8, 10] as const).map((pct) => (
                    <button
                      key={pct}
                      onClick={() => onFavMoveUpPctChange(pct)}
                      className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                        favMoveUpPct === pct ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
                      }`}
                    >
                      {pct === 0 ? 'Off' : `${pct}%`}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-1.5">↓ Ribasso</p>
                <div className="flex gap-2">
                  {([0, 2, 4, 8, 10] as const).map((pct) => (
                    <button
                      key={pct}
                      onClick={() => onFavMoveDownPctChange(pct)}
                      className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                        favMoveDownPct === pct ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
                      }`}
                    >
                      {pct === 0 ? 'Off' : `${pct}%`}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
          <div className="px-4 py-3">
            <p className="text-sm text-white mb-1">Animazione rank mercato</p>
            <p className="text-xs text-gray-500 mb-3">Illumina la card quando una coin guadagna o perde posizioni nella top N per capitalizzazione</p>
            <div className="flex gap-2">
              {([0, 50, 100, 200] as const).map((n) => (
                <button
                  key={n}
                  onClick={() => onRankAnimTopNChange(n)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    rankAnimTopN === n ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
                  }`}
                >
                  {n === 0 ? 'Off' : `Top ${n}`}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Aggiornamento prezzi */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Aggiornamento prezzi</h2>
        <div className="bg-dark-800 rounded-xl px-4 py-3">
          <p className="text-sm text-white mb-3">Intervallo di aggiornamento</p>
          <div className="flex gap-2">
            {INTERVALS.map(({ label, ms }) => (
              <button
                key={ms}
                onClick={() => onIntervalChange(ms)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                  refreshInterval === ms
                    ? 'bg-accent-blue text-white'
                    : 'bg-dark-700 text-gray-400 hover:text-white'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Supporto */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Supporto</h2>
        <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
          <div className="px-4 py-3">
            <p className="text-sm text-white mb-2">Nome utente</p>
            <div className="flex gap-2">
              <input
                value={supportDisplayName}
                onChange={(event) => setSupportDisplayName(event.target.value)}
                placeholder="Es. Marco S23"
                className="flex-1 bg-dark-700 text-white text-sm rounded-lg px-3 py-2 outline-none border border-dark-600 focus:border-accent-blue"
                maxLength={120}
              />
              <button
                onClick={saveSupportDisplayName}
                className="px-3 py-2 bg-accent-blue text-white text-sm font-semibold rounded-lg disabled:opacity-50"
                disabled={supportState === 'saving'}
              >
                Salva
              </button>
            </div>
          </div>

          <div className="px-4 py-3 space-y-3">
            <div className="flex gap-2">
              <button
                onClick={() => { setSupportMode('user'); void loadSupportTickets('user'); }}
                className={`flex-1 py-2 rounded-lg text-sm font-medium ${supportMode === 'user' ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400'}`}
              >
                I miei ticket
              </button>
              <button
                onClick={() => { setSupportMode('admin'); void loadSupportTickets('admin'); }}
                disabled={!adminToken}
                className={`flex-1 py-2 rounded-lg text-sm font-medium disabled:opacity-40 ${supportMode === 'admin' ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400'}`}
              >
                Admin
              </button>
              <button
                onClick={() => void loadSupportTickets()}
                className="px-3 py-2 bg-dark-700 text-gray-400 rounded-lg text-sm"
              >
                ↻
              </button>
            </div>
            {supportError && <p className="text-xs text-accent-red">{supportError}</p>}
          </div>

          {supportMode === 'user' && (
            <div className="px-4 py-3 space-y-3">
              <p className="text-sm text-white">Apri ticket</p>
              <div className="grid grid-cols-2 gap-2">
                <select
                  value={supportCategory}
                  onChange={(event) => setSupportCategory(event.target.value as TicketCategory)}
                  className="bg-dark-700 text-white text-sm rounded-lg px-3 py-2 outline-none"
                >
                  {SUPPORT_CATEGORIES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
                <select
                  value={supportPriority}
                  onChange={(event) => setSupportPriority(event.target.value as TicketPriority)}
                  className="bg-dark-700 text-white text-sm rounded-lg px-3 py-2 outline-none"
                >
                  {SUPPORT_PRIORITIES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
              </div>
              <input
                value={supportSubject}
                onChange={(event) => setSupportSubject(event.target.value)}
                placeholder="Oggetto"
                className="w-full bg-dark-700 text-white text-sm rounded-lg px-3 py-2 outline-none border border-dark-600 focus:border-accent-blue"
                maxLength={160}
              />
              <textarea
                value={supportMessage}
                onChange={(event) => setSupportMessage(event.target.value)}
                placeholder="Descrivi il problema o la richiesta"
                className="w-full min-h-24 bg-dark-700 text-white text-sm rounded-lg px-3 py-2 outline-none border border-dark-600 focus:border-accent-blue resize-none"
                maxLength={4000}
              />
              <label className="flex items-center justify-between text-sm text-gray-400">
                <span>Includi diagnostica tecnica</span>
                <input
                  type="checkbox"
                  checked={supportDiagnostics}
                  onChange={(event) => setSupportDiagnostics(event.target.checked)}
                  className="w-4 h-4"
                />
              </label>
              <button
                onClick={createTicket}
                disabled={supportState === 'saving' || !supportSubject.trim() || !supportMessage.trim()}
                className="w-full py-2.5 bg-accent-green/20 text-accent-green text-sm font-semibold rounded-lg disabled:opacity-40"
              >
                {supportState === 'saving' ? 'Invio…' : 'Invia ticket'}
              </button>
            </div>
          )}

          <div className="px-4 py-3 space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-sm text-white">Ticket</p>
              <span className="text-xs text-gray-500">{supportTickets.length}</span>
            </div>
            {supportTickets.length === 0 ? (
              <p className="text-xs text-gray-500">Nessun ticket caricato.</p>
            ) : (
              supportTickets.slice(0, 8).map((ticket) => (
                <button
                  key={ticket.ticket_id}
                  onClick={() => {
                    if (supportLongPressHandled.current) {
                      supportLongPressHandled.current = false;
                      return;
                    }
                    void openTicket(ticket);
                  }}
                  onContextMenu={(event) => {
                    if (supportMode !== 'admin') return;
                    event.preventDefault();
                    void archiveTicket(ticket);
                  }}
                  onTouchStart={() => startSupportLongPress(ticket)}
                  onTouchEnd={cancelSupportLongPress}
                  onTouchMove={cancelSupportLongPress}
                  onTouchCancel={cancelSupportLongPress}
                  className={`w-full text-left px-3 py-2 rounded-lg border transition-colors ${
                    ticket.has_unread
                      ? 'bg-amber-500/10 border-amber-500/40 animate-pulse'
                      : supportDetail?.ticket_id === ticket.ticket_id
                        ? 'bg-dark-700 border-accent-blue'
                        : 'bg-dark-700 border-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-sm truncate ${ticket.has_unread ? 'text-amber-400 font-semibold' : 'text-white'}`}>{ticket.subject}</span>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {ticket.has_unread && <span className="w-2 h-2 rounded-full bg-amber-400" />}
                      <span className="text-xs text-gray-400">{statusLabel(ticket.status)}</span>
                    </div>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5 truncate">
                    {supportMode === 'admin' ? `${ticket.display_name} · ` : ''}{categoryLabel(ticket.category)} · <span className={
                      ticket.priority === 'critical' ? 'text-red-400 font-semibold'
                        : ticket.priority === 'high' ? 'text-orange-400 font-semibold'
                          : ticket.priority === 'medium' ? 'text-yellow-400'
                            : 'text-gray-500'
                    }>{priorityLabel(ticket.priority)}</span>
                  </p>
                </button>
              ))
            )}
          </div>

          {supportDetail && (
            <div className="px-4 py-3 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-white font-semibold truncate">{supportDetail.subject}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {supportDetail.display_name} · {statusLabel(supportDetail.status)} · <span className={
                      supportDetail.priority === 'critical' ? 'text-red-400 font-semibold'
                        : supportDetail.priority === 'high' ? 'text-orange-400 font-semibold'
                          : supportDetail.priority === 'medium' ? 'text-yellow-400'
                            : 'text-gray-500'
                    }>{priorityLabel(supportDetail.priority)}</span>
                  </p>
                </div>
                {!['closed', 'archived'].includes(supportDetail.status) && (
                  <button onClick={closeCurrentTicket} className="text-xs px-3 py-1.5 bg-accent-red/15 text-accent-red rounded-lg">
                    Chiudi
                  </button>
                )}
              </div>

              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {supportDetail.messages.map((message) => {
                  const isNew = supportDetail.last_seen_at != null
                    && new Date(message.created_at) > new Date(supportDetail.last_seen_at)
                    && message.sender_type !== (supportMode === 'admin' ? 'admin' : 'user');
                  return (
                    <div
                      key={message.message_id}
                      className={`px-3 py-2 rounded-lg border-l-2 ${
                        isNew
                          ? 'bg-amber-500/10 border-l-amber-400'
                          : message.sender_type === 'admin'
                            ? 'bg-accent-blue/15 border-l-transparent'
                            : 'bg-dark-700 border-l-transparent'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className={`text-xs font-semibold ${isNew ? 'text-amber-400' : 'text-gray-400'}`}>
                          {message.sender_type === 'admin' ? 'Admin' : 'Utente'}
                          {isNew && ' · Nuovo'}
                        </span>
                        <span className="text-[11px] text-gray-600">{new Date(message.created_at).toLocaleString('it-IT')}</span>
                      </div>
                      <p className="text-sm text-gray-200 whitespace-pre-wrap break-words">{message.body}</p>
                    </div>
                  );
                })}
              </div>

              {supportMode === 'admin' && adminToken && (
                <div className="grid grid-cols-2 gap-2">
                  {SUPPORT_STATUSES.filter((item) => item.value !== 'archived').map((item) => (
                    <button
                      key={item.value}
                      onClick={() => void updateTicketStatus(item.value)}
                      className={`py-2 rounded-lg text-xs font-semibold ${supportDetail.status === item.value ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400'}`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              )}

              {!['closed', 'archived'].includes(supportDetail.status) && (
                <div className="space-y-2">
                  <textarea
                    value={supportReply}
                    onChange={(event) => setSupportReply(event.target.value)}
                    placeholder={supportMode === 'admin' ? 'Risposta admin' : 'Rispondi al supporto'}
                    className="w-full min-h-20 bg-dark-700 text-white text-sm rounded-lg px-3 py-2 outline-none border border-dark-600 focus:border-accent-blue resize-none"
                    maxLength={4000}
                  />
                  <button
                    onClick={sendTicketReply}
                    disabled={supportState === 'saving' || !supportReply.trim() || (supportMode === 'admin' && !adminToken)}
                    className="w-full py-2.5 bg-accent-blue text-white text-sm font-semibold rounded-lg disabled:opacity-40"
                  >
                    Invia risposta
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Cancella dati */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Dati</h2>
        <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
          <button
            onClick={handleClearFavorites}
            disabled={favoritesCount === 0}
            className="w-full px-4 py-3 flex items-center justify-between disabled:opacity-40 hover:bg-dark-700 transition-colors rounded-t-xl"
          >
            <div className="text-left">
              <p className="text-sm text-white">Cancella preferiti</p>
              <p className="text-xs text-gray-500 mt-0.5">{favoritesCount} salvati</p>
            </div>
            <span className="text-accent-red text-sm font-medium">Cancella</span>
          </button>
          <button
            onClick={handleClearAlerts}
            disabled={alertsCount === 0}
            className="w-full px-4 py-3 flex items-center justify-between disabled:opacity-40 hover:bg-dark-700 transition-colors rounded-b-xl"
          >
            <div className="text-left">
              <p className="text-sm text-white">Cancella allarmi</p>
              <p className="text-xs text-gray-500 mt-0.5">{alertsCount} impostati</p>
            </div>
            <span className="text-accent-red text-sm font-medium">Cancella</span>
          </button>
        </div>
      </section>

      {/* Informazioni */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Informazioni</h2>
        <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-gray-400">Applicazione</span>
            <span className="text-sm text-white font-medium">CryptoSentinelAI</span>
          </div>
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-gray-400">Versione</span>
            <span className="text-sm text-white font-medium font-mono">
              v1.0.{__APP_BUILD_NUMBER__}
            </span>
          </div>
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-gray-400">Sviluppatore</span>
            <span className="text-sm text-white font-medium">Iridexx</span>
          </div>
          <a
            href="https://www.coingecko.com"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-3 flex items-center gap-3 hover:bg-dark-700 active:bg-dark-600 transition-colors group"
          >
            <span className="text-xs font-bold w-7 text-center flex-shrink-0">CG</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-white font-medium">CoinGecko</p>
              <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                Grazie per il servizio di dati di mercato
              </p>
            </div>
          </a>
          <a
            href="https://coinmarketcap.com"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-3 flex items-center gap-3 hover:bg-dark-700 active:bg-dark-600 transition-colors group"
          >
            <span className="text-xs font-bold w-7 text-center flex-shrink-0">CMC</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-white font-medium">CoinMarketCap</p>
              <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                Grazie per il servizio di dati di mercato
              </p>
            </div>
          </a>
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-gray-400">Dati personali</span>
            <span className="text-sm text-accent-green font-medium">Nessuno raccolto</span>
          </div>
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-gray-400">Archiviazione</span>
            <span className="text-sm text-white font-medium">Solo locale</span>
          </div>
          <a
            href="https://www.gnu.org/licenses/gpl-3.0.html"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-3 flex items-center justify-between hover:bg-dark-700 transition-colors rounded-b-xl"
          >
            <span className="text-sm text-gray-400">Licenza</span>
            <div className="flex items-center gap-1.5">
              <span className="text-sm text-white font-medium">GPL v3</span>
              <svg className="w-3.5 h-3.5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </div>
          </a>
        </div>
      </section>

      {/* Social */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Sviluppatore</h2>
        <a
          href="https://x.com/eifel3btc"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 bg-dark-800 rounded-xl px-4 py-3 hover:bg-dark-700 active:bg-dark-600 transition-colors group"
        >
          <div className="w-9 h-9 bg-white rounded-lg flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="black">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.748l7.73-8.835L1.254 2.25H8.08l4.253 5.622 5.91-5.622Zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-white font-semibold">Seguimi su X</p>
            <p className="text-xs text-gray-500 mt-0.5">@eifel3btc</p>
          </div>
          <svg className="w-4 h-4 text-gray-600 group-hover:text-gray-400 transition-colors flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </a>
      </section>

      {/* Donazioni */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Supporta lo sviluppatore</h2>
        <div className="bg-dark-800 rounded-xl divide-y divide-dark-700">
          <a
            href="https://buymeacoffee.com/eifel3btc"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-3 flex items-center gap-3 hover:bg-dark-700 transition-colors rounded-t-xl group"
          >
            <span className="text-xl w-7 text-center flex-shrink-0">☕</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-white font-medium">Buy Me a Coffee</p>
              <p className="text-xs text-gray-500 mt-0.5">Carta di credito · PayPal</p>
            </div>
            <svg className="w-4 h-4 text-gray-600 group-hover:text-gray-400 transition-colors flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
          {DONATION_OPTIONS.map((opt, i) => (
            <DonationRow
              key={opt.address}
              {...opt}
              last={i === DONATION_OPTIONS.length - 1}
            />
          ))}
        </div>
      </section>

      {/* Modalità Sviluppatore */}
      <section>
        {devState === 'locked' && (
          <button
            onClick={() => { setDevState('pin-entry'); setPinError(false); setPinInput(''); }}
            className="w-full text-center text-xs text-gray-700 hover:text-gray-500 transition-colors py-2"
          >
            🔒 Modalità Sviluppatore
          </button>
        )}

        {devState === 'pin-entry' && (
          <div className="bg-dark-800 rounded-xl px-4 py-4">
            <p className="text-sm text-white font-medium text-center mb-3">Inserisci PIN</p>
            <input
              type="password"
              inputMode="numeric"
              maxLength={4}
              value={pinInput}
              onChange={(e) => { setPinInput(e.target.value.replace(/\D/g, '')); setPinError(false); }}
              onKeyDown={(e) => e.key === 'Enter' && handlePinSubmit()}
              placeholder="• • • •"
              className={`w-full bg-dark-700 border rounded-lg px-4 py-2.5 text-center text-white text-xl tracking-widest outline-none transition-colors mb-3 ${
                pinError ? 'border-accent-red' : 'border-dark-600 focus:border-accent-blue'
              }`}
              autoFocus
            />
            {pinError && <p className="text-xs text-accent-red text-center mb-3">PIN errato</p>}
            <div className="flex gap-2">
              <button onClick={() => setDevState('locked')} className="flex-1 py-2 bg-dark-700 text-gray-400 text-sm rounded-lg">Annulla</button>
              <button onClick={handlePinSubmit} disabled={pinInput.length !== 4} className="flex-1 py-2 bg-accent-blue text-white text-sm font-semibold rounded-lg disabled:opacity-40">Sblocca</button>
            </div>
          </div>
        )}

        {devState === 'unlocked' && (
          <div className="bg-dark-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-accent-blue/10 border-b border-dark-700 flex items-center justify-between">
              <span className="text-sm font-semibold text-accent-blue">⚙️ Modalità Sviluppatore</span>
              <button onClick={() => setDevState('locked')} className="text-gray-500 text-lg">×</button>
            </div>
            <div className="px-4 py-4 space-y-3">

              {/* ── Diagnostica Backend ── */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Diagnostica</span>
                  <button
                    onClick={handleDiagnostic}
                    disabled={diagState === 'checking'}
                    className="flex items-center gap-1.5 px-3 py-1 bg-dark-700 text-gray-300 text-xs rounded-lg hover:bg-dark-600 transition-colors disabled:opacity-50"
                  >
                    {diagState === 'checking' ? (
                      <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>
                    ) : (
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                    )}
                    {diagState === 'checking' ? 'Test…' : 'Testa'}
                  </button>
                </div>

                <div className="bg-dark-700 rounded-lg divide-y divide-dark-600">
                  {/* Backend URL */}
                  <div className="px-3 py-2 flex justify-between items-center gap-2">
                    <span className="text-xs text-gray-500 flex-shrink-0">Backend URL</span>
                    {diagResult ? (
                      diagResult.backendUrl
                        ? <span className="text-xs font-mono text-gray-300 truncate text-right max-w-[55%]">{diagResult.backendUrl.replace(/https?:\/\//, '')}</span>
                        : <span className="text-xs text-accent-red font-mono">non configurato</span>
                    ) : <span className="text-xs text-gray-600">—</span>}
                  </div>
                  {/* Device Token */}
                  <div className="px-3 py-2 flex justify-between items-center">
                    <span className="text-xs text-gray-500">Device Token</span>
                    {diagResult ? (
                      diagResult.deviceTokenSet
                        ? <span className="text-xs text-accent-green font-semibold">✓ configurato</span>
                        : <span className="text-xs text-accent-red">✗ mancante</span>
                    ) : <span className="text-xs text-gray-600">—</span>}
                  </div>
                  <div className="px-3 py-2 flex justify-between items-center">
                    <span className="text-xs text-gray-500">Read Token</span>
                    {diagResult ? (
                      diagResult.readTokenSet
                        ? <span className="text-xs text-accent-green font-semibold">configurato</span>
                        : <span className="text-xs text-accent-red">mancante</span>
                    ) : <span className="text-xs text-gray-600">-</span>}
                  </div>
                  <div className="px-3 py-2 flex justify-between items-center">
                    <span className="text-xs text-gray-500">Alert Token</span>
                    {diagResult ? (
                      diagResult.alertsTokenSet
                        ? <span className="text-xs text-accent-green font-semibold">✓ configurato</span>
                        : <span className="text-xs text-accent-red">✗ mancante</span>
                    ) : <span className="text-xs text-gray-600">—</span>}
                  </div>
                  {/* Backend raggiungibile */}
                  <div className="px-3 py-2 flex justify-between items-center">
                    <span className="text-xs text-gray-500">Backend</span>
                    {diagResult ? (
                      diagResult.backendReachable
                        ? <span className="text-xs text-accent-green font-semibold">✓ online {diagResult.backendLatencyMs != null ? `· ${diagResult.backendLatencyMs}ms` : ''}</span>
                        : <span className="text-xs text-accent-red">✗ {diagResult.error ?? 'irraggiungibile'}</span>
                    ) : <span className="text-xs text-gray-600">—</span>}
                  </div>
                  <div className="px-3 py-2 flex justify-between items-center">
                    <span className="text-xs text-gray-500">Device registrati</span>
                    {diagResult ? (
                      diagResult.deviceCount != null
                        ? <span className="text-xs text-accent-green font-semibold">{diagResult.deviceCount}</span>
                        : <span className="text-xs text-gray-600">—</span>
                    ) : <span className="text-xs text-gray-600">—</span>}
                  </div>
                </div>
                {diagResult && diagResult.registrationLog.length > 0 && (
                  <div className="bg-dark-900 rounded-lg px-3 py-2 space-y-0.5 max-h-32 overflow-y-auto">
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Push log</p>
                    {diagResult.registrationLog.map((line, i) => (
                      <p key={i} className="text-xs text-gray-500 font-mono leading-relaxed">{line}</p>
                    ))}
                  </div>
                )}
                {diagResult && (
                  <p className="text-xs text-gray-600 text-right">Aggiornato alle {diagResult.checkedAt}</p>
                )}
              </div>

              <div className="border-t border-dark-600" />

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Market data provider</span>
                  <button
                    onClick={handleLoadProvider}
                    disabled={providerLoadState === 'loading'}
                    className="px-3 py-1 bg-dark-700 text-gray-300 text-xs rounded-lg disabled:opacity-50"
                  >
                    {providerLoadState === 'loading' ? 'Loading...' : 'Refresh'}
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {(['cmc', 'coingecko'] as ProviderName[]).map(provider => (
                    <button
                      key={provider}
                      onClick={() => handleProviderChange(provider)}
                      disabled={!adminToken || providerLoadState === 'loading'}
                      className={`py-2 rounded-lg text-xs font-semibold uppercase transition-colors disabled:opacity-40 ${
                        providerState?.active === provider
                          ? 'bg-accent-blue text-white'
                          : 'bg-dark-700 text-gray-400'
                      }`}
                    >
                      {provider}
                    </button>
                  ))}
                </div>
                <input
                  type="password"
                  value={adminToken}
                  onChange={(event) => onAdminToken(event.target.value)}
                  placeholder="Admin token salvato"
                  autoComplete="off"
                  className="w-full bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-accent-blue font-mono"
                />
                <p className="text-xs text-gray-600">
                  Global selection, no automatic fallback. The configured default is restored after backend restart.
                </p>
                {providerLoadState === 'error' && (
                  <p className="text-xs text-accent-red">Unable to read or update the provider.</p>
                )}
              </div>

              <div className="border-t border-dark-600" />

              {/* ── Reset database ── */}
              <div className="space-y-2">
                <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Database</span>
                <p className="text-xs text-gray-600">Azzera trade, decisioni, posizioni, PnL, portfolio e grafici. Impostazioni e watchlist restano. Prima di azzerare puoi salvare un backup con un nome.</p>
                <button
                  onClick={handleResetDb}
                  disabled={!adminToken || resetState === 'working'}
                  className="w-full py-2.5 bg-accent-red/20 text-accent-red text-sm font-semibold rounded-lg hover:bg-accent-red/30 transition-colors disabled:opacity-40"
                >
                  {resetState === 'working' ? 'Esecuzione…' : '🗑 Resetta database'}
                </button>
                {!adminToken && <p className="text-xs text-gray-600">Richiede admin token (sopra).</p>}
                {resetMsg && <p className={`text-xs ${resetState === 'error' ? 'text-accent-red' : 'text-accent-green'}`}>{resetMsg}</p>}
              </div>

              <div className="border-t border-dark-600" />

              {devLoadState === 'idle' && (
                <button onClick={handleLoadDevBuild} className="w-full py-2.5 bg-dark-700 text-gray-300 text-sm rounded-lg hover:bg-dark-600 transition-colors">Controlla ultima dev build</button>
              )}
              {devLoadState === 'loading' && (
                <div className="flex items-center justify-center gap-2 py-2 text-gray-400 text-sm">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Caricamento…
                </div>
              )}
              {devLoadState === 'error' && (
                <p className="text-xs text-accent-red text-center">Errore nel caricamento. Nessuna dev build disponibile.</p>
              )}
              {devLoadState === 'loaded' && devBuildInfo && (
                <>
                  <div className="bg-dark-700 rounded-lg divide-y divide-dark-600">
                    <div className="px-3 py-2 flex justify-between"><span className="text-xs text-gray-500">Build</span><span className="text-xs text-white font-mono">#{devBuildInfo.buildNumber ?? '—'}</span></div>
                    <div className="px-3 py-2 flex justify-between"><span className="text-xs text-gray-500">Branch</span><span className="text-xs text-accent-blue font-mono truncate max-w-[60%] text-right">{devBuildInfo.branch ?? '—'}</span></div>
                    <div className="px-3 py-2 flex justify-between"><span className="text-xs text-gray-500">Data</span><span className="text-xs text-white">{devBuildInfo.buildDate}</span></div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={handleLoadDevBuild} className="p-2.5 bg-dark-700 text-gray-400 rounded-lg hover:text-white transition-colors" title="Aggiorna">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                    </button>
                    {devBuildInfo.downloadUrl && (
                      <button onClick={() => handleDownload(devBuildInfo.downloadUrl!)} disabled={dlState === 'downloading'} className="flex-1 py-2.5 bg-accent-blue text-white text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity disabled:opacity-60">
                        {dlState === 'downloading' ? 'Download in corso…' : `Scarica build #${devBuildInfo.buildNumber}`}
                      </button>
                    )}
                  </div>
                  {dlState !== 'idle' && (
                    <div className={`rounded-lg px-3 py-2.5 flex items-center justify-between gap-3 ${dlState === 'done' ? 'bg-accent-green/10 border border-accent-green/20' : 'bg-accent-blue/10 border border-accent-blue/20'}`}>
                      <div className="flex items-center gap-2 min-w-0">
                        {dlState === 'downloading' ? (<svg className="w-4 h-4 text-accent-blue flex-shrink-0 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>) : (<span className="text-accent-green text-sm flex-shrink-0">✓</span>)}
                        <p className="text-xs text-gray-300 truncate">{dlState === 'downloading' ? 'Download in corso…' : 'Download completato'}</p>
                      </div>
                      <button onClick={openDownloadsFolder} className="flex-shrink-0 text-xs text-accent-blue underline underline-offset-2 whitespace-nowrap">📁 Apri Download</button>
                    </div>
                  )}
                  <div className="border-t border-dark-600 pt-3 space-y-2">
                    <p className="text-xs text-gray-500">GitHub Token (PAT con scope repo)</p>
                    <div className="flex gap-2">
                      <input type={showToken ? 'text' : 'password'} value={ghToken} onChange={(e) => handleSaveToken(e.target.value)} placeholder="ghp_xxxxxxxxxxxx" className="flex-1 bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-accent-blue font-mono" />
                      <button onClick={() => setShowToken(v => !v)} className="px-2.5 bg-dark-700 text-gray-400 rounded-lg text-xs">{showToken ? 'Nascondi' : 'Mostra'}</button>
                    </div>
                    {mergeState === 'done' ? (
                      <div className="py-2.5 bg-accent-green/10 border border-accent-green/20 rounded-lg text-center text-xs text-accent-green font-semibold">✓ Merge completato su main</div>
                    ) : (
                      <button onClick={handleMerge} disabled={!ghToken || !devBuildInfo.branch || mergeState === 'merging'} className="w-full py-2.5 bg-accent-green/20 text-accent-green text-sm font-semibold rounded-lg hover:bg-accent-green/30 transition-colors disabled:opacity-40 flex items-center justify-center gap-2">
                        {mergeState === 'merging' ? (<><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>Merge in corso…</>) : ('Valida e merga in main')}
                      </button>
                    )}
                    {mergeState === 'error' && <p className="text-xs text-accent-red">{mergeError}</p>}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </section>

    </div>
  );
};

export default SettingsTab;
