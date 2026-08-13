import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  addExecutionWallet,
  fetchAgentDecisions,
  fetchAgentStatus,
  fetchAssetBreakdown,
  fetchDataCoverage,
  fetchEquityCurve,
  fetchExecutionStatus,
  fetchExecutionWallets,
  fetchGlobal,
  fetchHeartbeat,
  fetchLive,
  fetchLogs,
  fetchMarkets,
  fetchNotificationPrefs,
  fetchOperationalStats,
  fetchPerp,
  fetchReady,
  fetchSettings,
  fetchSpot,
  fetchSupportTicket,
  fetchSupportTickets,
  fetchSupportNotifications,
  markSupportTicketRead,
  markAllSupportTicketsRead,
  fetchTradeDetail,
  replySupportTicket,
  resetDatabase,
  adjustEquity,
  fetchEquityAdjustments,
  saveNotificationPrefs,
  saveSettings,
  sendToken,
  setKillSwitch,
  setExecutionNetwork,
  setExecutionWallet,
  setPerpExecutionProvider,
  setRpcEndpoint,
  setSpotExecutionProvider,
  updateSupportTicketStatus,
  validateOnboarding,
  defaultBackendBaseUrl,
  normalizeBackendBaseUrl,
  type DashboardSession,
  type EquityAdjustment,
} from './api';
import type {
  AgentDecisionResponse,
  AgentSettings,
  NotificationPreferences,
  NotificationPreferencesResponse,
  AgentStatus,
  AssetBreakdownResponse,
  CredentialCheck,
  DataCoverageItem,
  DataCoverageResponse,
  EquityCurveResponse,
  EquityRange,
  ExecutionStatus,
  ExecutionWalletsResponse,
  GlobalView,
  HealthPayload,
  KillSwitchState,
  LogEntry,
  MarketAsset,
  OperationalStats,
  PerpView,
  SettingsResponse,
  SpotView,
  SupportTicketDetail,
  SupportTicketListResponse,
  SupportNotificationResponse,
  SupportTicketStatus,
  TradeChart,
  TradeDetail,
} from './types';

type Tab = 'overview' | 'spot' | 'perp' | 'global' | 'analytics' | 'health' | 'wallet' | 'support' | 'logs' | 'settings' | 'onboarding' | 'markets' | 'export';
type LoadState<T> = { data: T | null; loading: boolean; error: string | null };

const tabs: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'spot', label: 'Spot' },
  { id: 'perp', label: 'Perp' },
  { id: 'global', label: 'Global' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'health', label: 'Health' },
  { id: 'wallet', label: 'Wallet' },
  { id: 'support', label: 'Support' },
  { id: 'logs', label: 'Logs' },
  { id: 'settings', label: 'Settings' },
  { id: 'onboarding', label: 'Onboarding' },
  { id: 'markets', label: 'Markets' },
  { id: 'export', label: 'Export' },
];

const settingFields = [
  'mode',
  'markets_enabled',
  'execution_mode',
  'network',
  'daily_loss_limit_pct',
  'drawdown_cap_pct',
  'spot_capital_per_trade_pct',
  'spot_per_trade_pct',
  'spot_max_open_positions',
  'spot_max_exposure_pct',
  'spot_cooldown_minutes',
  'spot_max_slippage_pct',
  'perp_capital_per_trade_pct',
  'perp_per_trade_pct',
  'perp_max_open_positions',
  'perp_max_exposure_pct',
  'perp_cooldown_minutes',
  'perp_max_slippage_pct',
  'perp_fixed_margin_enabled',
  'perp_fixed_margin_usd',
  'spot_confidence_threshold',
  'spot_trailing_distance_pct',
  'perp_min_leverage',
  'perp_max_leverage',
  'perp_trailing_pnl_pct',
  'spot_tp1_close_pct',
  'perp_tp1_close_pct',
  'post_close_candles',
  'spot_trailing_enabled',
  'perp_trailing_enabled',
  'spot_time_stop_enabled',
  'spot_time_stop_hours',
  'perp_time_stop_enabled',
  'perp_time_stop_hours',
  'spot_breakeven_mode',
  'perp_breakeven_mode',
  'spot_sl_mode',
  'perp_sl_mode',
  'spot_structural_stop_buffer_pct',
  'perp_structural_stop_buffer_pct',
  'perp_trend_shock_enabled',
  'perp_trend_shock_adx_threshold',
  'perp_trend_shock_natr_percentile',
  'perp_trend_shock_volume_threshold',
  'perp_trend_shock_recovery_confirmations',
];

const AUTO_REFRESH_MS = 45_000;

function emptyState<T>(data: T | null = null): LoadState<T> {
  return { data, loading: false, error: null };
}

async function loadDetail<T>(setter: (value: LoadState<T>) => void, task: () => Promise<T>) {
  setter({ data: null, loading: true, error: null });
  try {
    setter({ data: await task(), loading: false, error: null });
  } catch (error) {
    setter({ data: null, loading: false, error: error instanceof Error ? error.message : 'Request failed' });
  }
}

function normalizedStoredBackendUrl() {
  const stored = localStorage.getItem('cs.dashboard.baseUrl');
  return stored ? normalizeBackendBaseUrl(stored) : defaultBackendBaseUrl();
}

export default function App() {
  const [tab, setTab] = useState<Tab>('overview');
  const [session, setSession] = useState<DashboardSession>(() => ({
    baseUrl: normalizedStoredBackendUrl(),
    readToken: localStorage.getItem('cs.dashboard.readToken') || '',
    adminToken: localStorage.getItem('cs.dashboard.adminToken') || '',
  }));
  const [spot, setSpot] = useState<LoadState<SpotView>>(emptyState());
  const [perp, setPerp] = useState<LoadState<PerpView>>(emptyState());
  const [global, setGlobal] = useState<LoadState<GlobalView>>(emptyState());
  const [equity, setEquity] = useState<LoadState<EquityCurveResponse>>(emptyState());
  const [equityRange, setEquityRange] = useState<EquityRange>('24h');
  const equityRangeRef = useRef<EquityRange>('24h');
  equityRangeRef.current = equityRange;
  const [decisions, setDecisions] = useState<LoadState<AgentDecisionResponse>>(emptyState());
  const [decisionsOffset, setDecisionsOffset] = useState(0);
  const decisionsOffsetRef = useRef(0);
  const [assetBreakdown, setAssetBreakdown] = useState<LoadState<AssetBreakdownResponse>>(emptyState());
  const [operationalStats, setOperationalStats] = useState<LoadState<OperationalStats>>(emptyState());
  const [agent, setAgent] = useState<LoadState<AgentStatus>>(emptyState());
  const [ready, setReady] = useState<LoadState<HealthPayload>>(emptyState());
  const [live, setLive] = useState<LoadState<HealthPayload>>(emptyState());
  const [heartbeat, setHeartbeat] = useState<LoadState<HealthPayload>>(emptyState());
  const [execution, setExecution] = useState<LoadState<ExecutionStatus>>(emptyState());
  const [wallets, setWallets] = useState<LoadState<ExecutionWalletsResponse>>(emptyState());
  const [coverage, setCoverage] = useState<LoadState<DataCoverageResponse>>(emptyState());
  const [logs, setLogs] = useState<LoadState<LogEntry[]>>(emptyState([]));
  const [supportTickets, setSupportTickets] = useState<LoadState<SupportTicketListResponse>>(emptyState({ items: [], total: 0 }));
  const [supportDetail, setSupportDetail] = useState<LoadState<SupportTicketDetail>>(emptyState());
  const [supportNotifications, setSupportNotifications] = useState<LoadState<SupportNotificationResponse>>(emptyState());
  const [supportReply, setSupportReply] = useState('');
  const [supportArchived, setSupportArchived] = useState(false);
  const [settings, setSettings] = useState<LoadState<SettingsResponse>>(emptyState());
  const [settingsDraft, setSettingsDraft] = useState<AgentSettings>({});
  const [equityInput, setEquityInput] = useState('');
  const [equityHistory, setEquityHistory] = useState<EquityAdjustment[]>([]);
  const [checks, setChecks] = useState<LoadState<CredentialCheck[]>>(emptyState([]));
  const [markets, setMarkets] = useState<LoadState<MarketAsset[]>>(emptyState([]));
  const [notice, setNotice] = useState('');
  const [walletDraft, setWalletDraft] = useState('');
  const [notifPrefs, setNotifPrefs] = useState<LoadState<NotificationPreferencesResponse>>(emptyState());

  const canRead = Boolean(session.readToken);
  const canAdmin = Boolean(session.adminToken);

  useEffect(() => {
    setSession((current) => {
      const normalized = normalizeBackendBaseUrl(current.baseUrl);
      return normalized === current.baseUrl ? current : { ...current, baseUrl: normalized };
    });
  }, []);

  useEffect(() => {
    localStorage.setItem('cs.dashboard.baseUrl', session.baseUrl);
    localStorage.setItem('cs.dashboard.readToken', session.readToken);
    localStorage.setItem('cs.dashboard.adminToken', session.adminToken);
  }, [session.baseUrl, session.readToken, session.adminToken]);

  useEffect(() => {
    void refreshCore();
  }, []);

  // Refetch della sola curva equity quando cambia il range (24h/7g/Tutto).
  const equityInitialized = useRef(false);
  useEffect(() => {
    if (!equityInitialized.current) { equityInitialized.current = true; return; }
    if (!canRead) return;
    void silentLoad(setEquity, () => fetchEquityCurve(session, 'global', equityRange));
  }, [equityRange]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshCore(true);
    }, AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [session.baseUrl, session.readToken]);

  async function load<T>(setter: (value: LoadState<T>) => void, task: () => Promise<T>) {
    setter({ data: null, loading: true, error: null });
    try {
      const data = await task();
      setter({ data, loading: false, error: null });
      return data;
    } catch (error) {
      setter({ data: null, loading: false, error: error instanceof Error ? error.message : 'Request failed' });
      return null;
    }
  }

  async function silentLoad<T>(setter: (value: LoadState<T>) => void, task: () => Promise<T>) {
    try {
      setter({ data: await task(), loading: false, error: null });
    } catch { /* keep existing data on background refresh error */ }
  }

  async function refreshCore(silent = false) {
    function fetch<T>(setter: (v: LoadState<T>) => void, task: () => Promise<T>) {
      return silent ? silentLoad(setter, task) : load(setter, task);
    }
    await Promise.all([
      fetch(setLive, () => fetchLive(session)),
      canRead ? fetch(setSpot, () => fetchSpot(session)) : Promise.resolve(null),
      canRead ? fetch(setPerp, () => fetchPerp(session)) : Promise.resolve(null),
      canRead ? fetch(setGlobal, () => fetchGlobal(session)) : Promise.resolve(null),
      canRead ? fetch(setEquity, () => fetchEquityCurve(session, 'global', equityRangeRef.current)) : Promise.resolve(null),
      canRead ? fetch(setDecisions, () => fetchAgentDecisions(session, undefined, decisionsOffsetRef.current)) : Promise.resolve(null),
      canRead ? fetch(setAssetBreakdown, () => fetchAssetBreakdown(session, 'spot')) : Promise.resolve(null),
      canRead ? fetch(setOperationalStats, () => fetchOperationalStats(session)) : Promise.resolve(null),
      canRead ? fetch(setAgent, () => fetchAgentStatus(session)) : Promise.resolve(null),
      canRead ? fetch(setReady, () => fetchReady(session)) : Promise.resolve(null),
      canRead ? fetch(setHeartbeat, () => fetchHeartbeat(session)) : Promise.resolve(null),
      canRead ? fetch(setExecution, () => fetchExecutionStatus(session)) : Promise.resolve(null),
      canRead ? fetch(setWallets, () => fetchExecutionWallets(session)) : Promise.resolve(null),
      canRead ? fetch(setCoverage, () => fetchDataCoverage(session)) : Promise.resolve(null),
      canAdmin ? fetch(setSupportNotifications, () => fetchSupportNotifications(session)) : Promise.resolve(null),
    ]);
  }

  async function loadDecisionsPage(newOffset: number) {
    if (!canRead) return;
    decisionsOffsetRef.current = newOffset;
    setDecisionsOffset(newOffset);
    await load(setDecisions, () => fetchAgentDecisions(session, undefined, newOffset));
  }

  async function refreshLogs() {
    if (!canAdmin) {
      setLogs({ data: [], loading: false, error: 'Admin token required' });
      return;
    }
    setLogs({ data: [], loading: true, error: null });
    try {
      const response = await fetchLogs(session, { limit: 250 });
      setLogs({ data: response.entries, loading: false, error: null });
    } catch (error) {
      setLogs({ data: [], loading: false, error: error instanceof Error ? error.message : 'Request failed' });
    }
  }

  async function refreshSupport() {
    if (!canAdmin) {
      setSupportTickets({ data: { items: [], total: 0 }, loading: false, error: 'Admin token required' });
      return;
    }
    const response = await load(setSupportTickets, () => fetchSupportTickets(session, { archived: supportArchived }));
    if (response && !supportArchived) {
      await markAllSupportTicketsRead(session);
    }
    await load(setSupportNotifications, () => fetchSupportNotifications(session));
  }

  async function setSupportArchiveView(archived: boolean) {
    setSupportArchived(archived);
    setSupportDetail(emptyState());
    if (!canAdmin) return;
    await load(setSupportTickets, () => fetchSupportTickets(session, { archived }));
  }

  async function openSupportTicket(ticketId: string) {
    if (!canAdmin) return;
    const detail = await load(setSupportDetail, () => fetchSupportTicket(session, ticketId));
    if (detail) {
      await markSupportTicketRead(session, ticketId);
      await silentLoad(setSupportNotifications, () => fetchSupportNotifications(session));
    }
  }

  async function submitSupportReply() {
    if (!canAdmin || !supportDetail.data || !supportReply.trim()) return;
    const detail = await load(setSupportDetail, () => replySupportTicket(session, supportDetail.data!.ticket_id, supportReply.trim()));
    if (detail) {
      setSupportReply('');
      await refreshSupport();
    }
  }

  async function updateSupportStatus(status: SupportTicketStatus) {
    if (!canAdmin || !supportDetail.data) return;
    const detail = await load(setSupportDetail, () => updateSupportTicketStatus(session, supportDetail.data!.ticket_id, status));
    if (detail) {
      if (status === 'archived' && !supportArchived) setSupportDetail(emptyState());
      await refreshSupport();
    }
  }

  async function refreshSettings() {
    if (!canRead) return;
    const response = await load(setSettings, () => fetchSettings(session));
    if (response) setSettingsDraft(response.settings);
  }

  async function submitSettings() {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const response = await load(setSettings, () => saveSettings(session, settingsDraft));
    if (response) {
      setSettingsDraft(response.settings);
      setNotice('Settings saved');
    }
  }

  async function refreshEquityHistory() {
    if (!canRead) return;
    try {
      const response = await fetchEquityAdjustments(session);
      setEquityHistory(response.items);
    } catch {
      // best-effort
    }
  }

  async function submitAdjustEquity() {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const amount = Number(equityInput);
    if (equityInput.trim() === '' || !Number.isFinite(amount) || amount === 0) {
      setNotice('Importo non valido');
      return;
    }
    const verb = amount >= 0 ? 'Versare' : 'Prelevare';
    if (!window.confirm(`${verb} ${Math.abs(amount).toFixed(2)}$ di liquidità? Aggiorna l'equity, non il PnL.`)) return;
    try {
      const result = await adjustEquity(session, amount, null);
      setNotice(`Applicato ${amount >= 0 ? '+' : ''}${amount}$. Equity ora: ${Number(result.total_equity_usd).toFixed(2)}$.`);
      setEquityInput('');
      await refreshEquityHistory();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Adjust equity failed');
    }
  }

  async function submitResetDb() {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
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
    try {
      const result = await resetDatabase(session, backupName);
      const total = Object.values(result.deleted).reduce((a, b) => a + b, 0);
      const agente = result.kill_switch ? ` Agente: ${result.kill_switch}.` : '';
      setNotice(result.archived_run_id
        ? `Database azzerato (${total} record). Backup: "${result.backup_label}".${agente}`
        : `Database azzerato (${total} record). Nessun backup.${agente}`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Reset database failed');
    }
  }

  async function runOnboarding() {
    if (!canAdmin) {
      setChecks({ data: [], loading: false, error: 'Admin token required' });
      return;
    }
    const response = await load(setChecks, () => validateOnboarding(session).then((payload) => payload.checks));
    if (response) setNotice('Onboarding validation completed');
  }

  async function updateKillSwitch(state: KillSwitchState) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const response = await load(setAgent, () => setKillSwitch(session, state));
    if (response) setNotice(`Kill switch set to ${state}`);
  }

  async function refreshMarkets() {
    if (!canRead) return;
    const response = await load(setMarkets, () => fetchMarkets(session, 100).then((payload) => payload.items));
    if (response) setNotice('Market snapshot updated');
  }

  async function refreshNotifPrefs() {
    if (!canRead) return;
    await load(setNotifPrefs, () => fetchNotificationPrefs(session));
  }

  async function toggleNotifPref(key: keyof NotificationPreferences) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const current = notifPrefs.data?.preferences;
    if (!current) return;
    const updated: NotificationPreferences = { ...current, [key]: !current[key] };
    const response = await load(setNotifPrefs, () => saveNotificationPrefs(session, updated));
    if (response) setNotice(`Notification preference "${key}" updated`);
  }

  async function updateSpotProvider(provider: string) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    await setSpotExecutionProvider(session, provider);
    await load(setWallets, () => fetchExecutionWallets(session));
    await load(setExecution, () => fetchExecutionStatus(session));
    setNotice(`Spot provider set to ${provider}`);
  }

  async function updatePerpProvider(provider: string) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    await setPerpExecutionProvider(session, provider);
    await load(setWallets, () => fetchExecutionWallets(session));
    await load(setExecution, () => fetchExecutionStatus(session));
    setNotice(`Perp provider set to ${provider}`);
  }

  async function updateRpcEndpoint(index: number) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const response = await load(setWallets, () => setRpcEndpoint(session, index));
    if (response) setNotice(`RPC endpoint ${index + 1} selected`);
  }

  async function updateExecutionNetwork(network: 'testnet' | 'mainnet') {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const response = await load(setWallets, () => setExecutionNetwork(session, network));
    if (response) {
      await load(setExecution, () => fetchExecutionStatus(session));
      setNotice(`BSC ${network} selected`);
    }
  }

  async function updateExecutionWallet(address: string) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const response = await load(setWallets, () => setExecutionWallet(session, address));
    if (response) {
      await load(setExecution, () => fetchExecutionStatus(session));
      setNotice('Wallet selected');
    }
  }

  async function submitWalletAddress() {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const address = walletDraft.trim();
    if (!address) return;
    const response = await load(setWallets, () => addExecutionWallet(session, address));
    if (response) {
      setWalletDraft('');
      await load(setExecution, () => fetchExecutionStatus(session));
      setNotice('Wallet added');
    }
  }

  const exportPayload = useMemo(
    () => ({
      generated_at: new Date().toISOString(),
      scope: 'step8_dashboard_export',
      spot: spot.data,
      global: global.data,
      analytics: {
        equity_curve: equity.data,
        decisions: decisions.data,
        asset_breakdown: assetBreakdown.data,
        operational_stats: operationalStats.data,
      },
      agent: agent.data,
      health: {
        live: live.data,
        ready: ready.data,
        heartbeat: heartbeat.data,
        execution: execution.data,
        wallets: wallets.data,
        data_coverage: coverage.data,
      },
    }),
    [
      agent.data,
      assetBreakdown.data,
      coverage.data,
      decisions.data,
      equity.data,
      execution.data,
      global.data,
      heartbeat.data,
      live.data,
      operationalStats.data,
      ready.data,
      spot.data,
      wallets.data,
    ],
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">CS</span>
          <div>
            <strong>CryptoSentinel</strong>
            <small>Judge Dashboard</small>
          </div>
        </div>
        <nav>
          {tabs.map((item) => (
            <button key={item.id} className={tab === item.id ? 'active' : ''} onClick={() => setTab(item.id)}>
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1>{tabs.find((item) => item.id === tab)?.label}</h1>
            <p>Unified desktop control surface for Spot ranking, agent state, health and safety controls.</p>
          </div>
          <div className="session-panel">
            <input
              aria-label="Backend URL"
              value={session.baseUrl}
              onChange={(event) => setSession((current) => ({ ...current, baseUrl: event.target.value }))}
              onBlur={() => setSession((current) => ({ ...current, baseUrl: normalizeBackendBaseUrl(current.baseUrl) }))}
            />
            <input
              aria-label="Read token"
              type="password"
              placeholder="Read token"
              value={session.readToken}
              onChange={(event) => setSession((current) => ({ ...current, readToken: event.target.value }))}
            />
            <input
              aria-label="Admin token"
              type="password"
              placeholder="Admin token"
              value={session.adminToken}
              onChange={(event) => setSession((current) => ({ ...current, adminToken: event.target.value }))}
            />
            <button onClick={() => void refreshCore(true)}>Refresh</button>
          </div>
        </header>

        {notice && (
          <button className="notice" onClick={() => setNotice('')}>
            {notice}
          </button>
        )}

        {tab === 'overview' && (
          <div className="grid overview-grid">
            <GlobalPanel global={global} equity={equity} />
            <SpotPanel spot={spot} session={session} />
            <PerpPanel perp={perp} session={session} />
            <HealthPanel live={live} ready={ready} heartbeat={heartbeat} execution={execution} coverage={coverage} />
            <KillSwitchPanel agent={agent} onSet={(state) => void updateKillSwitch(state)} canAdmin={canAdmin} />
          </div>
        )}
        {tab === 'spot' && <SpotPanel spot={spot} session={session} expanded />}
        {tab === 'perp' && <PerpPanel perp={perp} session={session} expanded />}
        {tab === 'global' && <GlobalPanel global={global} equity={equity} expanded />}
        {tab === 'analytics' && (
          <AnalyticsPanel
            equity={equity}
            equityRange={equityRange}
            onEquityRange={setEquityRange}
            decisions={decisions}
            decisionsOffset={decisionsOffset}
            onDecisionsPage={(offset) => void loadDecisionsPage(offset)}
            assetBreakdown={assetBreakdown}
            operationalStats={operationalStats}
            onTradeDetail={(tradeId) => fetchTradeDetail(session, tradeId)}
          />
        )}
        {tab === 'health' && (
          <HealthPanel live={live} ready={ready} heartbeat={heartbeat} execution={execution} coverage={coverage} expanded />
        )}
        {tab === 'wallet' && (
          <WalletPanel
            wallets={wallets}
            spot={spot}
            canAdmin={canAdmin}
            onSpotProvider={(provider) => void updateSpotProvider(provider)}
            onPerpProvider={(provider) => void updatePerpProvider(provider)}
            onRpcEndpoint={(index) => void updateRpcEndpoint(index)}
            onNetwork={(network) => void updateExecutionNetwork(network)}
            walletDraft={walletDraft}
            onWalletDraft={setWalletDraft}
            onWallet={(address) => void updateExecutionWallet(address)}
            onAddWallet={() => void submitWalletAddress()}
            onSend={(payload) => sendToken(session, payload)}
          />
        )}
        {tab === 'support' && (
          <SupportPanel
            tickets={supportTickets}
            detail={supportDetail}
            notifications={supportNotifications}
            reply={supportReply}
            onReply={setSupportReply}
            canAdmin={canAdmin}
            archived={supportArchived}
            onArchiveView={(archived) => void setSupportArchiveView(archived)}
            onRefresh={() => void refreshSupport()}
            onOpen={(ticketId) => void openSupportTicket(ticketId)}
            onSend={() => void submitSupportReply()}
            onStatus={(status) => void updateSupportStatus(status)}
          />
        )}
        {tab === 'logs' && <LogsPanel logs={logs} onRefresh={() => void refreshLogs()} canAdmin={canAdmin} />}
        {tab === 'settings' && (
          <div className="grid">
            <SettingsPanel
              settings={settings}
              draft={settingsDraft}
              setDraft={setSettingsDraft}
              onLoad={() => void refreshSettings()}
              onSave={() => void submitSettings()}
            />
            <NotificationPrefsPanel
              notifPrefs={notifPrefs}
              canAdmin={canAdmin}
              onLoad={() => void refreshNotifPrefs()}
              onToggle={(key) => void toggleNotifPref(key)}
            />
            <Panel title="Liquidità · Versamento / Prelievo" className="wide" action={<button onClick={() => void refreshEquityHistory()} disabled={!canRead}>Storico</button>}>
              <p className="hint">Aggiunge (o toglie, con valore negativo) capitale come un deposito. Alza l'equity senza contare come PnL. Es: 200 = +200$, -50 = −50$.</p>
              <div className="equity-adjust-row">
                <input
                  type="number"
                  inputMode="decimal"
                  value={equityInput}
                  onChange={(e) => setEquityInput(e.target.value)}
                  placeholder="es. 200 oppure -50"
                />
                <button onClick={() => void submitAdjustEquity()} disabled={!canAdmin || equityInput.trim() === '' || Number(equityInput) === 0 || !Number.isFinite(Number(equityInput))}>Applica</button>
              </div>
              {!canAdmin && <p className="hint">Admin token required.</p>}
              {equityHistory.length > 0 && (
                <table className="mini-table">
                  <thead><tr><th>Data</th><th>Importo</th><th>Saldo dopo</th><th>Nota</th></tr></thead>
                  <tbody>
                    {equityHistory.map((a) => (
                      <tr key={a.id}>
                        <td>{shortDate(a.created_at)}</td>
                        <td className={Number(a.amount) >= 0 ? 'ok-text' : 'error-text'}>{Number(a.amount) >= 0 ? '+' : ''}{money(a.amount)}</td>
                        <td className="num">{money(a.balance_after)}</td>
                        <td>{a.note ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
            <Panel title="Modalità sviluppatore" className="wide">
              <p className="hint">Azzera tutto il database: trade, decisioni, posizioni, PnL, portfolio e grafici. Impostazioni e watchlist restano. Prima di azzerare puoi salvare un backup con un nome.</p>
              <button className="danger" onClick={() => void submitResetDb()} disabled={!canAdmin}>🗑 Resetta database</button>
              {!canAdmin && <p className="hint">Admin token required.</p>}
            </Panel>
          </div>
        )}
        {tab === 'onboarding' && (
          <OnboardingPanel checks={checks} onValidate={() => void runOnboarding()} canAdmin={canAdmin} />
        )}
        {tab === 'markets' && (
          <MarketsPanel markets={markets} onRefresh={() => void refreshMarkets()} canRead={canRead} />
        )}
        {tab === 'export' && <ExportPanel payload={exportPayload} />}
      </main>
    </div>
  );
}

function Panel({
  title,
  children,
  action,
  className = '',
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-head">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

const RISK_GUARDRAIL_COPY: Record<string, { title: string; detail: string }> = {
  drawdown_cap_guard: {
    title: 'Trading blocked: drawdown cap',
    detail: 'Drawdown is above the configured cap. New Spot and Perp entries are suspended.',
  },
  daily_loss_limit_guard: {
    title: 'Trading blocked: daily loss limit',
    detail: 'Daily loss reached the configured limit. New entries are suspended until the UTC reset.',
  },
  portfolio_floor_guard: {
    title: 'Trading blocked: portfolio floor',
    detail: 'Portfolio equity is at the safety floor. New entries are suspended.',
  },
};

function RiskGuardrailBanner({ guardrail }: { guardrail: GlobalView['risk_guardrail'] }) {
  if (!guardrail?.blocked) return null;
  const copy = guardrail.reason ? RISK_GUARDRAIL_COPY[guardrail.reason] : undefined;
  return (
    <div className="guardrail-banner">
      <div>
        <strong>{copy?.title ?? guardrail.title}</strong>
        <p>{copy?.detail ?? guardrail.detail}</p>
      </div>
      <div className="guardrail-values">
        <span>{guardrail.reason?.replace(/_/g, ' ') ?? 'blocked'}</span>
        <span>DD {guardrail.drawdown_pct}% / cap {Math.abs(guardrail.drawdown_cap_pct).toFixed(2)}%</span>
      </div>
    </div>
  );
}

function GlobalPanel({ global, equity, expanded = false }: { global: LoadState<GlobalView>; equity: LoadState<EquityCurveResponse>; expanded?: boolean }) {
  const data = global.data;
  return (
    <Panel title="Global Agent" className={expanded ? 'wide' : ''}>
      <StateBlock state={global} empty="Waiting for global agent data" />
      {data && (
        <>
          <RiskGuardrailBanner guardrail={data.risk_guardrail} />
          <div className="metric-grid">
            <Metric label="Equity" value={money(data.total_equity_usd)} />
            <Metric label="PnL tot." value={money(data.pnl_total_usd)} tone={Number(data.pnl_total_usd) >= 0 ? 'good' : 'bad'} />
            <Metric label="PnL realizzato" value={money(data.realized_pnl_usd)} tone={Number(data.realized_pnl_usd) >= 0 ? 'good' : 'bad'} />
            <Metric label="PnL aperto" value={money(data.unrealized_pnl_usd)} tone={Number(data.unrealized_pnl_usd) >= 0 ? 'good' : 'bad'} />
            <Metric label="Daily" value={money(data.daily_pnl_usd)} />
            <Metric label="PnL % Day" value={`${data.daily_pnl_net_pct >= 0 ? '+' : ''}${data.daily_pnl_net_pct.toFixed(2)}%`} tone={data.daily_pnl_net_pct >= 0 ? 'good' : 'bad'} />
            <Metric label="PnL % Global" value={`${data.pnl_total_net_pct >= 0 ? '+' : ''}${data.pnl_total_net_pct.toFixed(2)}%`} tone={data.pnl_total_net_pct >= 0 ? 'good' : 'bad'} />
            <Metric label="Trades" value={String(data.trades_today)} />
            <Metric label="Drawdown" value={`${data.drawdown_pct}%`} tone={Number(data.drawdown_pct) >= 10 ? 'bad' : 'warn'} />
            <Metric label="Exposure" value={`${data.exposure_pct}%`} />
            <Metric label="Exposure Spot" value={money(data.spot_exposure_usd ?? '0')} />
            <Metric label="Exposure Perp" value={money(data.perp_exposure_usd ?? '0')} />
            <Metric label="Fee pagate" value={money(data.total_fees_usd ?? '0')} tone="warn" />
            {expanded && (
              <Metric
                label="Sharpe"
                value={data.sharpe_status === 'ready' && data.sharpe_ratio ? data.sharpe_ratio : 'insufficient data'}
              />
            )}
          </div>
          {(equity.data?.items.length ?? 0) < 2 ? (
            <Empty title="No PnL history" detail="Global tracking is ready and waiting for confirmed activity." />
          ) : (
            <EquityChart equity={equity.data} />
          )}
        </>
      )}
    </Panel>
  );
}

function SpotPanel({ spot, session, expanded = false }: { spot: LoadState<SpotView>; session: DashboardSession; expanded?: boolean }) {
  const data = spot.data;
  const [openTrade, setOpenTrade] = useState<string | null>(null);
  return (
    <Panel title="Spot Ranking View" className={expanded ? 'wide' : ''}>
      <StateBlock state={spot} empty="No Spot data loaded" />
      {data && (
        <>
          <div className="metric-grid">
            <Metric label="Realized" value={money(data.realized_pnl_usd)} />
            <Metric label="Unrealized" value={money(data.unrealized_pnl_usd)} />
            <Metric label="Win rate" value={`${data.win_rate_pct.toFixed(2)}%`} />
            <Metric label="Trade Tot" value={String(data.trade_count)} />
            <Metric label="Trade Day" value={String(data.trade_count_today ?? 0)} />
            <Metric label="Bot Day" value={String(data.bot_active_days ?? 0)} />
          </div>
          {data.open_positions.length === 0 ? (
            <Empty title="No open Spot positions" detail="The agent has no active Spot exposure." />
          ) : (
            <>
              <p className="hint">Clicca una posizione per il dettaglio.</p>
              <Table
                columns={['Asset', 'Size', 'Entry', 'Price Now', 'Invested', 'Value', 'PnL $', 'PnL %', 'Status']}
                onRowClick={(i) => {
                  const tid = data.open_positions[i].open_trade_id;
                  if (tid) setOpenTrade((cur) => (cur === tid ? null : tid));
                }}
                rows={data.open_positions.map((item) => {
                  const invested = Number(item.entry_price) * Number(item.size);
                  const value = invested + Number(item.pnl_unrealized);
                  const pnl = Number(item.pnl_unrealized);
                  const pct = item.pnl_pct ?? '+0.00';
                  return [
                    item.asset,
                    item.size,
                    fmtPrice(item.entry_price),
                    fmtPrice(item.current_price),
                    money(String(invested)),
                    <span className={value >= invested ? 'ok-text' : 'error-text'}>{money(String(value))}</span>,
                    <span className={pnl >= 0 ? 'ok-text' : 'error-text'}>{money(item.pnl_unrealized)}</span>,
                    <span className={pnl >= 0 ? 'ok-text' : 'error-text'}>{pct}%</span>,
                    item.status,
                  ];
                })}
              />
              {openTrade && <TradeDetailInline tradeId={openTrade} session={session} />}
            </>
          )}
          {expanded && (
            <div className="history-section">
              <div className="section-head">Trade History</div>
              <TradeHistoryTable trades={data.history} market="spot" session={session} />
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

function PerpPanel({ perp, session, expanded = false }: { perp: LoadState<PerpView>; session: DashboardSession; expanded?: boolean }) {
  const data = perp.data;
  const [openTrade, setOpenTrade] = useState<string | null>(null);
  return (
    <Panel title="Perp Futures View" className={expanded ? 'wide' : ''}>
      <StateBlock state={perp} empty="No Perp data loaded" />
      {data && (
        <>
          <div className="metric-grid">
            <Metric label="Realized" value={money(data.realized_pnl_usd)} />
            <Metric label="Unrealized" value={money(data.unrealized_pnl_usd)} />
            <Metric label="Win rate" value={`${data.win_rate_pct.toFixed(2)}%`} />
            <Metric label="Trade Tot" value={String(data.trade_count)} />
            <Metric label="Trade Day" value={String(data.trade_count_today ?? 0)} />
            <Metric label="Bot Day" value={String(data.bot_active_days ?? 0)} />
          </div>
          {data.open_positions.length === 0 ? (
            <Empty title="No open Perp positions" detail="The agent has no active Perp exposure." />
          ) : (
            <>
              <p className="hint">Clicca una posizione per il dettaglio.</p>
              <Table
                columns={['Asset', 'Side', 'Leverage', 'Entry', 'Now', 'Margine', 'Nozionale', 'Value', 'PnL', '%', 'Status']}
                onRowClick={(i) => {
                  const tid = data.open_positions[i].open_trade_id;
                  if (tid) setOpenTrade((cur) => (cur === tid ? null : tid));
                }}
                rows={data.open_positions.map((item) => {
                  const notional = Number(item.entry_price) * Number(item.size);
                  const margin = item.leverage ? notional / Number(item.leverage) : notional;
                  const value = margin + Number(item.pnl_unrealized);
                  const pnl = Number(item.pnl_unrealized);
                  const pct = item.pnl_pct ?? '0.00';
                  return [
                    item.asset,
                    <span className={item.side === 'long' ? 'ok-text' : 'error-text'}>{item.side}</span>,
                    item.leverage ? `${item.leverage}x` : '-',
                    fmtPrice(item.entry_price),
                    fmtPrice(item.current_price),
                    money(String(margin)),
                    money(String(notional)),
                    <span className={value >= margin ? 'ok-text' : 'error-text'}>{money(String(value))}</span>,
                    <span className={pnl >= 0 ? 'ok-text' : 'error-text'}>{money(item.pnl_unrealized)}</span>,
                    <span className={pnl >= 0 ? 'ok-text' : 'error-text'}>{pct}%</span>,
                    item.status,
                  ];
                })}
              />
              {openTrade && <TradeDetailInline tradeId={openTrade} session={session} />}
            </>
          )}
          {expanded && (
            <div className="history-section">
              <div className="section-head">Trade History</div>
              <TradeHistoryTable trades={data.history} market="perp" session={session} />
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

const DECISIONS_PAGE_SIZE = 200;

function AnalyticsPanel({
  equity,
  equityRange,
  onEquityRange,
  decisions,
  decisionsOffset,
  onDecisionsPage,
  assetBreakdown,
  operationalStats,
  onTradeDetail,
}: {
  equity: LoadState<EquityCurveResponse>;
  equityRange: EquityRange;
  onEquityRange: (r: EquityRange) => void;
  decisions: LoadState<AgentDecisionResponse>;
  decisionsOffset: number;
  onDecisionsPage: (offset: number) => void;
  assetBreakdown: LoadState<AssetBreakdownResponse>;
  operationalStats: LoadState<OperationalStats>;
  onTradeDetail: (tradeId: string) => Promise<TradeDetail>;
}) {
  const [detail, setDetail] = useState<LoadState<TradeDetail>>(emptyState());
  const [filterSearch, setFilterSearch] = useState('');
  const [filterAsset, setFilterAsset] = useState('');
  const [filterMarket, setFilterMarket] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterExecution, setFilterExecution] = useState('');

  async function openDetail(tradeId?: string | null) {
    if (!tradeId) return;
    await loadDetail(setDetail, () => onTradeDetail(tradeId));
  }

  const allItems = decisions.data?.items ?? [];

  const uniqueAssets = useMemo(() => [...new Set(allItems.map(i => i.asset ?? '').filter(Boolean))].sort(), [allItems]);
  const uniqueMarkets = useMemo(() => [...new Set(allItems.map(i => i.market))].sort(), [allItems]);
  const uniqueActions = useMemo(() => [...new Set(allItems.map(i => i.action))].sort(), [allItems]);
  const uniqueExecutions = useMemo(() => [...new Set(allItems.map(i => i.execution_result ?? '').filter(Boolean))].sort(), [allItems]);

  const filtered = useMemo(() => {
    const q = filterSearch.toLowerCase();
    return allItems.filter(item => {
      if (filterAsset && (item.asset ?? '') !== filterAsset) return false;
      if (filterMarket && item.market !== filterMarket) return false;
      if (filterAction && item.action !== filterAction) return false;
      if (filterExecution && (item.execution_result ?? '') !== filterExecution) return false;
      if (q) {
        return (
          (item.asset ?? '').toLowerCase().includes(q) ||
          item.market.toLowerCase().includes(q) ||
          item.action.toLowerCase().includes(q) ||
          (item.execution_result ?? '').toLowerCase().includes(q) ||
          (item.reasoning ?? '').toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [allItems, filterSearch, filterAsset, filterMarket, filterAction, filterExecution]);

  const hasActiveFilter = filterSearch || filterAsset || filterMarket || filterAction || filterExecution;

  return (
    <div>
    <div className="grid overview-grid">
      <Panel title="Equity Curve" className="wide">
        <StateBlock state={equity} empty="No equity curve data" />
        {equity.data && equity.data.items.length > 0 ? (
          <>
            <EquityChart equity={equity.data} range={equityRange} onRange={onEquityRange} />
            <Table
              columns={['Time', 'Equity', 'PnL', 'ROI', 'Drawdown']}
              rows={equity.data.items.slice(-12).map((item) => [
                shortDate(item.timestamp_utc),
                money(item.equity_usd),
                item.pnl_usd,
                `${item.pnl_pct}%`,
                `${item.drawdown_pct}%`,
              ])}
            />
          </>
        ) : equity.data ? (
          <Empty title="No equity snapshots" detail="New clean dry-run snapshots will appear here." />
        ) : null}
      </Panel>

      <Panel title="Operational Stats">
        <StateBlock state={operationalStats} empty="No operational stats loaded" />
        {operationalStats.data && (
          <div className="metric-grid two">
            <Metric label="Uptime" value={`${operationalStats.data.uptime_pct}%`} />
            <Metric label="Degraded" value={String(operationalStats.data.degraded_count)} />
            <Metric label="Kill switch" value={operationalStats.data.last_kill_switch ?? 'none'} />
          </div>
        )}
      </Panel>

      <Panel title="Asset Breakdown" className="wide">
        <StateBlock state={assetBreakdown} empty="No asset breakdown data" />
        {assetBreakdown.data && assetBreakdown.data.items.length > 0 ? (
          <Table
            columns={['Asset', 'Trades', 'Win rate', 'PnL', 'ROI', 'Allocation']}
            rows={assetBreakdown.data.items.map((item) => [
              item.asset,
              String(item.trade_count),
              `${item.win_rate_pct}%`,
              item.pnl_usd,
              `${item.pnl_pct}%`,
              `${item.allocation_pct}%`,
            ])}
          />
        ) : assetBreakdown.data ? (
          <Empty title="No asset activity" detail="Breakdown starts after the first non-archived trade or position." />
        ) : null}
      </Panel>
    </div>

    <Panel
      title="Decision Log"
      className="wide"
      action={
        <div className="pager-controls">
          <button
            className="pager-btn"
            disabled={decisionsOffset === 0 || decisions.loading}
            onClick={() => onDecisionsPage(Math.max(0, decisionsOffset - DECISIONS_PAGE_SIZE))}
          >‹ Prec</button>
          <span className="pager-info">
            {decisions.loading ? '…' : `${decisionsOffset + 1}–${decisionsOffset + (decisions.data?.items.length ?? 0)}`}
          </span>
          <button
            className="pager-btn"
            disabled={(decisions.data?.items.length ?? 0) < DECISIONS_PAGE_SIZE || decisions.loading}
            onClick={() => onDecisionsPage(decisionsOffset + DECISIONS_PAGE_SIZE)}
          >Succ ›</button>
        </div>
      }
    >
        <StateBlock state={decisions} empty="No agent decisions loaded" />
        {decisions.data && (
          <>
            <div className="decision-filters">
              <input
                type="search"
                placeholder="Cerca…"
                value={filterSearch}
                onChange={e => setFilterSearch(e.target.value)}
              />
              <select value={filterAsset} onChange={e => setFilterAsset(e.target.value)}>
                <option value="">Tutti gli asset</option>
                {uniqueAssets.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
              <select value={filterMarket} onChange={e => setFilterMarket(e.target.value)}>
                <option value="">Tutti i mercati</option>
                {uniqueMarkets.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <select value={filterAction} onChange={e => setFilterAction(e.target.value)}>
                <option value="">Tutte le azioni</option>
                {uniqueActions.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
              <select value={filterExecution} onChange={e => setFilterExecution(e.target.value)}>
                <option value="">Tutti i risultati</option>
                {uniqueExecutions.map(e => <option key={e} value={e}>{e}</option>)}
              </select>
              {hasActiveFilter && (
                <button onClick={() => { setFilterSearch(''); setFilterAsset(''); setFilterMarket(''); setFilterAction(''); setFilterExecution(''); }}>
                  Reset
                </button>
              )}
              <span className="muted">{filtered.length} / {allItems.length}</span>
            </div>
            {filtered.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Asset</th>
                      <th>Market</th>
                      <th>Quality</th>
                      <th>Action</th>
                      <th>Execution</th>
                      <th>Reasoning</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((item) => (
                      <tr key={item.decision_id} onClick={() => void openDetail(item.trade_id)}>
                        <td>{shortDate(item.timestamp_utc)}</td>
                        <td>{item.asset ?? '--'}</td>
                        <td>{item.market}</td>
                        <td>{item.signal_quality}</td>
                        <td>{item.action}</td>
                        <td>{item.execution_result ?? '--'}</td>
                        <td className="reasoning-cell"><ReasoningCell reasoning={item.reasoning} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="Nessun risultato" detail={hasActiveFilter ? 'Nessuna decisione corrisponde ai filtri selezionati.' : 'Agent reasoning will appear after the first evaluation.'} />
            )}
          </>
        )}
        {detail.data && <TradeDetailCard detail={detail.data} />}
        {detail.error && <p className="error-text">{detail.error}</p>}
      </Panel>
    </div>
  );
}

function TradeCandleChart({ chart }: { chart: TradeChart }) {
  const candles = chart.candles ?? [];
  const postClose = chart.post_close_candles ?? [];
  const allCandles = [...candles, ...postClose];
  if (allCandles.length < 2) {
    return <p className="muted">Grafico non disponibile per questo trade.</p>;
  }
  const W = Math.max(520, allCandles.length * 8 + 64);
  const H = 230;
  const padL = 8;
  const padR = 48;
  const padT = 10;
  const padB = 20;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const entry = Number(chart.entry_price);
  const exit = Number(chart.exit_price);
  const sl = chart.stop_loss != null ? Number(chart.stop_loss) : null;
  const tp1 = chart.take_profit_1 != null ? Number(chart.take_profit_1) : null;
  const tp2 = chart.take_profit_2 != null ? Number(chart.take_profit_2) : null;

  const levels = [entry, exit, sl, tp1, tp2].filter((v): v is number => v != null && !Number.isNaN(v));
  let hi = Math.max(...allCandles.map((c) => c.h), ...levels);
  let lo = Math.min(...allCandles.map((c) => c.l), ...levels);
  if (hi === lo) { hi += 1; lo -= 1; }
  const range = hi - lo;
  const y = (price: number) => padT + (1 - (price - lo) / range) * plotH;
  const colW = plotW / allCandles.length;
  const cx = (i: number) => padL + colW * (i + 0.5);

  const ts = (s: string) => new Date(s).getTime();
  const nearest = (target: number, pool: typeof allCandles) => {
    let best = 0;
    let bestD = Infinity;
    pool.forEach((c, i) => { const d = Math.abs(ts(c.t) - target); if (d < bestD) { bestD = d; best = i; } });
    return best;
  };
  const atOrBefore = (target: number, pool: typeof allCandles) => {
    let best = -1;
    pool.forEach((c, i) => { if (ts(c.t) <= target) best = i; });
    return best >= 0 ? best : nearest(target, pool);
  };
  const entryIdx = nearest(ts(chart.opened_at), allCandles);
  const exitIdx = atOrBefore(ts(chart.closed_at), allCandles);
  const stopRefIdx = chart.stop_reference?.t ? nearest(ts(chart.stop_reference.t), allCandles) : null;
  const stopRefPrice = sl ?? (chart.stop_reference?.price != null ? Number(chart.stop_reference.price) : null);
  const exitGood = exit >= entry;

  const levelLine = (price: number | null, color: string, dash: string) =>
    price == null || Number.isNaN(price) ? null : (
      <line x1={padL} x2={W - padR} y1={y(price)} y2={y(price)} stroke={color} strokeWidth="1" strokeDasharray={dash} opacity="0.7" />
    );

  const stopRefLine = (idx: number) => {
    const candle = allCandles[idx];
    if (!candle) return null;
    const gap = 3;
    const x = cx(idx);
    const topEnd = Math.max(padT, y(candle.h) - gap);
    const bottomStart = Math.min(padT + plotH, y(candle.l) + gap);
    return (
      <>
        {topEnd > padT && (
          <line x1={x} x2={x} y1={padT} y2={topEnd} stroke="#a855f7" strokeWidth="1" strokeDasharray="2 2" opacity="0.9" />
        )}
        {bottomStart < padT + plotH && (
          <line x1={x} x2={x} y1={bottomStart} y2={padT + plotH} stroke="#a855f7" strokeWidth="1" strokeDasharray="2 2" opacity="0.9" />
        )}
      </>
    );
  };

  const axisPrice = (v: number) => {
    const a = Math.abs(v);
    if (a >= 1000) return v.toFixed(0);
    if (a >= 1) return v.toFixed(2);
    if (a >= 0.01) return v.toFixed(4);
    return v.toExponential(1);
  };
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => lo + range * f);
  const fmtClock = (s: string) => new Date(s).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  const last = allCandles.length - 1;
  const xTickIdx = last <= 3
    ? allCandles.map((_, i) => i)
    : [0, Math.floor(last / 3), Math.floor((2 * last) / 3), last];

  // Linea verticale subito dopo la candela di chiusura.
  const closeLineX = postClose.length > 0 ? padL + colW * (exitIdx + 1) : null;

  return (
    <div style={{ overflowX: 'auto', paddingBottom: 4 }}>
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: `${W}px`, minWidth: '100%', height: 'auto' }}>
      {/* griglia + prezzo (Y) a destra */}
      {yTicks.map((p, i) => (
        <g key={`y${i}`}>
          <line x1={padL} x2={W - padR} y1={y(p)} y2={y(p)} stroke="#ffffff" strokeOpacity="0.05" strokeWidth="1" />
          <text x={W - padR + 4} y={y(p) + 3} fontSize="8" fill="#6b7280">{axisPrice(p)}</text>
        </g>
      ))}
      {/* sfondo post-close */}
      {closeLineX != null && (
        <rect x={closeLineX} y={padT} width={W - padR - closeLineX} height={plotH} fill="#111827" opacity="0.45" />
      )}
      {/* candele */}
      {allCandles.map((c, i) => {
        const isPost = i >= candles.length;
        const isPreEntry = i < entryIdx;
        const up = c.c >= c.o;
        const color = isPost ? (up ? '#166534' : '#7f1d1d') : (up ? '#22c55e' : '#ef4444');
        const bodyTop = y(Math.max(c.o, c.c));
        const bodyBot = y(Math.min(c.o, c.c));
        const bw = Math.max(1, colW * 0.6);
        return (
          <g key={i} opacity={isPost || isPreEntry ? 0.55 : 1}>
            <line x1={cx(i)} x2={cx(i)} y1={y(c.h)} y2={y(c.l)} stroke={color} strokeWidth="1" />
            <rect x={cx(i) - bw / 2} y={bodyTop} width={bw} height={Math.max(1, bodyBot - bodyTop)} fill={color} />
          </g>
        );
      })}
      {/* linea verticale tratteggiata di chiusura */}
      {closeLineX != null && (
        <line x1={closeLineX} x2={closeLineX} y1={padT} y2={padT + plotH} stroke="#6b7280" strokeWidth="1" strokeDasharray="3 2" opacity="0.8" />
      )}
      {stopRefIdx != null && (
        <>
          {stopRefLine(stopRefIdx)}
          <text x={Math.min(W - padR - 4, cx(stopRefIdx) + 4)} y={padT + 8} fontSize="8" fill="#c084fc">SL ref</text>
          {stopRefPrice != null && !Number.isNaN(stopRefPrice) && (
            <circle cx={cx(stopRefIdx)} cy={y(stopRefPrice)} r="3" fill="#a855f7" stroke="#0b0e11" strokeWidth="1" />
          )}
        </>
      )}
      {levelLine(sl, '#ef4444', '5 4')}
      {levelLine(tp1, '#22c55e', '5 4')}
      {levelLine(tp2, '#16a34a', '2 4')}
      {levelLine(entry, '#9ca3af', '1 0')}
      <circle cx={cx(entryIdx)} cy={y(entry)} r="4" fill="#e5e7eb" stroke="#0b0e11" strokeWidth="1" />
      <circle cx={cx(exitIdx)} cy={y(exit)} r="4" fill={exitGood ? '#22c55e' : '#ef4444'} stroke="#0b0e11" strokeWidth="1" />
      {/* orario (X) in basso */}
      {xTickIdx.map((idx) => (
        <text
          key={`x${idx}`}
          x={cx(idx)}
          y={H - 6}
          fontSize="8"
          fill="#6b7280"
          textAnchor={idx === 0 ? 'start' : idx === last ? 'end' : 'middle'}
        >
          {fmtClock(allCandles[idx].t)}
        </text>
      ))}
    </svg>
    </div>
  );
}

function TradeDetailInline({ tradeId, session }: { tradeId: string; session: DashboardSession }) {
  const [state, setState] = useState<LoadState<TradeDetail>>(emptyState());
  useEffect(() => {
    let active = true;
    void loadDetail((value) => { if (active) setState(value); }, () => fetchTradeDetail(session, tradeId));
    return () => { active = false; };
  }, [tradeId, session]);

  const detail = state.data;
  return (
    <div className="trade-inline">
      {state.loading && <span className="muted">Caricamento dettaglio…</span>}
      {state.error && <span className="error-text">{state.error}</span>}
      {detail && (
        <>
          <div className="metric-grid">
            <Metric label="Direction" value={detail.direction} />
            <Metric label={detail.is_smart_sl ? 'Entry originale' : 'Entry'} value={fmtPrice(detail.original_entry_price ?? detail.entry_price)} />
            {detail.current_position_entry_price && detail.current_position_entry_price !== (detail.original_entry_price ?? detail.entry_price) && (
              <Metric label="Entry corrente" value={fmtPrice(detail.current_position_entry_price)} />
            )}
            <Metric label="Now/Exit" value={fmtPrice(detail.current_or_exit_price)} />
            <Metric label="PnL" value={`${detail.pnl_usd} / ${detail.pnl_pct}%`} tone={Number(detail.pnl_usd) >= 0 ? 'good' : 'bad'} />
            <Metric label="Size" value={detail.size} />
            <Metric label="Leverage" value={detail.leverage ? `${detail.leverage}x` : '—'} />
            {detail.margin_usd != null && <Metric label="Margine" value={money(detail.margin_usd)} />}
            <Metric label="Exposure" value={money(detail.exposure_usd)} />
            <Metric label="Motivo" value={detail.close_reason ? (CLOSE_REASON_LABELS[detail.close_reason] ?? detail.close_reason) : '—'} />
          </div>
          <div className="metric-grid">
            <Metric label="Stop loss" value={detail.stop_loss ? fmtPrice(detail.stop_loss) : '—'} />
            {detail.market === 'perp' && (
              <Metric
                label={detail.stop_reference_field === 'high' ? 'Max candela ref SL' : 'Min candela ref SL'}
                value={detail.stop_reference_price ? fmtPrice(detail.stop_reference_price) : '---'}
              />
            )}
            {detail.market === 'perp' && <Metric label="Liquidation" value={detail.liquidation_price ? fmtPrice(detail.liquidation_price) : '---'} />}
            <Metric label="Breakeven" value={detail.breakeven_price ? fmtPrice(detail.breakeven_price) : '---'} />
            <Metric label="Take profit 1" value={detail.take_profit_1 ? fmtPrice(detail.take_profit_1) : '—'} />
            <Metric label="Take profit 2" value={detail.take_profit_2 ? fmtPrice(detail.take_profit_2) : '—'} />
            <Metric label="Trailing" value={detail.trailing_stop ? fmtPrice(detail.trailing_stop) : 'Non attivo'} />
          </div>
          <div className="trade-timeline muted">
            <span>Open: {detail.opened_at ? shortDate(detail.opened_at) : '—'}</span>
            <span>Close: {detail.closed_at ? shortDate(detail.closed_at) : '—'}</span>
          </div>
          {detail.chart ? (
            <div className="trade-chart">
              <div className="section-head">Grafico del trade <span className="muted">{detail.chart.interval}</span></div>
              <TradeCandleChart chart={detail.chart} />
              <div className="chart-legend muted">
                ⚪ Entry &nbsp; ● Exit &nbsp; <span style={{ color: '#ef4444' }}>- - SL</span> &nbsp; <span style={{ color: '#22c55e' }}>- - TP</span>
              </div>
            </div>
          ) : (
            <p className="muted">Grafico non disponibile per questo trade (chiuso prima dell'introduzione della funzione).</p>
          )}
        </>
      )}
    </div>
  );
}

function TradeDetailCard({ detail }: { detail: TradeDetail }) {
  return (
    <div className="trade-detail">
      <div className="subhead">
        <h3>{detail.asset} {detail.market}</h3>
        <span>{detail.is_simulated ? 'simulated' : 'live'}</span>
      </div>
      <div className="metric-grid">
        <Metric label="Direction" value={detail.direction} />
        <Metric label={detail.is_smart_sl ? 'Entry originale' : 'Entry'} value={fmtPrice(detail.original_entry_price ?? detail.entry_price)} />
        {detail.current_position_entry_price && detail.current_position_entry_price !== (detail.original_entry_price ?? detail.entry_price) && (
          <Metric label="Entry corrente" value={fmtPrice(detail.current_position_entry_price)} />
        )}
        <Metric label="Now/Exit" value={fmtPrice(detail.current_or_exit_price)} />
        <Metric label="PnL" value={`${detail.pnl_usd} / ${detail.pnl_pct}%`} tone={Number(detail.pnl_usd) >= 0 ? 'good' : 'bad'} />
        <Metric label="Exposure" value={money(detail.exposure_usd)} />
        <Metric label="Size" value={detail.size} />
      </div>
      <pre className="json-dump">{JSON.stringify(detail, null, 2)}</pre>
    </div>
  );
}

function HealthPanel({
  live,
  ready,
  heartbeat,
  execution,
  coverage,
  expanded = false,
}: {
  live: LoadState<HealthPayload>;
  ready: LoadState<HealthPayload>;
  heartbeat: LoadState<HealthPayload>;
  execution: LoadState<ExecutionStatus>;
  coverage: LoadState<DataCoverageResponse>;
  expanded?: boolean;
}) {
  const coverageItems = coverage.data?.items || [];
  const readyCount = coverageItems.filter((item) => item.status === 'ready').length;
  return (
    <Panel title="System Health" className={expanded ? 'wide' : ''}>
      <div className="status-list">
        <StatusRow label="Live" state={live} />
        <StatusRow label="Ready" state={ready} />
        <StatusRow label="Heartbeat" state={heartbeat} />
        <StatusRow label="Execution" state={execution} />
        <div className="status-row">
          <span>Data Coverage</span>
          <strong className={readyCount > 0 ? 'ok-text' : 'warn-text'}>
            {coverage.loading ? 'loading' : `${readyCount}/${coverageItems.length || 0} ready`}
          </strong>
        </div>
      </div>
      {expanded && (
        <>
          <DataCoveragePanel coverage={coverage} />
          <pre className="json-dump">
            {JSON.stringify({ live: live.data, ready: ready.data, heartbeat: heartbeat.data, execution: execution.data }, null, 2)}
          </pre>
        </>
      )}
    </Panel>
  );
}

function DataCoveragePanel({ coverage }: { coverage: LoadState<DataCoverageResponse> }) {
  const [marketFilter, setMarketFilter] = useState<'spot' | 'perp'>('spot');
  const [query, setQuery] = useState('');
  const rows = coverage.data?.items || [];
  const marketRows = rows.filter((item) => item.market === marketFilter);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredRows = normalizedQuery
    ? marketRows.filter((item) =>
        `${item.asset} ${item.symbol} ${item.status} ${item.source}`.toLowerCase().includes(normalizedQuery),
      )
    : marketRows;
  const spotCount = rows.filter((item) => item.market === 'spot').length;
  const perpCount = rows.filter((item) => item.market === 'perp').length;
  return (
    <div className="coverage-block">
      <div className="subhead">
        <h3>Data Coverage</h3>
        <span>{coverage.data ? `Generated ${shortDate(coverage.data.generated_at)}` : 'Cache snapshot'}</span>
      </div>
      <StateBlock state={{ ...coverage, data: rows }} empty="No coverage data loaded" />
      {rows.length > 0 && (
        <>
          <div className="coverage-toolbar">
            <div className="segmented" role="tablist" aria-label="Data coverage market">
              <button className={marketFilter === 'spot' ? 'selected' : ''} onClick={() => setMarketFilter('spot')}>
                Spot <span>{spotCount}</span>
              </button>
              <button className={marketFilter === 'perp' ? 'selected' : ''} onClick={() => setMarketFilter('perp')}>
                Perp <span>{perpCount}</span>
              </button>
            </div>
            <input
              aria-label="Search token"
              placeholder="Search token"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          {filteredRows.length === 0 ? (
            <Empty title="No matching assets" detail="Adjust the search or switch market." />
          ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Asset</th>
                <th>Market</th>
                <th>Candles</th>
                <th>Status</th>
                <th>First</th>
                <th>Last</th>
                <th>Updated</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((item) => (
                <CoverageRow key={`${item.market}-${item.asset}`} item={item} />
              ))}
            </tbody>
          </table>
        </div>
          )}
        </>
      )}
    </div>
  );
}

function CoverageRow({ item }: { item: DataCoverageItem }) {
  return (
    <tr>
      <td>{item.asset}</td>
      <td>{item.market}</td>
      <td>{item.available_candles}/{item.required_candles}</td>
      <td><span className={`coverage-status ${item.status}`}>{item.status}</span></td>
      <td>{item.first_candle_at ? shortDate(item.first_candle_at) : '--'}</td>
      <td>{item.last_candle_at ? shortDate(item.last_candle_at) : '--'}</td>
      <td>{formatAge(item.age_seconds)}</td>
      <td>{item.source}</td>
    </tr>
  );
}

function WalletPanel({
  wallets,
  spot,
  canAdmin,
  onSpotProvider,
  onPerpProvider,
  onRpcEndpoint,
  onNetwork,
  walletDraft,
  onWalletDraft,
  onWallet,
  onAddWallet,
  onSend,
}: {
  wallets: LoadState<ExecutionWalletsResponse>;
  spot: LoadState<SpotView>;
  canAdmin: boolean;
  onSpotProvider: (provider: string) => void;
  onPerpProvider: (provider: string) => void;
  onRpcEndpoint: (index: number) => void;
  onNetwork: (network: 'testnet' | 'mainnet') => void;
  walletDraft: string;
  onWalletDraft: (value: string) => void;
  onWallet: (address: string) => void;
  onAddWallet: () => void;
  onSend: (payload: { to_address: string; amount: string; token: string; wallet_password: string }) => Promise<{ status: string; tx_hash?: string; error?: string }>;
}) {
  const [expandedCoin, setExpandedCoin] = useState<string | null>(null);
  const [txSearch, setTxSearch] = useState('');
  const [txType, setTxType] = useState<'all' | 'buy' | 'sell'>('all');
  const [modal, setModal] = useState<{ mode: 'send' | 'receive'; asset: string } | null>(null);

  // Send form state
  const [sendTo, setSendTo] = useState('');
  const [sendAmount, setSendAmount] = useState('');
  const [sendPassword, setSendPassword] = useState('');
  const [sendState, setSendState] = useState<'idle' | 'sending' | 'success' | 'error'>('idle');
  const [sendResult, setSendResult] = useState<{ tx_hash?: string; error?: string } | null>(null);

  function openModal(mode: 'send' | 'receive', asset: string) {
    setModal({ mode, asset });
    setSendTo(''); setSendAmount(''); setSendPassword('');
    setSendState('idle'); setSendResult(null);
  }

  async function execSend() {
    if (!modal || !sendTo.trim() || !sendAmount.trim() || !sendPassword.trim()) return;
    setSendState('sending');
    try {
      const res = await onSend({ to_address: sendTo.trim(), amount: sendAmount.trim(), token: modal.asset, wallet_password: sendPassword });
      if (res.status === 'success') {
        setSendState('success'); setSendResult({ tx_hash: res.tx_hash });
      } else {
        setSendState('error'); setSendResult({ error: res.error ?? 'Errore sconosciuto' });
      }
    } catch (e) {
      setSendState('error'); setSendResult({ error: e instanceof Error ? e.message : 'Errore di rete' });
    }
  }

  const data = wallets.data;
  const spotData = spot.data;
  const activeWallet = data?.available_wallets?.find((w) => w.active) ?? data?.available_wallets?.[0];

  function toggleCoin(asset: string) {
    setExpandedCoin((prev) => (prev === asset ? null : asset));
    setTxSearch('');
    setTxType('all');
  }

  function coinColor(asset: string) {
    const palette = ['#7fa66a', '#6a9ab0', '#b07a6a', '#b0a06a', '#8a6ab0', '#6ab09a', '#a06a8a'];
    return palette[asset.charCodeAt(0) % palette.length];
  }

  function assetTrades(asset: string) {
    if (!spotData) return [];
    return spotData.history.filter(
      (t) =>
        t.asset === asset &&
        (txType === 'all' || t.side === txType) &&
        (txSearch === '' ||
          t.trade_id.toLowerCase().includes(txSearch.toLowerCase()) ||
          t.status.toLowerCase().includes(txSearch.toLowerCase())),
    );
  }

  return (
    <Panel title="Wallet" className="wide">
      <StateBlock state={wallets} empty="Nessun snapshot wallet caricato" />

      {/* ── HOLDINGS ─────────────────────────────────────────────── */}
      {data && (
        <div className="holdings-section">
          <div className="subhead">
            <h3>Portfolio Holdings</h3>
            <span>
              {spotData ? `${spotData.open_positions.length} posizioni aperte` : 'caricamento…'}
            </span>
          </div>

          {/* BNB card */}
          {activeWallet?.balance_bnb && (
            <div className={`coin-card${expandedCoin === 'BNB' ? ' expanded' : ''}`}>
              <button className="coin-header" onClick={() => toggleCoin('BNB')}>
                <span className="coin-avatar" style={{ background: '#f0b90b', color: '#10130f' }}>B</span>
                <div className="coin-meta">
                  <strong>BNB</strong>
                  <span>BNB Smart Chain · gas token</span>
                </div>
                <div className="coin-stat-group">
                  <strong>{parseFloat(activeWallet.balance_bnb).toFixed(4)} BNB</strong>
                  <span>{activeWallet.balance_status}</span>
                </div>
                <div className="coin-stat-group">
                  <strong className="muted">—</strong>
                  <span>PnL</span>
                </div>
                <div className="coin-stat-group">
                  <strong className="muted">—</strong>
                  <span>Entry / Now</span>
                </div>
                <div className="coin-actions" onClick={(e) => e.stopPropagation()}>
                  <button onClick={() => openModal('receive', 'BNB')}>↓ Ricevi</button>
                  <button onClick={() => openModal('send', 'BNB')}>↑ Invia</button>
                </div>
                <span className="coin-chevron">{expandedCoin === 'BNB' ? '▲' : '▼'}</span>
              </button>
              {expandedCoin === 'BNB' && (
                <div className="coin-detail">
                  <div className="wallet-detail-info">
                    <div><span>Indirizzo</span><code>{activeWallet.address}</code></div>
                    <div><span>Network</span><strong>{data.network} · Chain {data.chain_id}</strong></div>
                    <div><span>Bilancio</span><strong>{activeWallet.balance_bnb} BNB</strong></div>
                  </div>
                  <p className="hint" style={{ padding: '0 14px 14px' }}>Le transazioni BNB on-chain non sono tracciate in questo sistema.</p>
                </div>
              )}
            </div>
          )}

          {/* Spot position cards */}
          {spotData?.open_positions.map((pos) => {
            const pnl = parseFloat(pos.pnl_unrealized);
            const isPos = pnl >= 0;
            const entry = parseFloat(pos.entry_price);
            const current = parseFloat(pos.current_price);
            const size = parseFloat(pos.size);
            const invested = entry * size;
            const value = current * size;
            const isExp = expandedCoin === pos.asset;
            const trades = isExp ? assetTrades(pos.asset) : [];
            return (
              <div key={pos.position_id} className={`coin-card${isExp ? ' expanded' : ''}`}>
                <button className="coin-header" onClick={() => toggleCoin(pos.asset)}>
                  <span className="coin-avatar" style={{ background: coinColor(pos.asset) }}>
                    {pos.asset[0]}
                  </span>
                  <div className="coin-meta">
                    <strong>{pos.asset}/USDT</strong>
                    <span>Spot · {pos.status}</span>
                  </div>
                  <div className="coin-stat-group">
                    <strong>{size.toFixed(6)}</strong>
                    <span>Quantità</span>
                  </div>
                  <div className="coin-stat-group">
                    <strong>${invested.toLocaleString('en-US', { maximumFractionDigits: 2 })}</strong>
                    <span>Investito → ${value.toLocaleString('en-US', { maximumFractionDigits: 2 })}</span>
                  </div>
                  <div className="coin-stat-group">
                    <strong>${entry.toLocaleString()} → ${current.toLocaleString()}</strong>
                    <span>Entry → Now</span>
                  </div>
                  <div className={`coin-pnl-badge${isPos ? ' pos' : ' neg'}`}>
                    <strong>{isPos ? '+' : ''}{pnl.toFixed(2)} $</strong>
                    <span>{pos.pnl_pct ?? '—'}</span>
                  </div>
                  <div className="coin-actions" onClick={(e) => e.stopPropagation()}>
                    <button onClick={() => openModal('receive', pos.asset)}>↓ Ricevi</button>
                    <button onClick={() => openModal('send', pos.asset)}>↑ Invia</button>
                  </div>
                  <span className="coin-chevron">{isExp ? '▲' : '▼'}</span>
                </button>

                {isExp && (
                  <div className="coin-detail">
                    {/* position summary bar */}
                    <div className="wallet-detail-info">
                      <div><span>SL</span><strong>{pos.stop_loss ? `$${parseFloat(pos.stop_loss).toLocaleString()}` : '—'}</strong></div>
                      <div><span>TP1</span><strong>{pos.take_profit_1 ? `$${parseFloat(pos.take_profit_1).toLocaleString()}` : '—'}</strong></div>
                      <div><span>TP2</span><strong>{pos.take_profit_2 ? `$${parseFloat(pos.take_profit_2).toLocaleString()}` : '—'}</strong></div>
                      <div><span>Aperta il</span><strong>{new Date(pos.opened_at).toLocaleString('it-IT')}</strong></div>
                    </div>

                    {/* filter bar */}
                    <div className="tx-filter-bar">
                      <input
                        placeholder="Cerca per ID o stato…"
                        value={txSearch}
                        onChange={(e) => setTxSearch(e.target.value)}
                      />
                      <select value={txType} onChange={(e) => setTxType(e.target.value as 'all' | 'buy' | 'sell')}>
                        <option value="all">Tutti i tipi</option>
                        <option value="buy">Acquisto</option>
                        <option value="sell">Vendita / Chiusura</option>
                      </select>
                      {(txSearch || txType !== 'all') && (
                        <button onClick={() => { setTxSearch(''); setTxType('all'); }}>Reset</button>
                      )}
                      <span className="muted">{trades.length} transazioni</span>
                    </div>

                    {trades.length === 0 ? (
                      <p className="muted" style={{ padding: '0 14px 14px' }}>Nessuna transazione trovata per {pos.asset}.</p>
                    ) : (
                      <div className="table-wrap" style={{ margin: '0 14px 14px' }}>
                        <table>
                          <thead>
                            <tr>
                              <th>Data / Ora</th>
                              <th>Tipo</th>
                              <th>Quantità</th>
                              <th>Prezzo</th>
                              <th>Totale</th>
                              <th>PnL</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {trades.map((t) => {
                              const qty = parseFloat(t.amount ?? '0');
                              const px = parseFloat(t.price ?? '0');
                              const total = qty * px;
                              const tPnl = t.pnl_usd && t.pnl_usd !== '+0.00' ? parseFloat(t.pnl_usd) : null;
                              return (
                                <tr key={t.trade_id}>
                                  <td>{new Date(t.timestamp_utc).toLocaleString('it-IT')}</td>
                                  <td>
                                    <span className={t.side === 'buy' ? 'ok-text' : 'error-text'}>
                                      {t.side.toUpperCase()}
                                    </span>
                                  </td>
                                  <td>{qty.toFixed(6)}</td>
                                  <td>${px.toLocaleString('en-US', { maximumFractionDigits: 4 })}</td>
                                  <td>${total.toFixed(2)}</td>
                                  <td className={tPnl == null ? '' : tPnl >= 0 ? 'ok-text' : 'error-text'}>
                                    {tPnl == null ? '—' : `${tPnl >= 0 ? '+' : ''}${tPnl.toFixed(2)} $`}
                                  </td>
                                  <td>{t.status}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {spotData?.open_positions.length === 0 && !activeWallet?.balance_bnb && (
            <Empty title="Nessun asset" detail="Nessuna posizione spot aperta e nessun bilancio BNB disponibile." />
          )}
        </div>
      )}

      {/* ── CONFIGURAZIONE ───────────────────────────────────────── */}
      {data && (
        <>
          <div className="subhead" style={{ marginTop: 24 }}>
            <h3>Configurazione Esecuzione</h3>
          </div>
          <div className="provider-row">
            <label>
              <span>BSC chain</span>
              <select
                value={data.bsc_network || (data.chain_id === 56 ? 'mainnet' : 'testnet')}
                disabled={!canAdmin}
                onChange={(event) => onNetwork(event.target.value as 'testnet' | 'mainnet')}
              >
                <option value="testnet">Testnet</option>
                <option value="mainnet">Mainnet</option>
              </select>
            </label>
            <label>
              <span>Spot provider</span>
              <select value={data.spot_active_provider} disabled={!canAdmin} onChange={(event) => onSpotProvider(event.target.value)}>
                <option value="twak">TWAK</option>
                <option value="pancakeswap">PancakeSwap</option>
              </select>
            </label>
            <label>
              <span>Perp provider</span>
              <select value={data.perp_active_provider} disabled={!canAdmin} onChange={(event) => onPerpProvider(event.target.value)}>
                <option value="bnb_sdk">BNB SDK</option>
              </select>
            </label>
            <div className="network-chip">
              <span>{data.network}</span>
              <strong>Chain {data.chain_id}</strong>
            </div>
          </div>

          <div className="wallet-select-row">
            <label>
              <span>Wallet attivo</span>
              <select value={data.active_wallet_address || ''} disabled={!canAdmin} onChange={(event) => onWallet(event.target.value)}>
                {(data.available_wallets || []).map((w) => (
                  <option key={w.address} value={w.address}>{shortAddress(w.address)}</option>
                ))}
              </select>
            </label>
            <input
              aria-label="Nuovo indirizzo wallet"
              placeholder="Aggiungi indirizzo wallet"
              value={walletDraft}
              disabled={!canAdmin}
              onChange={(event) => onWalletDraft(event.target.value)}
            />
            <button onClick={onAddWallet} disabled={!canAdmin || !walletDraft.trim()}>Aggiungi</button>
          </div>
          {!canAdmin && <p className="hint">Token admin richiesto per modifiche provider e RPC.</p>}

          <div className="wallet-grid">
            {data.wallets.map((w) => (
              <button
                className="wallet-item"
                key={`${w.market}-${w.provider}`}
                onClick={() => w.address && void navigator.clipboard.writeText(w.address)}
                title={w.address ? 'Copia indirizzo' : 'Indirizzo non configurato'}
              >
                <span className="wallet-title">
                  <strong>{w.provider}</strong>
                  {w.active && <em>active</em>}
                </span>
                <span>{w.market.toUpperCase()} / {w.network}</span>
                <code>{w.address || 'non configurato'}</code>
                <span className={w.configured ? 'ok-text' : 'warn-text'}>
                  {w.configured ? 'configurato' : 'mancante'} / {w.balance_bnb ?? '--'} BNB
                </span>
              </button>
            ))}
          </div>

          <div className="subhead" style={{ marginTop: 20 }}>
            <h3>RPC Endpoints</h3>
          </div>
          <div className="rpc-list">
            {data.rpc_endpoints.map((ep) => (
              <div className="rpc-item" key={ep.index}>
                <div>
                  <strong>{ep.index + 1}. {ep.label}</strong>
                  <span>{ep.status} / {ep.latency_ms == null ? '--' : `${ep.latency_ms}ms`}</span>
                </div>
                {ep.active ? <span className="pill ok">active</span> : (
                  <button onClick={() => onRpcEndpoint(ep.index)} disabled={!canAdmin}>Usa</button>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* ── SEND / RECEIVE MODAL ─────────────────────────────────── */}
      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <strong>{modal.mode === 'send' ? '↑ Invia' : '↓ Ricevi'} {modal.asset}</strong>
              <button className="modal-close" onClick={() => setModal(null)}>✕</button>
            </div>
            {modal.mode === 'receive' ? (
              <div className="modal-body">
                <p className="muted">Invia {modal.asset} a questo indirizzo wallet:</p>
                <code className="address-display">{activeWallet?.address ?? 'Nessun wallet attivo'}</code>
                {activeWallet?.address && (
                  <div className="modal-actions">
                    <button
                      className="primary"
                      onClick={() => { void navigator.clipboard.writeText(activeWallet.address); setModal(null); }}
                    >
                      Copia indirizzo
                    </button>
                    <button onClick={() => setModal(null)}>Chiudi</button>
                  </div>
                )}
              </div>
            ) : (
              <div className="modal-body">
                {sendState === 'success' ? (
                  <>
                    <div className="send-result ok">
                      <strong>✓ Transazione inviata</strong>
                      {sendResult?.tx_hash && (
                        <code className="address-display">{sendResult.tx_hash}</code>
                      )}
                    </div>
                    <div className="modal-actions">
                      <button className="primary" onClick={() => setModal(null)}>Chiudi</button>
                    </div>
                  </>
                ) : sendState === 'error' ? (
                  <>
                    <div className="send-result err">
                      <strong>✗ Errore</strong>
                      <span>{sendResult?.error}</span>
                    </div>
                    <div className="modal-actions">
                      <button onClick={() => setSendState('idle')}>Riprova</button>
                      <button onClick={() => setModal(null)}>Chiudi</button>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="send-info-grid">
                      <div><span>Asset</span><strong>{modal.asset}</strong></div>
                      <div><span>Da wallet</span><code>{activeWallet ? shortAddress(activeWallet.address) : '—'}</code></div>
                      <div><span>Network</span><strong>{data?.network ?? '—'} · Chain {data?.chain_id}</strong></div>
                      <div><span>Provider</span><strong>{data?.spot_active_provider ?? '—'}</strong></div>
                    </div>
                    <label className="send-field">
                      <span>Indirizzo destinazione</span>
                      <input
                        placeholder="0x..."
                        value={sendTo}
                        onChange={(e) => setSendTo(e.target.value)}
                        disabled={sendState === 'sending'}
                      />
                    </label>
                    <label className="send-field">
                      <span>Importo ({modal.asset})</span>
                      <div className="send-amount-row">
                        <input
                          type="number"
                          min="0"
                          step="any"
                          placeholder="0.00"
                          value={sendAmount}
                          onChange={(e) => setSendAmount(e.target.value)}
                          disabled={sendState === 'sending'}
                        />
                        {modal.asset === 'BNB' && activeWallet?.balance_bnb && (
                          <button
                            onClick={() => setSendAmount(activeWallet.balance_bnb!)}
                            disabled={sendState === 'sending'}
                          >
                            MAX
                          </button>
                        )}
                      </div>
                    </label>
                    <label className="send-field">
                      <span>Password wallet</span>
                      <input
                        type="password"
                        placeholder="Password per sbloccare il wallet"
                        value={sendPassword}
                        onChange={(e) => setSendPassword(e.target.value)}
                        disabled={sendState === 'sending'}
                      />
                    </label>
                    <p className="hint">La password viene usata solo per firmare la transazione e non viene salvata.</p>
                    <div className="modal-actions">
                      <button onClick={() => setModal(null)} disabled={sendState === 'sending'}>Annulla</button>
                      <button
                        className="primary"
                        onClick={() => void execSend()}
                        disabled={sendState === 'sending' || !sendTo.trim() || !sendAmount.trim() || !sendPassword.trim()}
                      >
                        {sendState === 'sending' ? 'Invio in corso…' : `Conferma Invio ${modal.asset}`}
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}

function KillSwitchPanel({
  agent,
  onSet,
  canAdmin,
}: {
  agent: LoadState<AgentStatus>;
  onSet: (state: KillSwitchState) => void;
  canAdmin: boolean;
}) {
  const current = agent.data?.kill_switch || 'unknown';
  return (
    <Panel title="Kill Switch" className="safety-panel">
      <div className={`switch-state ${current}`}>{String(current).replace('_', ' ')}</div>
      <div className="button-row">
        <button onClick={() => onSet('running')} disabled={!canAdmin}>Run</button>
        <button onClick={() => onSet('soft_stop')} disabled={!canAdmin}>Soft</button>
        <button className="danger" onClick={() => onSet('hard_stop')} disabled={!canAdmin}>Hard</button>
      </div>
      {!canAdmin && <p className="hint">Admin token required for safety controls.</p>}
    </Panel>
  );
}

function SupportPanel({
  tickets,
  detail,
  notifications,
  reply,
  onReply,
  canAdmin,
  archived,
  onArchiveView,
  onRefresh,
  onOpen,
  onSend,
  onStatus,
}: {
  tickets: LoadState<SupportTicketListResponse>;
  detail: LoadState<SupportTicketDetail>;
  notifications: LoadState<SupportNotificationResponse>;
  reply: string;
  onReply: (value: string) => void;
  canAdmin: boolean;
  archived: boolean;
  onArchiveView: (archived: boolean) => void;
  onRefresh: () => void;
  onOpen: (ticketId: string) => void;
  onSend: () => void;
  onStatus: (status: SupportTicketStatus) => void;
}) {
  const statuses: SupportTicketStatus[] = ['open', 'in_progress', 'waiting_user', 'resolved', 'closed'];
  const unread = notifications.data?.unread_count ?? 0;
  return (
    <Panel title="Support Tickets" action={<button onClick={onRefresh}>Load tickets</button>} className="wide">
      {!canAdmin && <Empty title="Admin token required" detail="Support queue management is admin-only in the dashboard." />}
      {canAdmin && unread > 0 && (
        <div className="notice warn">
          {unread} unread support message{unread === 1 ? '' : 's'}
          {notifications.data?.latest_ticket ? ` · ${notifications.data.latest_ticket.subject}` : ''}
        </div>
      )}
      <StateBlock state={tickets} empty="No support tickets loaded" />
      {canAdmin && tickets.data && (
        <div className="support-layout">
          <div className="support-list">
            <div className="support-tabs">
              <button className={!archived ? 'active' : ''} onClick={() => onArchiveView(false)}>Active</button>
              <button className={archived ? 'active' : ''} onClick={() => onArchiveView(true)}>Archive</button>
            </div>
            {tickets.data.items.map((ticket) => (
              <button key={ticket.ticket_id} onClick={() => onOpen(ticket.ticket_id)} className="support-ticket">
                <span>{ticket.display_name}</span>
                <strong>{ticket.subject}</strong>
                <em>{ticket.category} · {ticket.priority} · {ticket.status}</em>
              </button>
            ))}
          </div>
          <div className="support-detail">
            <StateBlock state={detail} empty="Select a ticket" />
            {detail.data && (
              <>
                <div className="detail-head">
                  <div>
                    <h3>{detail.data.subject}</h3>
                    <p>{detail.data.display_name} · {detail.data.device_id ?? 'no device'} · {detail.data.status}</p>
                  </div>
                  <div className="button-row">
                    <button onClick={() => onStatus('archived')} disabled={detail.data.status === 'archived'}>Archive</button>
                    <button onClick={() => onStatus('closed')} disabled={detail.data.status === 'closed' || detail.data.status === 'archived'}>Close</button>
                  </div>
                </div>
                {!archived && <div className="status-row">
                  {statuses.map((status) => (
                    <button
                      key={status}
                      onClick={() => onStatus(status)}
                      className={detail.data?.status === status ? 'active' : ''}
                    >
                      {status.replace('_', ' ')}
                    </button>
                  ))}
                </div>}
                <div className="support-thread">
                  {detail.data.messages.map((message) => (
                    <div key={message.message_id} className={`support-message ${message.sender_type}`}>
                      <span>{message.sender_type} · {shortDate(message.created_at)}</span>
                      <p>{message.body}</p>
                      {message.diagnostics && (
                        <pre>{JSON.stringify(message.diagnostics, null, 2)}</pre>
                      )}
                    </div>
                  ))}
                </div>
                {!['closed', 'archived'].includes(detail.data.status) && (
                  <div className="support-reply">
                    <textarea value={reply} onChange={(event) => onReply(event.target.value)} placeholder="Admin reply" />
                    <button className="primary" onClick={onSend} disabled={!reply.trim()}>Send reply</button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}

function LogsPanel({ logs, onRefresh, canAdmin }: { logs: LoadState<LogEntry[]>; onRefresh: () => void; canAdmin: boolean }) {
  return (
    <Panel title="Log Viewer" action={<button onClick={onRefresh}>Load logs</button>} className="wide">
      {!canAdmin && <Empty title="Admin token required" detail="Logs are admin-only and redacted by the backend." />}
      <StateBlock state={logs} empty="No logs loaded" />
      {logs.data && logs.data.length > 0 && (
        <div className="log-list">
          {logs.data.map((entry, index) => (
            <div className="log-line" key={`${entry.timestamp || 'line'}-${index}`}>
              <span>{entry.timestamp ? shortDate(entry.timestamp) : '--'}</span>
              <strong>{entry.level || 'LOG'}</strong>
              <em>{entry.logger || 'backend'}</em>
              <p>{entry.message}</p>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

const SETTING_LABELS: Record<string, string> = {
  perp_trend_shock_enabled: 'Filtro shock BTC perp',
  perp_trend_shock_adx_threshold: 'Shock BTC — ADX threshold',
  perp_trend_shock_natr_percentile: 'Shock BTC — NATR percentile',
  perp_trend_shock_volume_threshold: 'Shock BTC — Volume threshold',
  perp_trend_shock_recovery_confirmations: 'Shock BTC — Recovery confirmations',
};

function SettingsPanel({
  settings,
  draft,
  setDraft,
  onLoad,
  onSave,
}: {
  settings: LoadState<SettingsResponse>;
  draft: AgentSettings;
  setDraft: (value: AgentSettings) => void;
  onLoad: () => void;
  onSave: () => void;
}) {
  return (
    <Panel title="Agent Settings" action={<button onClick={onLoad}>Load</button>} className="wide">
      <StateBlock state={settings} empty="Load settings to edit the agent profile" />
      <div className="settings-grid">
        {settingFields.map((field) => (
          <label key={field}>
            <span>{SETTING_LABELS[field] ?? field.replaceAll('_', ' ')}</span>
            {typeof draft[field] === 'boolean' ? (
              <input
                type="checkbox"
                checked={Boolean(draft[field])}
                onChange={(event) => setDraft({ ...draft, [field]: event.target.checked })}
              />
            ) : (
              <input
                value={String(draft[field] ?? '')}
                onChange={(event) => setDraft({ ...draft, [field]: coerceSetting(event.target.value, draft[field]) })}
              />
            )}
          </label>
        ))}
      </div>
      <button className="primary" onClick={onSave}>Save settings</button>
    </Panel>
  );
}

function OnboardingPanel({
  checks,
  onValidate,
  canAdmin,
}: {
  checks: LoadState<CredentialCheck[]>;
  onValidate: () => void;
  canAdmin: boolean;
}) {
  return (
    <Panel title="Onboarding" action={<button onClick={onValidate}>Validate</button>} className="wide">
      {!canAdmin && <Empty title="Admin token required" detail="Validation locks and checks runtime credentials without exposing values." />}
      <StateBlock state={checks} empty="No onboarding validation yet" />
      {checks.data && checks.data.length > 0 && (
        <div className="check-grid">
          {checks.data.map((check) => (
            <div className="check-item" key={check.name}>
              <strong>{check.name}</strong>
              <span className={check.configured ? 'pill ok' : 'pill warn'}>{check.status}</span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function MarketsPanel({
  markets,
  onRefresh,
  canRead,
}: {
  markets: LoadState<MarketAsset[]>;
  onRefresh: () => void;
  canRead: boolean;
}) {
  return (
    <Panel title="Price Monitor" action={<button onClick={onRefresh}>Load 100</button>} className="wide">
      {!canRead && <Empty title="Read token required" detail="Market monitoring uses the backend market-data provider." />}
      <StateBlock state={markets} empty="No price snapshot loaded" />
      {markets.data && markets.data.length > 0 && (
        <Table
          columns={['Asset', 'Symbol', 'Price', '24h', 'Volume']}
          rows={markets.data.map((item) => [
            item.name,
            item.symbol,
            item.current_price == null ? '--' : fmtPrice(item.current_price),
            item.price_change_percentage_24h == null ? '--' : `${item.price_change_percentage_24h.toFixed(2)}%`,
            item.total_volume == null ? '--' : compact(item.total_volume),
          ])}
        />
      )}
    </Panel>
  );
}

const NOTIF_PREF_LABELS: Record<keyof NotificationPreferences, string> = {
  spot_trades: 'Spot Trades',
  perp_trades: 'Perp Trades',
  risk_alerts: 'Risk Alerts',
  daily_summary: 'Daily Summary',
  critical: 'Critical Events',
};

function NotificationPrefsPanel({
  notifPrefs,
  canAdmin,
  onLoad,
  onToggle,
}: {
  notifPrefs: LoadState<NotificationPreferencesResponse>;
  canAdmin: boolean;
  onLoad: () => void;
  onToggle: (key: keyof NotificationPreferences) => void;
}) {
  const prefs = notifPrefs.data?.preferences ?? null;
  const source = notifPrefs.data?.source ?? null;
  return (
    <Panel title="Notification Preferences" action={<button onClick={onLoad}>Load</button>}>
      {!canAdmin && <p className="muted">Admin token required to change preferences.</p>}
      <StateBlock state={notifPrefs} empty="Load to see notification preferences" />
      {source && <p className="muted" style={{ marginBottom: '0.5rem' }}>Source: <strong>{source}</strong></p>}
      {prefs && (
        <div>
          {(Object.keys(NOTIF_PREF_LABELS) as Array<keyof NotificationPreferences>).map((key) => (
            <div key={key} className="status-row">
              <span>{NOTIF_PREF_LABELS[key]}</span>
              <button
                className={prefs[key] ? 'ok-text' : 'muted'}
                onClick={() => canAdmin && onToggle(key)}
                disabled={!canAdmin}
                style={{ cursor: canAdmin ? 'pointer' : 'default', background: 'none', border: 'none', fontWeight: 600 }}
              >
                {prefs[key] ? 'ON' : 'OFF'}
              </button>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function ExportPanel({ payload }: { payload: unknown }) {
  const serialized = JSON.stringify(payload, null, 2);
  return (
    <Panel title="Strategy Export" className="wide">
      <div className="button-row">
        <button onClick={() => void navigator.clipboard.writeText(serialized)}>Copy JSON</button>
      </div>
      <pre className="json-dump">{serialized}</pre>
    </Panel>
  );
}

function StateBlock<T>({ state, empty }: { state: LoadState<T>; empty: string }) {
  if (state.loading) return <p className="muted">Loading...</p>;
  if (state.error) return <p className="error-text">{state.error}</p>;
  if (!state.data || (Array.isArray(state.data) && state.data.length === 0)) return <p className="muted">{empty}</p>;
  return null;
}

function StatusRow<T>({ label, state }: { label: string; state: LoadState<T> }) {
  const ok = !state.error && Boolean(state.data);
  return (
    <div className="status-row">
      <span>{label}</span>
      <strong className={ok ? 'ok-text' : 'warn-text'}>{state.loading ? 'loading' : ok ? 'ok' : 'check'}</strong>
    </div>
  );
}

function Metric({ label, value, tone = '' }: { label: string; value: string; tone?: string }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

const HISTORY_PAGE_OPTIONS = [20, 50, 100, 'all'] as const;
type HistoryPageSize = (typeof HISTORY_PAGE_OPTIONS)[number];

type SpotHistoryItem = SpotView['history'][number];
type PerpHistoryItem = PerpView['history'][number];

function shortPositionId(value?: string | null): string {
  if (!value) return '';
  return value.replace(/^pos_/, '').slice(0, 8);
}

const CLOSE_REASON_LABELS: Record<string, string> = {
  stop_loss: 'Stop Loss',
  breakeven: 'Breakeven',
  take_profit_1: 'Take Profit 1',
  take_profit_2: 'Take Profit 2',
  trailing_stop: 'Trailing Stop',
  time_stop: 'Time Stop',
};

function TradeHistoryTable({
  trades,
  market,
  session,
}: {
  trades: SpotHistoryItem[] | PerpHistoryItem[];
  market: 'spot' | 'perp';
  session: DashboardSession;
}) {
  const [search, setSearch] = useState('');
  const [filterSide, setFilterSide] = useState('all');
  const [filterDir, setFilterDir] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterReason, setFilterReason] = useState('all');
  const [pageSize, setPageSize] = useState<HistoryPageSize>(20);
  const [page, setPage] = useState(0);
  const [openTrade, setOpenTrade] = useState<string | null>(null);

  const sides = useMemo(() => ['all', ...Array.from(new Set(trades.map((t) => t.side)))], [trades]);
  const dirs = useMemo(
    () => (market === 'perp' ? ['all', ...Array.from(new Set((trades as PerpHistoryItem[]).map((t) => t.direction)))] : []),
    [trades, market],
  );
  const statuses = useMemo(() => ['all', ...Array.from(new Set(trades.map((t) => t.status)))], [trades]);
  const reasons = useMemo(
    () => ['all', ...Array.from(new Set((trades as (SpotHistoryItem & PerpHistoryItem)[]).map((t) => t.close_reason ?? '').filter(Boolean))).sort()],
    [trades],
  );

  const filtered = useMemo(() => {
    return (trades as (SpotHistoryItem & PerpHistoryItem)[]).filter((t) => {
      if (search && !t.asset.toLowerCase().includes(search.toLowerCase())) return false;
      if (filterSide !== 'all' && t.side !== filterSide) return false;
      if (market === 'perp' && filterDir !== 'all' && t.direction !== filterDir) return false;
      if (filterStatus !== 'all' && t.status !== filterStatus) return false;
      if (filterReason !== 'all' && (t.close_reason ?? '') !== filterReason) return false;
      return true;
    });
  }, [trades, search, filterSide, filterDir, filterStatus, filterReason, market]);

  const effectivePageSize = pageSize === 'all' ? Math.max(filtered.length, 1) : pageSize;
  const totalPages = Math.max(1, Math.ceil(filtered.length / effectivePageSize));
  const pg = Math.min(page, totalPages - 1);
  const pageItems = pageSize === 'all' ? filtered : filtered.slice(pg * effectivePageSize, (pg + 1) * effectivePageSize);
  const resetPage = () => setPage(0);

  if (trades.length === 0)
    return <Empty title="No trade history" detail="History will appear after the first confirmed order." />;

  return (
    <div className="trade-history-wrap">
      <div className="trade-history-controls">
        <div className="trade-history-filters">
          <input
            className="trade-history-search"
            placeholder="Asset…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); resetPage(); }}
          />
          <select value={filterSide} onChange={(e) => { setFilterSide(e.target.value); resetPage(); }}>
            {sides.map((s) => <option key={s} value={s}>{s === 'all' ? 'All sides' : s}</option>)}
          </select>
          {market === 'perp' && (
            <select value={filterDir} onChange={(e) => { setFilterDir(e.target.value); resetPage(); }}>
              {dirs.map((d) => <option key={d} value={d}>{d === 'all' ? 'All dirs' : d}</option>)}
            </select>
          )}
          <select value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); resetPage(); }}>
            {statuses.map((s) => <option key={s} value={s}>{s === 'all' ? 'All statuses' : s}</option>)}
          </select>
          {reasons.length > 1 && (
            <select value={filterReason} onChange={(e) => { setFilterReason(e.target.value); resetPage(); }}>
              <option value="all">Tutti i motivi</option>
              {reasons.filter((r) => r !== 'all').map((r) => (
                <option key={r} value={r}>{CLOSE_REASON_LABELS[r] ?? r}</option>
              ))}
            </select>
          )}
        </div>
        <div className="trade-history-pager">
          <select
            className="trade-history-page-size"
            value={String(pageSize)}
            onChange={(e) => {
              const nextSize = e.target.value === 'all' ? 'all' : Number(e.target.value);
              setPageSize(nextSize as HistoryPageSize);
              resetPage();
            }}
          >
            <option value="20">20 trade</option>
            <option value="50">50 trade</option>
            <option value="100">100 trade</option>
            <option value="all">Tutti</option>
          </select>
          <button className="pager-btn" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={pg === 0}>‹</button>
          <span className="pager-info">{pg + 1}/{totalPages} <span className="pager-total">({filtered.length})</span></span>
          <button className="pager-btn" onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={pg >= totalPages - 1}>›</button>
        </div>
      </div>
      <div className="trade-history-scroll">
        <table>
          <thead>
            <tr>
              <th>Asset</th>
              {market === 'perp' && <th>Pos</th>}
              <th>Side</th>
              {market === 'perp' && <th>Dir</th>}
              {market === 'perp' && <th>Lev</th>}
              <th>{market === 'spot' ? 'Amount' : 'Size'}</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>Investito</th>
              {market === 'perp' && <th>Margine</th>}
              <th>Val. uscita</th>
              <th>PnL $</th>
              <th>PnL %</th>
              <th>Status</th>
              <th>Motivo</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((t) => {
              const pnl = Number(t.pnl_usd ?? 0);
              const isGood = pnl >= 0;
              const isClose = market === 'perp' ? t.direction === 'close' : t.side === 'sell';
              const qty = market === 'spot' ? Number(t.amount ?? 0) : Number(t.size ?? 0);
              const entryP = Number(t.entry_price ?? t.price);
              const exitP = Number(t.current_or_exit_price ?? t.price);
              const invested = qty * entryP;
              const exitValue = qty * exitP;
              return (
                <tr
                  key={t.trade_id}
                  className={isClose ? 'tr-close' : ''}
                  onClick={() => setOpenTrade(openTrade === t.trade_id ? null : t.trade_id)}
                  style={{ cursor: 'pointer' }}
                >
                  <td><strong>{t.asset}</strong></td>
                  {market === 'perp' && <td>{t.position_id ? `Pos ${shortPositionId(t.position_id)}` : '--'}</td>}
                  <td><span className={t.side === 'buy' || t.side === 'long' ? 'ok-text' : 'error-text'}>{t.side}</span></td>
                  {market === 'perp' && <td><span className={t.direction === 'long' || t.direction === 'open' ? 'ok-text' : 'error-text'}>{t.direction}</span></td>}
                  {market === 'perp' && <td>{t.leverage ? `${t.leverage}x` : '-'}</td>}
                  <td className="num">{trimDecimals(market === 'spot' ? t.amount : t.size)}</td>
                  <td className="num">{fmtPrice(t.entry_price ?? t.price)}</td>
                  <td className="num">{fmtPrice(t.current_or_exit_price ?? t.price)}</td>
                  <td className="num">{qty > 0 ? money(invested) : '--'}</td>
                  {market === 'perp' && (
                    <td className="num">{qty > 0 && t.leverage ? money(invested / Number(t.leverage)) : '--'}</td>
                  )}
                  <td className="num">{qty > 0 ? money(exitValue) : '--'}</td>
                  <td className={`num ${isGood ? 'ok-text' : 'error-text'}`}>{t.pnl_usd ?? '--'}</td>
                  <td className={`num ${isGood ? 'ok-text' : 'error-text'}`}>{t.pnl_pct ?? '--'}%</td>
                  <td><span className="status-badge">{t.status}</span></td>
                  <td>{t.close_reason ? (CLOSE_REASON_LABELS[t.close_reason] ?? t.close_reason) : '—'}</td>
                  <td className="date-cell">{shortDate(t.timestamp_utc)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {openTrade && <TradeDetailInline tradeId={openTrade} session={session} />}
    </div>
  );
}

const RISK_LABELS: Record<string, string> = {
  daily_loss_limit: 'Daily loss cap',
  drawdown_cap: 'Drawdown cap',
  exposure_cap: 'Exposure cap',
  max_positions: 'Max positions',
  max_open_positions: 'Max positions',
  kill_switch: 'Kill switch',
  hard_stop: 'Hard stop',
};

function parseReasoning(raw: string | null | undefined): { brain: string; risk: string | null } {
  if (!raw) return { brain: '--', risk: null };
  const riskMatch = raw.match(/;\s*risk=(.+)$/);
  let brain = riskMatch ? raw.slice(0, riskMatch.index).trim() : raw;
  const risk = riskMatch ? riskMatch[1].trim() : null;
  brain = brain
    .replace(/^claude_not_configured_dry_run;\s*/i, '')
    .replace(/^claude_unavailable_dry_run;\s*/i, '')
    .replace(/\.$/, '')
    .trim();
  return { brain: brain || raw, risk };
}

function ReasoningCell({ reasoning }: { reasoning: string | null | undefined }) {
  const [expanded, setExpanded] = useState(false);
  const { brain, risk } = parseReasoning(reasoning);
  const MAX_LEN = 90;
  const isLong = brain.length > MAX_LEN;
  const displayText = isLong && !expanded ? brain.slice(0, MAX_LEN) + '…' : brain;
  const riskOk = !risk || risk === 'ok' || risk === 'allowed' || risk === 'pass';
  const riskLabel = risk ? (RISK_LABELS[risk] ?? risk.replace(/_/g, ' ')) : null;
  return (
    <div className="reasoning-content">
      <span className="reasoning-brain">{displayText}</span>
      {isLong && (
        <button
          className="reasoning-expand"
          onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
        >
          {expanded ? '▲ meno' : '▼ altro'}
        </button>
      )}
      {riskLabel && (
        <span className={`risk-badge ${riskOk ? 'risk-ok' : 'risk-block'}`}>
          {riskOk ? 'risk OK' : riskLabel}
        </span>
      )}
    </div>
  );
}

function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

function Table({ columns, rows, onRowClick }: { columns: string[]; rows: ReactNode[][]; onRowClick?: (index: number) => void }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={index}
              onClick={onRowClick ? () => onRowClick(index) : undefined}
              style={onRowClick ? { cursor: 'pointer' } : undefined}
            >
              {row.map((cell, cellIndex) => <td key={`${index}-${cellIndex}`}>{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EquityChart({ equity, range, onRange }: {
  equity: EquityCurveResponse | null;
  range?: EquityRange;
  onRange?: (r: EquityRange) => void;
}) {
  const items = equity?.items ?? [];
  if (items.length < 2) return <p className="muted">Dati insufficienti per il grafico.</p>;
  const points = items.map((pt) => ({
    pct: Number(pt.pnl_pct),
    btc: pt.btc_pct != null ? Number(pt.btc_pct) : null,
    label: new Date(pt.timestamp_utc).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }),
    equity: pt.equity_usd,
  }));
  const lastPnl = points[points.length - 1].pct;
  const hasBtc = (equity?.benchmark_available ?? false) && points.some((p) => p.btc != null);
  const lastBtc = hasBtc ? points[points.length - 1].btc ?? 0 : null;
  const RANGES: EquityRange[] = ['24h', '7d', 'all'];
  const rangeLabel: Record<EquityRange, string> = { '24h': '24h', '7d': '7g', 'all': 'Tutto' };
  return (
    <div className="equity-chart">
      <div className="equity-chart-head">
        <div className="equity-readouts">
          <div>
            <div className={`equity-big ${lastPnl >= 0 ? 'ok-text' : 'error-text'}`}>{lastPnl >= 0 ? '+' : ''}{lastPnl.toFixed(2)}%</div>
            <div className="equity-legend"><span style={{ color: '#F0B90B' }}>●</span> PnL cumulato</div>
          </div>
          {hasBtc && lastBtc != null && (
            <div>
              <div className={`equity-big ${lastBtc >= 0 ? 'ok-text' : 'error-text'}`}>{lastBtc >= 0 ? '+' : ''}{lastBtc.toFixed(2)}%</div>
              <div className="equity-legend"><span style={{ color: '#3B82F6' }}>●</span> BTC trend</div>
            </div>
          )}
        </div>
        {onRange && range && (
          <div className="equity-ranges">
            {RANGES.map((r) => (
              <button key={r} className={r === range ? 'active' : ''} onClick={() => onRange(r)}>{rangeLabel[r]}</button>
            ))}
          </div>
        )}
      </div>
      <EquityLineChart points={points} />
    </div>
  );
}

function EquityLineChart({ points }: { points: { pct: number; label: string; equity?: string | number; btc?: number | null }[] }) {
  const n = points.length;
  if (n < 2) return <p className="muted">Dati insufficienti per il grafico.</p>;

  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const PNL_COLOR = '#F0B90B';
  const BTC_COLOR = '#3B82F6';
  const hasBtc = points.some((p) => p.btc != null);
  const W = 520, H = 180, padL = 48, padR = 16, padT = 12, padB = 24;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const vals = points.map((p) => p.pct);
  const btcVals = points.map((p) => (p.btc != null ? p.btc : null)).filter((v): v is number => v != null);
  let lo = Math.min(...vals, ...btcVals, 0);
  let hi = Math.max(...vals, ...btcVals, 0);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.12;
  lo -= pad; hi += pad;

  const xAt = (i: number) => padL + (i / (n - 1)) * plotW;
  const yAt = (v: number) => padT + (1 - (v - lo) / (hi - lo)) * plotH;
  const y0 = yAt(0);

  const pnlLine = points.map((p, i) => `${xAt(i).toFixed(1)},${yAt(p.pct).toFixed(1)}`).join(' ');
  const btcLine = hasBtc
    ? points.map((p, i) => (p.btc != null ? `${xAt(i).toFixed(1)},${yAt(p.btc).toFixed(1)}` : null)).filter(Boolean).join(' ')
    : '';
  const areaPath =
    `M ${xAt(0).toFixed(1)},${y0.toFixed(1)} ` +
    points.map((p, i) => `L ${xAt(i).toFixed(1)},${yAt(p.pct).toFixed(1)}`).join(' ') +
    ` L ${xAt(n - 1).toFixed(1)},${y0.toFixed(1)} Z`;

  const gridVals = [hi, (hi + lo) / 2, lo];
  const xIdxs = n <= 4 ? points.map((_, i) => i) : [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1];
  const lastPct = vals[n - 1];

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const scaleX = W / rect.width;
    const svgX = (e.clientX - rect.left) * scaleX;
    const rawIdx = (svgX - padL) / plotW * (n - 1);
    const idx = Math.max(0, Math.min(n - 1, Math.round(rawIdx)));
    setHoverIdx(idx);
  };

  const hov = hoverIdx !== null ? points[hoverIdx] : null;
  const hovX = hoverIdx !== null ? xAt(hoverIdx) : null;
  const hovY = hov !== null && hov !== undefined ? yAt(hov.pct) : null;

  // tooltip box: flip to left side when too close to right edge
  const tooltipLeft = hovX !== null && hovX > W * 0.65;

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${W} ${H}`}
      style={{ width: '100%', height: 'auto', cursor: 'crosshair' }}
      role="img"
      aria-label="Equity curve"
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setHoverIdx(null)}
    >
      <defs>
        <linearGradient id="dashPnlFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={PNL_COLOR} stopOpacity="0.25" />
          <stop offset="100%" stopColor={PNL_COLOR} stopOpacity="0" />
        </linearGradient>
      </defs>
      {gridVals.map((v, i) => (
        <g key={i}>
          <line x1={padL} y1={yAt(v)} x2={W - padR} y2={yAt(v)} stroke="#ffffff" strokeOpacity="0.07" strokeWidth="1" />
          <text x={padL - 4} y={yAt(v) + 3} textAnchor="end" fontSize="9" fill="#6b7280">
            {v >= 0 ? '+' : ''}{v.toFixed(1)}%
          </text>
        </g>
      ))}
      <line x1={padL} y1={y0} x2={W - padR} y2={y0} stroke="#9ca3af" strokeOpacity="0.5" strokeWidth="1" strokeDasharray="4 3" />
      <path d={areaPath} fill="url(#dashPnlFill)" />
      {btcLine && <polyline points={btcLine} fill="none" stroke={BTC_COLOR} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />}
      <polyline points={pnlLine} fill="none" stroke={PNL_COLOR} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={xAt(n - 1)} cy={yAt(lastPct)} r="3.5" fill={PNL_COLOR} stroke="#0b0e14" strokeWidth="1.5" />
      {xIdxs.map((idx) => (
        <text key={idx} x={xAt(idx)} y={H - 4} textAnchor="middle" fontSize="9" fill="#6b7280">
          {points[idx].label}
        </text>
      ))}

      {/* crosshair + tooltip */}
      {hoverIdx !== null && hovX !== null && hovY !== null && hov !== null && (
        <g>
          {/* vertical line */}
          <line x1={hovX} x2={hovX} y1={padT} y2={H - padB} stroke="#ffffff" strokeOpacity="0.25" strokeWidth="1" strokeDasharray="3 3" />
          {/* dot on curve */}
          <circle cx={hovX} cy={hovY} r="4.5" fill={PNL_COLOR} stroke="#0b0e14" strokeWidth="2" />
          {/* tooltip box */}
          <g transform={`translate(${tooltipLeft ? hovX - 94 : hovX + 10},${Math.min(H - padB - 46, Math.max(padT, hovY - 28))})`}>
            <rect x="0" y="0" width="84" height="46" rx="4" fill="#1a1f2e" stroke="#2d3348" strokeWidth="1" />
            <text x="6" y="13" fontSize="9" fill="#9ca3af">{hov.label}</text>
            {hov.equity != null && (
              <text x="6" y="26" fontSize="10" fill="#e5e7eb">{money(hov.equity)}</text>
            )}
            <text x="6" y={hov.equity != null ? 40 : 28} fontSize="10" fontWeight="600" fill={hov.pct >= 0 ? '#22c55e' : '#ef4444'}>
              {hov.pct >= 0 ? '+' : ''}{hov.pct.toFixed(2)}%
            </text>
          </g>
        </g>
      )}
    </svg>
  );
}

function money(value: string | number) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numeric);
}

const MICRO_PRICE_FULL_THRESHOLD = 0.000001;

function fmtMicroPrice(value: number, maxDecimals = 18): string {
  const sign = value < 0 ? '-' : '';
  const fixed = Math.abs(value).toFixed(maxDecimals).replace(/0+$/, '').replace(/\.$/, '');
  return fixed === '0' ? '$0' : `${sign}$${fixed}`;
}

function fmtSubDollarPrice(value: number): string {
  const decimals = Math.abs(value) < MICRO_PRICE_FULL_THRESHOLD ? 18 : 8;
  return fmtMicroPrice(value, decimals);
}

function fmtPrice(value: string | number | null | undefined): string {
  const n = Number(value);
  if (!Number.isFinite(n) || value == null || value === '') return '$--';
  if (n === 0) return '$0';
  if (n >= 1000) return `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  if (n >= 1)    return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  return fmtSubDollarPrice(n);
}

function trimDecimals(value: string | number | null | undefined, max = 8): string {
  if (value == null || value === '') return '-';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return String(parseFloat(n.toFixed(max)));
}

function compact(value: number) {
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(value);
}

function shortDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date);
}

function formatAge(value?: number | null) {
  if (value == null) return '--';
  if (value < 60) return `${Math.round(value)}s ago`;
  if (value < 3600) return `${Math.round(value / 60)}m ago`;
  return `${Math.round(value / 3600)}h ago`;
}

function shortAddress(value: string) {
  if (value.length <= 14) return value;
  return `${value.slice(0, 6)}...${value.slice(-6)}`;
}

function coerceSetting(value: string, previous: unknown) {
  if (typeof previous === 'boolean') return value === 'true';
  if (typeof previous === 'number') {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : previous;
  }
  return value;
}
