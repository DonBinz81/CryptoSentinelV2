import { useCallback, useEffect, useMemo, useRef, useState, type FC } from 'react';
import {
  fetchAgentSettings,
  fetchAgentStatus,
  fetchAgentDecisions,
  fetchAssetBreakdown,
  fetchEquityCurve,
  type ClaudeUsageView,
  fetchClaudeUsage,
  fetchExecutionWallets,
  fetchGlobalView,
  fetchPerpView,
  fetchSpotView,
  fetchTradeDetail,
  saveAgentSettings,
  setKillSwitch,
  riskCloseAll,
  adjustEquity,
  validateOnboarding,
  fetchSpotWatchlist,
  updateSpotWatchlist,
  fetchPerpWatchlist,
  updatePerpWatchlist,
  type AgentDecisionResponse,
  type AgentMarketWatchlistResponse,
  type AgentMobileSettings,
  type AgentStatus,
  type AssetBreakdownResponse,
  type CredentialValidationResponse,
  type EquityCurveResponse,
  type EquityRange,
  type ExecutionWalletsResponse,
  type GlobalView,
  type KillSwitchState,
  type PerpView,
  type SpotView,
  type TradeDetail,
} from '../services/agentApi';
import { hapticLight } from '../utils/haptics';

type AgentPane = 'spot' | 'perp' | 'global' | 'coins' | 'wallet' | 'setup';

const MICRO_PRICE_FULL_THRESHOLD = 0.000001;

const fmtUsd = (value: string | number | null | undefined) => {
  const n = Number(value ?? 0);
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const fmtMicroPrice = (value: number, maxDecimals = 18): string => {
  const sign = value < 0 ? '-' : '';
  const fixed = Math.abs(value).toFixed(maxDecimals).replace(/0+$/, '').replace(/\.$/, '');
  return fixed === '0' ? '$0' : `${sign}$${fixed}`;
};

const fmtSubDollarPrice = (value: number): string => {
  const decimals = Math.abs(value) < MICRO_PRICE_FULL_THRESHOLD ? 18 : 8;
  return fmtMicroPrice(value, decimals);
};

const fmtPrice = (value: string | number | null | undefined): string => {
  const n = Number(value);
  if (!Number.isFinite(n) || value == null || value === '') return '$--';
  if (n === 0) return '$0';
  if (n >= 1000) return `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  if (n >= 1)    return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  return fmtSubDollarPrice(n);
};

const fmtPriceFull = (value: string | number | null | undefined): string => {
  if (value == null || value === '') return '-';
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  if (n === 0) return '$0';
  if (Math.abs(n) < 1) return fmtSubDollarPrice(n);
  const s = String(value);
  const dotIdx = s.indexOf('.');
  const intStr = Math.trunc(Math.abs(n)).toLocaleString('en-US');
  const sign = n < 0 ? '-' : '';
  if (dotIdx === -1) return `${sign}$${intStr}`;
  const decStr = s.slice(dotIdx + 1).slice(0, 8).replace(/0+$/, '');
  return decStr ? `${sign}$${intStr}.${decStr}` : `${sign}$${intStr}`;
};

const fmtPct = (value: string | number | null | undefined) => {
  const n = Number(value ?? 0);
  return `${n.toFixed(2)}%`;
};

const riskGuardrailText: Record<string, { title: string; detail: string }> = {
  drawdown_cap_guard: {
    title: 'Trading bloccato: drawdown cap',
    detail: 'Il drawdown ha superato la soglia impostata. Le nuove entrate spot e perp sono sospese.',
  },
  daily_loss_limit_guard: {
    title: 'Trading bloccato: perdita giornaliera',
    detail: 'La perdita giornaliera ha raggiunto il limite. Le nuove entrate sono sospese fino al reset UTC.',
  },
  portfolio_floor_guard: {
    title: 'Trading bloccato: equity minima',
    detail: 'Il capitale è sotto il floor di sicurezza. Le nuove entrate sono sospese.',
  },
};

const defaultSettings: AgentMobileSettings = {
  mode: 'conservative',
  markets_enabled: 'both',
  execution_mode: 'dry_run',
  network: 'testnet',
  test_scaling_pct: 10,
  operating_hours_utc: '00:00-23:59',
  drawdown_alert_enabled: true,
  daily_loss_limit_pct: -8,
  drawdown_cap_pct: -15,
  min_pool_liquidity_usd: 50000,
  market_reversal_filter_enabled: true,
  spot_breakeven_enabled: true,
  perp_breakeven_enabled: true,
  spot_trailing_enabled: true,
  perp_trailing_enabled: true,
  spot_time_stop_enabled: false,
  perp_time_stop_enabled: false,
  perp_trend_shock_enabled: true,
  perp_trend_shock_adx_threshold: 25,
  perp_trend_shock_natr_percentile: 90,
  perp_trend_shock_volume_threshold: 2.0,
  perp_trend_shock_recovery_confirmations: 3,
  perp_smart_sl_enabled: true,
  perp_smart_sl_l1_frac: 0.333,
  perp_smart_sl_l2_frac: 0.666,
  perp_smart_sl_split_l1: 0.25,
  perp_smart_sl_split_l2: 0.55,
  perp_smart_sl_split_l3: 0.20,
  perp_smart_sl_rebuy_mode: 'above_entry',
  perp_smart_sl_rebuy_above_entry_pct: 100,
  perp_smart_sl_split_l1_r2: 0.75,
  perp_smart_sl_split_l2_r2: 0.20,
  perp_smart_sl_split_l3_r2: 0.05,
  perp_smart_sl_delta_l1: 0.08,
  perp_smart_sl_delta_l2: 0.16,
  perp_smart_sl_confirmation_candles: 2,
  perp_smart_sl_max_reentries: 1,
  perp_smart_sl_tp_adjust_after_rebuy: true,
  perp_smart_sl_tp_recovery_delta_pct: 7,
  spot_breakeven_mode: 'atr' as const,
  perp_breakeven_mode: 'atr' as const,
  spot_sl_mode: 'atr' as const,
  perp_sl_mode: 'atr' as const,
  spot_structural_stop_lookback_candles: 20,
  spot_structural_stop_buffer_pct: 1.10,
  perp_structural_stop_lookback_candles: 20,
  perp_structural_stop_buffer_pct: 1.10,
  spot_capital_per_trade_pct: 6,
  spot_per_trade_pct: 1.5,
  spot_max_open_positions: 3,
  spot_max_exposure_pct: 30,
  spot_cooldown_minutes: 30,
  spot_max_slippage_pct: 1,
  perp_capital_per_trade_pct: 4,
  perp_per_trade_pct: 1.5,
  perp_max_open_positions: 5,
  perp_max_exposure_pct: 20,
  perp_cooldown_minutes: 15,
  perp_max_slippage_pct: 0.5,
  perp_fixed_margin_enabled: false,
  perp_fixed_margin_usd: 50,
  capital_per_trade_pct: 6,
  per_trade_pct: 1.5,
  max_open_positions: 3,
  max_total_exposure_pct: 30,
  max_slippage_pct: 1,
  cooldown_minutes: 30,
  spot_confidence_threshold: 0.7,
  spot_volatility_trigger_pct: 3,
  spot_relative_volume_threshold: 1.8,
  spot_atr_stop_multiplier: 1.5,
  spot_trailing_distance_pct: 2,
  spot_partial_take_profit_pct: 50,
  spot_tp1_close_pct: 50,
  spot_time_stop_hours: 6,
  perp_direction_mode: 'long_short',
  perp_min_leverage: 4,
  perp_max_leverage: 40,
  perp_value_area_pct: 68,
  perp_atr_stop_multiplier: 0.8,
  perp_trailing_mode: 'largo' as const,
  perp_trailing_pnl_pct: 0,
  perp_tp1_close_pct: 70,
  perp_time_stop_hours: 8,
  perp_fee_mode: 'taker' as const,
  spot_fee_mode: 'all' as const,
  post_close_candles: 10,
};

const AGENT_REFRESH_MS = 45_000;
// Refresh leggero (solo posizioni/PnL). 15s evita accavallamenti quando provider esterni rallentano.
const AGENT_FAST_REFRESH_MS = 15_000;
const TRADE_DETAIL_CACHE_TTL_MS = 10 * 60_000;
const TRADE_DETAIL_BASE_TIMEOUT_MS = 20_000;
const TRADE_DETAIL_ENRICH_TIMEOUT_MS = 25_000;
const TRADE_DETAIL_CACHE_MAX = 80;
// Matches the mobile history page size: open positions are always added on top.
const TRADE_DETAIL_PREFETCH_LIMIT = 8;
const TRADE_DETAIL_PREFETCH_CONCURRENCY = 2;
const TRADE_DETAIL_PREFETCH_RETRY_MS = 60_000;

const tradeDetailCache = new Map<string, { detail: TradeDetail; updatedAt: number }>();
const tradeDetailInflight = new Map<string, Promise<TradeDetail>>();
const tradeDetailPrefetchRetryAt = new Map<string, number>();

const hasBaseTradeChart = (detail: TradeDetail): boolean =>
  (detail.chart?.candles?.length ?? 0) > 1;

const needsPostCloseCandles = (detail: TradeDetail): boolean =>
  Boolean(detail.chart && !detail.chart.live && detail.chart.closed_at);

const hasCompleteTradeChart = (detail: TradeDetail): boolean => {
  if (!hasBaseTradeChart(detail)) return false;
  if (!detail.chart?.stop_reference) return false;
  if (!needsPostCloseCandles(detail)) return true;
  return (detail.chart?.post_close_candles?.length ?? 0) > 0;
};

const getCachedTradeDetail = (tradeId: string): TradeDetail | null => {
  const cached = tradeDetailCache.get(tradeId);
  if (!cached) return null;
  if (hasCompleteTradeChart(cached.detail)) return cached.detail;
  if (Date.now() - cached.updatedAt > TRADE_DETAIL_CACHE_TTL_MS) {
    tradeDetailCache.delete(tradeId);
    return null;
  }
  return cached.detail;
};

const hasCompleteCachedTradeDetail = (tradeId: string): boolean => {
  const cached = getCachedTradeDetail(tradeId);
  return cached != null && hasCompleteTradeChart(cached);
};

const isTradeDetailInflight = (tradeId: string): boolean =>
  tradeDetailInflight.has(`${tradeId}:base`) || tradeDetailInflight.has(`${tradeId}:chart`);

const shouldPrefetchTradeDetail = (tradeId: string): boolean => {
  if (hasCompleteCachedTradeDetail(tradeId) || isTradeDetailInflight(tradeId)) return false;
  return Date.now() >= (tradeDetailPrefetchRetryAt.get(tradeId) ?? 0);
};

const cacheTradeDetail = (tradeId: string, detail: TradeDetail) => {
  const existing = tradeDetailCache.get(tradeId)?.detail;
  if (existing && hasCompleteTradeChart(existing) && !hasCompleteTradeChart(detail)) {
    return;
  }
  if (existing && hasBaseTradeChart(existing) && !hasBaseTradeChart(detail)) {
    return;
  }
  if (tradeDetailCache.has(tradeId)) tradeDetailCache.delete(tradeId);
  tradeDetailCache.set(tradeId, { detail, updatedAt: Date.now() });
  if (hasCompleteTradeChart(detail)) {
    tradeDetailPrefetchRetryAt.delete(tradeId);
  }
  while (tradeDetailCache.size > TRADE_DETAIL_CACHE_MAX) {
    const oldest = tradeDetailCache.keys().next().value;
    if (!oldest) break;
    tradeDetailCache.delete(oldest);
  }
};

const fetchTradeDetailDeduped = (
  tradeId: string,
  options: { enrichChart?: boolean; timeoutMs?: number } = {},
): Promise<TradeDetail> => {
  const key = `${tradeId}:${options.enrichChart ? 'chart' : 'base'}`;
  const existing = tradeDetailInflight.get(key);
  if (existing) return existing;
  const request = fetchTradeDetail(tradeId, options)
    .then((detail) => {
      cacheTradeDetail(tradeId, detail);
      return detail;
    })
    .finally(() => {
      tradeDetailInflight.delete(key);
    });
  tradeDetailInflight.set(key, request);
  return request;
};

const EmptyState: FC<{ title: string; detail: string }> = ({ title, detail }) => (
  <div className="rounded-xl border border-dashed border-dark-600 bg-dark-800/60 px-4 py-8 text-center">
    <p className="text-sm font-semibold text-white">{title}</p>
    <p className="mt-1 text-xs text-gray-500 leading-relaxed">{detail}</p>
  </div>
);

const RiskGuardrailBanner: FC<{ guardrail: GlobalView['risk_guardrail'] }> = ({ guardrail }) => {
  if (!guardrail?.blocked) return null;
  const copy = guardrail.reason ? riskGuardrailText[guardrail.reason] : undefined;
  return (
    <div className="rounded-xl border border-accent-red/30 bg-accent-red/10 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-accent-red">{copy?.title ?? guardrail.title}</p>
          <p className="mt-1 text-xs leading-5 text-gray-300">{copy?.detail ?? guardrail.detail}</p>
        </div>
        <span className="rounded-full bg-accent-red/15 px-2 py-1 text-[11px] font-semibold text-accent-red">
          {guardrail.reason?.replace(/_/g, ' ') ?? 'blocked'}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">Drawdown <b className="text-white">{fmtPct(guardrail.drawdown_pct)}</b></span>
        <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">Cap <b className="text-white">{fmtPct(Math.abs(guardrail.drawdown_cap_pct))}</b></span>
      </div>
    </div>
  );
};

const Stat: FC<{ label: string; value: string; tone?: 'good' | 'bad' | 'neutral' }> = ({ label, value, tone = 'neutral' }) => (
  <div className="rounded-lg bg-dark-800 px-3 py-2 min-w-0">
    <p className="text-[11px] uppercase text-gray-500 truncate">{label}</p>
    <p className={`text-sm font-bold tabular-nums truncate ${
      tone === 'good' ? 'text-accent-green' : tone === 'bad' ? 'text-accent-red' : 'text-white'
    }`}>{value}</p>
  </div>
);

const EQUITY_RANGES: { id: EquityRange; label: string }[] = [
  { id: '24h', label: '24h' },
  { id: '7d', label: '7g' },
  { id: 'all', label: 'Tutto' },
];

const PNL_COLOR = '#F0B90B'; // oro (PnL cumulato)
const BTC_COLOR = '#3B82F6'; // blu (benchmark BTC)

const fmtSignedPct = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;

const EquityChart: FC<{
  equity: EquityCurveResponse | null;
  range: EquityRange;
  onRange: (r: EquityRange) => void;
}> = ({ equity, range, onRange }) => {
  const items = equity?.items ?? [];
  const n = items.length;

  const pnl = items.map((i) => Number(i.pnl_pct));
  const btc = items.map((i) => (i.btc_pct != null ? Number(i.btc_pct) : null));
  const hasBtc = (equity?.benchmark_available ?? false) && btc.some((v) => v != null);

  const lastPnl = n > 0 ? pnl[n - 1] : 0;
  const lastBtc = hasBtc ? (btc[n - 1] ?? 0) : null;

  // Dominio Y: include sempre lo 0% (breakeven) e un po' di margine.
  const pool = [...pnl, ...(hasBtc ? (btc.filter((v) => v != null) as number[]) : []), 0];
  let lo = Math.min(...pool);
  let hi = Math.max(...pool);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) { lo = -1; hi = 1; }
  if (lo === hi) { lo -= 1; hi += 1; }
  const padY = (hi - lo) * 0.12;
  lo -= padY; hi += padY;

  const W = 320, H = 170, padL = 40, padR = 14, padT = 10, padB = 22;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const xAt = (idx: number) => (n <= 1 ? padL + plotW / 2 : padL + (idx / (n - 1)) * plotW);
  const yAt = (v: number) => padT + (1 - (v - lo) / (hi - lo)) * plotH;
  const y0 = yAt(0);

  const polyline = (vals: (number | null)[]) =>
    vals
      .map((v, i) => (v == null ? null : `${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`))
      .filter(Boolean)
      .join(' ');

  const pnlLine = polyline(pnl);
  const btcLine = hasBtc ? polyline(btc) : '';
  const areaPath =
    n > 0
      ? `M ${xAt(0).toFixed(1)},${y0.toFixed(1)} ` +
        pnl.map((v, i) => `L ${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ') +
        ` L ${xAt(n - 1).toFixed(1)},${y0.toFixed(1)} Z`
      : '';

  const gridVals = [hi, (hi + lo) / 2, lo];

  const fmtX = (iso: string) => {
    const d = new Date(iso);
    return range === '24h'
      ? d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' });
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase text-gray-500">PnL cumulato</h3>
        <div className="flex gap-1">
          {EQUITY_RANGES.map((r) => (
            <button
              key={r.id}
              onClick={() => { hapticLight(); onRange(r.id); }}
              className={`rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
                range === r.id ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-6">
        <div>
          <div className={`text-2xl font-bold ${lastPnl >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
            {fmtSignedPct(lastPnl)}
          </div>
          <div className="text-[11px] text-gray-400">
            <span style={{ color: PNL_COLOR }}>●</span> PnL cumulato
          </div>
        </div>
        {hasBtc && lastBtc != null && (
          <div>
            <div className={`text-2xl font-bold ${lastBtc >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
              {fmtSignedPct(lastBtc)}
            </div>
            <div className="text-[11px] text-gray-400">
              <span style={{ color: BTC_COLOR }}>●</span> BTC trend
            </div>
          </div>
        )}
      </div>

      {n === 0 ? (
        <div className="py-6 text-center text-xs text-gray-500">Nessun dato nel periodo selezionato</div>
      ) : (
        <>
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 'auto' }} role="img" aria-label="Curva PnL cumulato">
            <defs>
              <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={PNL_COLOR} stopOpacity="0.28" />
                <stop offset="100%" stopColor={PNL_COLOR} stopOpacity="0" />
              </linearGradient>
            </defs>

            {/* griglia + label Y */}
            {gridVals.map((v, i) => (
              <g key={i}>
                <line x1={padL} y1={yAt(v)} x2={W - padR} y2={yAt(v)} stroke="#ffffff" strokeOpacity="0.06" strokeWidth="1" />
                <text x={padL - 4} y={yAt(v) + 3} textAnchor="end" fontSize="9" fill="#6b7280">
                  {v.toFixed(2)}%
                </text>
              </g>
            ))}

            {/* baseline 0% (breakeven) */}
            <line x1={padL} y1={y0} x2={W - padR} y2={y0} stroke="#9ca3af" strokeOpacity="0.5" strokeWidth="1" strokeDasharray="3 3" />

            {/* area sotto PnL */}
            {areaPath && <path d={areaPath} fill="url(#pnlFill)" />}

            {/* linea BTC */}
            {btcLine && <polyline points={btcLine} fill="none" stroke={BTC_COLOR} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}

            {/* linea PnL */}
            {pnlLine && <polyline points={pnlLine} fill="none" stroke={PNL_COLOR} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />}

            {/* dot finali */}
            {hasBtc && lastBtc != null && <circle cx={xAt(n - 1)} cy={yAt(lastBtc)} r="3" fill={BTC_COLOR} />}
            {n > 0 && <circle cx={xAt(n - 1)} cy={yAt(lastPnl)} r="3.5" fill={PNL_COLOR} stroke="#0b0e14" strokeWidth="1" />}
          </svg>

          <div className="flex justify-between px-1 text-[10px] text-gray-500">
            <span>{fmtX(items[0].timestamp_utc)}</span>
            <span>{fmtX(items[n - 1].timestamp_utc)}</span>
          </div>
        </>
      )}
    </div>
  );
};

const SegmentButton: FC<{ id: AgentPane; active: boolean; label: string; onClick: (id: AgentPane) => void }> = ({
  id, active, label, onClick,
}) => (
  <button
    onClick={() => { hapticLight(); onClick(id); }}
    className={`flex-1 rounded-lg px-2 py-2 text-xs font-semibold transition-colors ${
      active ? 'bg-accent-blue text-white' : 'bg-dark-800 text-gray-400'
    }`}
  >
    {label}
  </button>
);

const TokenToggle: FC<{
  symbol: string;
  selected: boolean;
  disabled: boolean;
  onToggle: (symbol: string) => void;
}> = ({ symbol, selected, disabled, onToggle }) => (
  <button
    type="button"
    disabled={disabled}
    onClick={() => { hapticLight(); onToggle(symbol); }}
    className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-45 ${
      selected
        ? 'border-accent-yellow/50 bg-accent-yellow/10 text-accent-yellow'
        : 'border-dark-700 bg-dark-800 text-gray-300'
    }`}
  >
    <span className="min-w-0 truncate text-sm font-semibold">{symbol}</span>
    <span className={`h-2.5 w-2.5 flex-shrink-0 rounded-full ${selected ? 'bg-accent-yellow' : 'bg-gray-600'}`} />
  </button>
);

const NumberInput: FC<{
  label: string;
  value: number;
  step?: number;
  onChange: (value: number) => void;
}> = ({ label, value, step = 1, onChange }) => {
  const [raw, setRaw] = useState(String(value));
  useEffect(() => { setRaw(String(value)); }, [value]);
  return (
    <label className="block">
      <span className="text-xs text-gray-500">{label}</span>
      <input
        type="number"
        step={step}
        value={raw}
        onChange={(e) => {
          const s = e.target.value;
          setRaw(s);
          const n = parseFloat(s);
          if (!Number.isNaN(n)) onChange(n);
        }}
        onBlur={() => setRaw(String(value))}
        className="mt-1 w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
      />
    </label>
  );
};

const SelectInput: FC<{
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}> = ({ label, value, options, onChange }) => (
  <label className="block">
    <span className="text-xs text-gray-500">{label}</span>
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="mt-1 w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
    >
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  </label>
);

const ToggleInput: FC<{
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}> = ({ label, checked, onChange }) => (
  <label className="flex items-center justify-between gap-3 rounded-lg border border-dark-700 bg-dark-800 px-3 py-2">
    <span className="min-w-0 text-sm font-semibold text-white">{label}</span>
    <input
      type="checkbox"
      checked={checked}
      onChange={(event) => onChange(event.target.checked)}
      className="h-5 w-5 accent-accent-blue"
    />
  </label>
);

const MOBILE_PAGE = 8;

type SpotHistoryRow = NonNullable<SpotView['history']>[number];
type PerpHistoryRow = NonNullable<PerpView['history']>[number];

function shortPositionId(value?: string | null): string {
  if (!value) return '';
  return value.replace(/^pos_/, '').slice(0, 8);
}

const CLOSE_REASON_LABELS: Record<string, { label: string; className: string }> = {
  stop_loss: { label: 'Stop Loss', className: 'text-accent-red' },
  breakeven: { label: 'Breakeven', className: 'text-gray-300' },
  take_profit_1: { label: 'Take Profit 1', className: 'text-accent-green' },
  take_profit_2: { label: 'Take Profit 2', className: 'text-accent-green' },
  trailing_stop: { label: 'Trailing Stop', className: 'text-accent-green' },
  time_stop: { label: 'Time Stop', className: 'text-gray-300' },
  smart_sl_sell_l1: { label: 'Smart SL Sell L1', className: 'text-amber-400' },
  smart_sl_sell_l2: { label: 'Smart SL Sell L2', className: 'text-amber-400' },
  smart_sl_rebuy_l1: { label: 'Smart SL Rebuy L1', className: 'text-sky-400' },
  smart_sl_rebuy_l2: { label: 'Smart SL Rebuy L2', className: 'text-sky-400' },
  smart_sl_rebuy_all: { label: 'Smart SL Rebuy All', className: 'text-sky-400' },
};

const TradeHistoryList: FC<{
  trades: SpotHistoryRow[] | PerpHistoryRow[];
  market: 'spot' | 'perp';
  onTrade: (id: string) => void;
}> = ({ trades, market, onTrade }) => {
  const [search, setSearch] = useState('');
  const [filterSide, setFilterSide] = useState('all');
  const [filterDir, setFilterDir] = useState('all');
  const [page, setPage] = useState(0);

  const sides = useMemo(() => ['all', ...Array.from(new Set(trades.map((t) => t.side)))], [trades]);
  const dirs = useMemo(
    () => (market === 'perp' ? ['all', ...Array.from(new Set((trades as PerpHistoryRow[]).map((t) => t.direction)))] : []),
    [trades, market],
  );

  const filtered = useMemo(() => {
    return (trades as (SpotHistoryRow & PerpHistoryRow)[]).filter((t) => {
      if (search && !t.asset.toLowerCase().includes(search.toLowerCase())) return false;
      if (filterSide !== 'all' && t.side !== filterSide) return false;
      if (market === 'perp' && filterDir !== 'all' && t.direction !== filterDir) return false;
      return true;
    });
  }, [trades, search, filterSide, filterDir, market]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / MOBILE_PAGE));
  const pg = Math.min(page, totalPages - 1);
  const pageItems = filtered.slice(pg * MOBILE_PAGE, (pg + 1) * MOBILE_PAGE);
  const resetPage = () => setPage(0);

  if (trades.length === 0) return null;

  return (
    <div className="space-y-2">
      {/* filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); resetPage(); }}
          placeholder="Asset…"
          className="w-24 flex-shrink-0 rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white outline-none"
        />
        <select
          value={filterSide}
          onChange={(e) => { setFilterSide(e.target.value); resetPage(); }}
          className="flex-1 min-w-0 rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white outline-none"
        >
          {sides.map((s) => <option key={s} value={s}>{s === 'all' ? 'All sides' : s}</option>)}
        </select>
        {market === 'perp' && (
          <select
            value={filterDir}
            onChange={(e) => { setFilterDir(e.target.value); resetPage(); }}
            className="flex-1 min-w-0 rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white outline-none"
          >
            {dirs.map((d) => <option key={d} value={d}>{d === 'all' ? 'Open+Close' : d}</option>)}
          </select>
        )}
      </div>

      {/* trade cards */}
      {pageItems.map((t) => {
        const pnl = Number(t.pnl_usd ?? 0);
        const isGood = pnl >= 0;
        const isClose = market === 'perp' ? t.direction === 'close' : t.side === 'sell';
        const label = market === 'perp'
          ? `${t.asset} ${t.side} ${t.leverage ? t.leverage + 'x' : ''} · ${t.direction}`
          : `${t.asset} ${t.side}`;
        return (
          <button
            key={t.trade_id}
            onClick={() => onTrade(t.trade_id)}
            className={`h-auto w-full rounded-xl border-0 px-4 py-3 text-left text-sm ${isClose ? 'bg-dark-700' : 'bg-dark-800'}`}
          >
            <div className="flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-white">{label}</div>
                {market === 'perp' && t.position_id && (
                  <div className="mt-1 text-[11px] font-semibold text-accent-blue">
                    Pos {shortPositionId(t.position_id)}
                  </div>
                )}
                <div className="mt-2 flex gap-3 text-sm text-gray-400">
                  <span>In {fmtPriceFull(t.entry_price ?? t.price)}</span>
                  <span>Out {fmtPriceFull(t.current_or_exit_price ?? t.price)}</span>
                </div>
              </div>
              <div className={`flex-shrink-0 text-right font-bold ${isGood ? 'text-accent-green' : 'text-accent-red'}`}>
                <div>{t.pnl_pct ?? '--'}%</div>
                <div>{isGood ? '+' : ''}{fmtUsd(t.pnl_usd ?? 0)}</div>
              </div>
            </div>
            <div className="mt-1.5 flex items-center justify-between text-xs text-gray-500">
              <span className="flex items-center gap-1.5">
                <span className="uppercase tracking-wide">{t.status}</span>
                {t.close_reason && CLOSE_REASON_LABELS[t.close_reason] && (
                  <span className={`rounded bg-dark-900 px-1.5 py-0.5 font-semibold ${CLOSE_REASON_LABELS[t.close_reason].className}`}>
                    {CLOSE_REASON_LABELS[t.close_reason].label}
                  </span>
                )}
              </span>
              <span>
                {new Date(t.timestamp_utc).toLocaleString('it-IT', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          </button>
        );
      })}

      {/* pager */}
      <div className="flex items-center justify-between text-sm text-gray-500 pt-1">
        <button
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={pg === 0}
          className="px-4 py-1.5 rounded-lg bg-dark-800 border border-dark-600 disabled:opacity-30 text-sm"
        >‹ Prev</button>
        <span>{pg + 1}/{totalPages} ({filtered.length} trade)</span>
        <button
          onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
          disabled={pg >= totalPages - 1}
          className="px-4 py-1.5 rounded-lg bg-dark-800 border border-dark-600 disabled:opacity-30 text-sm"
        >Next ›</button>
      </div>
    </div>
  );
};

const SpotPane: FC<{ data: SpotView | null; onTrade: (tradeId: string) => void }> = ({ data, onTrade }) => {
  const hasPositions = (data?.open_positions.length ?? 0) > 0;
  const hasHistory = (data?.history.length ?? 0) > 0;
  const hasActivity = hasPositions || hasHistory || Number(data?.realized_pnl_usd ?? 0) !== 0 || Number(data?.unrealized_pnl_usd ?? 0) !== 0;
  const riskOff = data?.market_risk_off ?? false;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Spot PnL" value={fmtUsd(Number(data?.realized_pnl_usd ?? 0) + Number(data?.unrealized_pnl_usd ?? 0))} tone={(Number(data?.realized_pnl_usd ?? 0) + Number(data?.unrealized_pnl_usd ?? 0)) >= 0 ? 'good' : 'bad'} />
        <Stat label="Win rate" value={fmtPct(data?.win_rate_pct ?? 0)} />
        <Stat label="Open" value={String(data?.open_positions.length ?? 0)} />
        <Stat label="Trade Tot" value={String(data?.trade_count ?? 0)} />
        <Stat label="Trade Day" value={String(data?.trade_count_today ?? 0)} />
        <Stat label="Bot Day" value={String(data?.bot_active_days ?? 0)} />
      </div>
      {!hasActivity && (
        riskOff
          ? <EmptyState title="Mercato bloccato per condizioni sfavorevoli" detail="BTC in downtrend: nuovi acquisti spot sospesi finché non rientra sopra la media." />
          : <EmptyState title="In attesa di segnali spot" detail="Nessuna posizione aperta e nessun trade registrato." />
      )}
      {hasPositions ? (
        <div className="space-y-2">
          {data!.open_positions.map((position) => (
            <button
              key={position.position_id}
              type="button"
              onClick={() => position.open_trade_id && onTrade(position.open_trade_id)}
              disabled={!position.open_trade_id}
              className="block w-full rounded-xl bg-dark-800 px-4 py-3 text-left transition active:scale-[0.99] disabled:cursor-default"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-white">{position.asset}</p>
                <p className={Number(position.pnl_unrealized) >= 0 ? 'text-accent-green text-sm font-bold' : 'text-accent-red text-sm font-bold'}>
                  {fmtUsd(position.pnl_unrealized)} / {position.pnl_pct ?? '+0.00'}%
                </p>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-500">
                <span>Entry {fmtPriceFull(position.entry_price)}</span>
                <span>Now {fmtPriceFull(position.current_price)}</span>
                <span>{position.status}</span>
              </div>
              <div className="mt-1 grid grid-cols-3 gap-2 text-xs text-gray-500">
                <span>Mode: <span className={!position.fee_mode || position.fee_mode === 'none' ? 'text-gray-400' : 'text-accent-yellow'}>{position.fee_mode === 'none' ? 'nessuna' : position.fee_mode === 'all' ? 'swap+slip' : position.fee_mode ?? '-'}</span></span>
                <span>Swap {position.swap_fee_usd != null ? fmtUsd(position.swap_fee_usd) : '$0.00'}</span>
                <span>Slip. {position.slippage_usd != null ? fmtUsd(position.slippage_usd) : '$0.00'}</span>
              </div>
              <div className="mt-1.5 flex items-center justify-between text-xs text-gray-500">
                <span>{position.open_trade_id ? 'Tocca per dettagli ›' : ''}</span>
                <span>{new Date(position.opened_at).toLocaleString('it-IT', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
              </div>
            </button>
          ))}
        </div>
      ) : hasActivity && (
        riskOff
          ? <EmptyState title="Mercato bloccato per condizioni sfavorevoli" detail="BTC in downtrend: nuovi acquisti spot sospesi finché non rientra sopra la media." />
          : <EmptyState title="Nessuna posizione aperta" detail="Lo Spot e' pronto: le nuove entrate appariranno qui." />
      )}
      {hasHistory ? (
        <div className="space-y-2">
          <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Spot history</h3>
          <TradeHistoryList trades={data!.history} market="spot" onTrade={onTrade} />
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessun trade oggi" detail="Lo storico si popola quando l'agente prepara o chiude operazioni spot." />
      )}
    </div>
  );
};

const PerpPane: FC<{ data: PerpView | null; onTrade: (tradeId: string) => void }> = ({ data, onTrade }) => {
  const hasPositions = (data?.open_positions.length ?? 0) > 0;
  const hasHistory = (data?.history.length ?? 0) > 0;
  const hasActivity = hasPositions || hasHistory || Number(data?.realized_pnl_usd ?? 0) !== 0 || Number(data?.unrealized_pnl_usd ?? 0) !== 0;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Perp PnL" value={fmtUsd(Number(data?.realized_pnl_usd ?? 0) + Number(data?.unrealized_pnl_usd ?? 0))} tone={(Number(data?.realized_pnl_usd ?? 0) + Number(data?.unrealized_pnl_usd ?? 0)) >= 0 ? 'good' : 'bad'} />
        <Stat label="Win rate" value={fmtPct(data?.win_rate_pct ?? 0)} />
        <Stat label="Open" value={String(data?.open_positions.length ?? 0)} />
        <Stat label="Trade Tot" value={String(data?.trade_count ?? 0)} />
        <Stat label="Trade Day" value={String(data?.trade_count_today ?? 0)} />
        <Stat label="Bot Day" value={String(data?.bot_active_days ?? 0)} />
      </div>
      {!hasActivity && (
        <EmptyState title="In attesa di segnali perp" detail="Nessuna posizione aperta e nessun trade registrato." />
      )}
      {hasPositions ? (
        <div className="space-y-2">
          {data!.open_positions.map((position) => (
            <button
              key={position.position_id}
              type="button"
              onClick={() => position.open_trade_id && onTrade(position.open_trade_id)}
              disabled={!position.open_trade_id}
              className="block w-full rounded-xl bg-dark-800 px-4 py-3 text-left transition active:scale-[0.99] disabled:cursor-default"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-white">{position.asset} {position.side}</p>
                  <span className="rounded-full bg-dark-700 px-2 py-1 text-xs text-accent-blue">{position.leverage}x</span>
                  {position.smart_sl_active && (
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${position.smart_sl_levels_sold?.some(Boolean) ? 'bg-amber-900/40 text-amber-400' : 'bg-dark-700 text-gray-400'}`}>
                      SSL {position.smart_sl_levels_sold?.filter(Boolean).length ?? 0}/2
                    </span>
                  )}
                </div>
                <p className={Number(position.pnl_unrealized) >= 0 ? 'text-accent-green text-sm font-bold' : 'text-accent-red text-sm font-bold'}>
                  {fmtUsd(position.pnl_unrealized)} / {position.pnl_pct ?? '+0.00'}%
                </p>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-500">
                <span>Size {Number(position.size).toFixed(4)}</span>
                <span>Entry {fmtPriceFull(position.entry_price)}</span>
                <span>Now {fmtPriceFull(position.current_price)}</span>
              </div>
              <div className="mt-1 grid grid-cols-3 gap-2 text-xs text-gray-500">
                <span>Margin {position.margin_usd != null ? fmtUsd(position.margin_usd) : '$0.00'}</span>
                <span>Liq {position.liquidation_price ? fmtPrice(position.liquidation_price) : '-'}</span>
                <span>Funding {position.funding_rate ? fmtPct(Number(position.funding_rate) * 100) : '-'}</span>
              </div>
              <div className="mt-1.5 flex items-center justify-between text-xs text-gray-500">
                <span>{position.open_trade_id ? 'Tocca per dettagli ›' : ''}</span>
                <span>{new Date(position.opened_at).toLocaleString('it-IT', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
              </div>
            </button>
          ))}
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessuna posizione aperta" detail="Le posizioni perp long/short appariranno qui." />
      )}
      {hasHistory ? (
        <div className="space-y-2">
          <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Perp history</h3>
          <TradeHistoryList trades={data!.history} market="perp" onTrade={onTrade} />
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessun trade perp" detail="Lo storico perp si popola dopo le prime operazioni." />
      )}
    </div>
  );
};

const GlobalPane: FC<{
  data: GlobalView | null;
  status: AgentStatus | null;
  equity: EquityCurveResponse | null;
  equityRange: EquityRange;
  onEquityRange: (r: EquityRange) => void;
  decisions: AgentDecisionResponse | null;
  assetBreakdown: AssetBreakdownResponse | null;
  claudeUsage: ClaudeUsageView | null;
}> = ({ data, status, equity, equityRange, onEquityRange, decisions, assetBreakdown, claudeUsage }) => {
  const hasHistory = (data?.pnl_history.length ?? 0) > 0;
  const hasPortfolio = Number(data?.total_equity_usd ?? 0) > 0 || Number(data?.initial_equity_usd ?? 0) > 0;
  const hasTradesToday = Number(data?.trades_today ?? 0) > 0;
  const sortedAssets = [...(assetBreakdown?.items ?? [])].sort((a, b) => Number(b.pnl_usd) - Number(a.pnl_usd));
  const bestAssets = sortedAssets.slice(0, 3);
  const worstAssets = sortedAssets.slice(-3).reverse();

  return (
    <div className="space-y-3">
      <RiskGuardrailBanner guardrail={data?.risk_guardrail} />
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Equity" value={fmtUsd(data?.total_equity_usd)} />
        <Stat label="PnL tot." value={fmtUsd(data?.pnl_total_usd)} tone={Number(data?.pnl_total_usd ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="PnL aperto" value={fmtUsd(data?.unrealized_pnl_usd)} tone={Number(data?.unrealized_pnl_usd ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="PnL realizzato" value={fmtUsd(data?.realized_pnl_usd)} tone={Number(data?.realized_pnl_usd ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="PnL % Global" value={`${Number(data?.pnl_total_net_pct ?? 0) >= 0 ? '+' : ''}${Number(data?.pnl_total_net_pct ?? 0).toFixed(2)}%`} tone={Number(data?.pnl_total_net_pct ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="PnL % Day" value={`${Number(data?.daily_pnl_net_pct ?? 0) >= 0 ? '+' : ''}${Number(data?.daily_pnl_net_pct ?? 0).toFixed(2)}%`} tone={Number(data?.daily_pnl_net_pct ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="Drawdown" value={fmtPct(data?.drawdown_pct)} tone={Number(data?.drawdown_pct ?? 0) >= 10 ? 'bad' : 'neutral'} />
        <Stat label="Exposure" value={fmtPct(data?.exposure_pct)} />
        <Stat label="Trades UTC" value={String(data?.trades_today ?? 0)} />
        <Stat label="Kill switch" value={status?.kill_switch ?? data?.agent_status ?? 'idle'} />
        <Stat label="Fee pagate" value={fmtUsd(data?.total_fees_usd ?? '0')} tone="bad" />
        <Stat
          label="API Claude"
          value={claudeUsage != null ? `$${claudeUsage.total_cost_usd.toFixed(2)} / $${claudeUsage.budget_usd.toFixed(2)}` : '--'}
          tone={claudeUsage == null ? 'neutral' : claudeUsage.budget_pct >= 90 ? 'bad' : claudeUsage.budget_pct >= 70 ? 'neutral' : 'good'}
        />
      </div>
      {!hasPortfolio && !hasHistory && (
        <EmptyState title="In attesa dello stato globale" detail="Equity, drawdown ed esposizione saranno visibili al primo snapshot." />
      )}
      {!hasTradesToday && (
        <EmptyState title="Nessun trade oggi" detail="Il contatore UTC si aggiorna dopo il primo trade valido." />
      )}
      {hasHistory ? (
        <div className="rounded-xl bg-dark-800 px-4 py-3">
          <EquityChart equity={equity} range={equityRange} onRange={onEquityRange} />
        </div>
      ) : hasPortfolio && (
        <EmptyState title="Nessuno storico PnL" detail="La curva equity apparira' dopo i prossimi snapshot." />
      )}
      <div className="grid grid-cols-2 gap-2">
        <AssetRank title="Top asset" items={bestAssets} />
        <AssetRank title="Worst asset" items={worstAssets} />
      </div>
      <section className="space-y-2">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Ultime decisioni</h3>
        {(decisions?.items.length ?? 0) > 0 ? decisions!.items.slice(0, 3).map((item) => (
          <div key={item.decision_id} className="flex items-center justify-between rounded-lg bg-dark-800 px-3 py-2 text-xs">
            <span className="text-white">{item.action} {item.asset ?? '--'}</span>
            <span className="text-gray-500">{new Date(item.timestamp_utc).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        )) : (
          <EmptyState title="Nessuna decisione" detail="Le ultime valutazioni AI appariranno qui." />
        )}
      </section>
    </div>
  );
};

const AssetRank: FC<{ title: string; items: AssetBreakdownResponse['items'] }> = ({ title, items }) => (
  <section className="rounded-xl bg-dark-800 px-3 py-3">
    <h3 className="text-xs font-semibold uppercase text-gray-500">{title}</h3>
    <div className="mt-2 space-y-1.5">
      {items.length > 0 ? items.map((item) => (
        <div key={`${title}-${item.asset}`} className="flex items-center justify-between gap-2 text-xs">
          <span className="text-white">{item.asset}</span>
          <span className={Number(item.pnl_usd) >= 0 ? 'text-accent-green' : 'text-accent-red'}>{item.pnl_pct}%</span>
        </div>
      )) : <p className="text-xs text-gray-500">--</p>}
    </div>
  </section>
);

const WalletPane: FC<{
  execWallets: ExecutionWalletsResponse | null;
  spot: SpotView | null;
  perp: PerpView | null;
}> = ({ execWallets, spot, perp }) => {
  const [copied, setCopied] = useState<string | null>(null);

  const copyAddress = async (address: string) => {
    try { await navigator.clipboard.writeText(address); } catch {
      const el = document.createElement('textarea');
      el.value = address; document.body.appendChild(el); el.select();
      document.execCommand('copy'); document.body.removeChild(el);
    }
    setCopied(address);
    setTimeout(() => setCopied(null), 1600);
  };

  const totalSpotValue = (spot?.open_positions ?? []).reduce((sum, p) =>
    sum + Number(p.current_price) * Number(p.size), 0);
  const totalSpotPnl = (spot?.open_positions ?? []).reduce((sum, p) =>
    sum + Number(p.pnl_unrealized), 0);
  const totalPerpPnl = (perp?.open_positions ?? []).reduce((sum, p) =>
    sum + Number(p.pnl_unrealized), 0);
  const totalPnl = totalSpotPnl + totalPerpPnl;

  const activeWallet = execWallets?.available_wallets.find((w) => w.active)
    ?? execWallets?.available_wallets[0];

  return (
    <div className="space-y-4">

      {/* ── SUMMARY ── */}
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Spot" value={String(spot?.open_positions.length ?? 0)} />
        <Stat label="Perp" value={String(perp?.open_positions.length ?? 0)} />
        <Stat label="PnL aperto" value={fmtUsd(totalPnl)} tone={totalPnl >= 0 ? 'good' : 'bad'} />
      </div>

      {/* ── WALLET ATTIVO ── */}
      <section className="space-y-2">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">
          Wallet attivo · {execWallets?.network ?? '—'} (chain {execWallets?.chain_id ?? '—'})
        </h3>
        {activeWallet ? (
          <div className="rounded-xl bg-dark-800 px-4 py-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-xs text-gray-500">{activeWallet.network}</p>
                <p className="text-xs text-gray-500">
                  Spot: {execWallets?.spot_active_provider} · Perp: {execWallets?.perp_active_provider}
                </p>
              </div>
              <span className="rounded-full bg-accent-green/15 px-2 py-0.5 text-xs font-semibold text-accent-green">attivo</span>
            </div>
            <button onClick={() => copyAddress(activeWallet.address)} className="w-full text-left rounded-lg bg-dark-900 px-3 py-2">
              <p className="font-mono text-xs text-gray-300 break-all leading-relaxed">{activeWallet.address}</p>
              <p className="mt-0.5 text-[11px] text-accent-blue">{copied === activeWallet.address ? '✓ Copiato' : 'Tocca per copiare'}</p>
            </button>
            {/* BNB balance */}
            <div className="flex items-center justify-between rounded-lg bg-dark-900 px-3 py-2">
              <div>
                <p className="text-sm font-semibold text-white">BNB</p>
                <p className="text-[11px] text-gray-500">gas · {activeWallet.balance_status}</p>
              </div>
              <p className="font-mono text-sm font-bold text-accent-green">
                {activeWallet.balance_bnb ? `${parseFloat(activeWallet.balance_bnb).toFixed(6)} BNB` : '—'}
              </p>
            </div>
          </div>
        ) : (
          <EmptyState title="Wallet non configurato" detail="Aggiungi un indirizzo wallet dalla dashboard." />
        )}

        {/* altri wallet disponibili */}
        {(execWallets?.available_wallets.length ?? 0) > 1 && (
          <div className="space-y-1">
            <p className="px-1 text-[11px] text-gray-600 uppercase">Altri indirizzi</p>
            {execWallets!.available_wallets.filter((w) => !w.active).map((w) => (
              <button key={w.address} onClick={() => copyAddress(w.address)} className="w-full text-left rounded-lg bg-dark-800 px-3 py-2">
                <p className="font-mono text-xs text-gray-500 break-all">{w.address}</p>
                <p className="text-[11px] text-gray-600">{w.balance_bnb ? `${parseFloat(w.balance_bnb).toFixed(4)} BNB` : w.balance_status}</p>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* ── POSIZIONI SPOT ── */}
      <section className="space-y-2">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">
          Posizioni spot aperte {spot?.open_positions.length ? `(${fmtUsd(totalSpotValue)} valore)` : ''}
        </h3>
        {(spot?.open_positions.length ?? 0) === 0
          ? <EmptyState title="Nessuna posizione spot" detail="Le posizioni aperte dall'agente appariranno qui." />
          : (spot?.open_positions ?? []).map((p) => {
              const pnl = Number(p.pnl_unrealized);
              const isGood = pnl >= 0;
              const entry = Number(p.entry_price);
              const now = Number(p.current_price);
              const size = Number(p.size);
              return (
                <div key={p.position_id} className="rounded-xl bg-dark-800 px-4 py-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-white">{p.asset}</p>
                      <p className="text-xs text-gray-500">Spot · {p.status}</p>
                    </div>
                    <div className={`text-right font-bold ${isGood ? 'text-accent-green' : 'text-accent-red'}`}>
                      <p>{isGood ? '+' : ''}{fmtUsd(pnl)}</p>
                      <p className="text-xs">{p.pnl_pct ?? '+0.00'}%</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-1 text-xs text-gray-400">
                    <span>Size {size.toFixed(6)}</span>
                    <span>Entry {fmtPrice(entry)}</span>
                    <span>Now {fmtPrice(now)}</span>
                  </div>
                  {(p.stop_loss || p.take_profit_1) && (
                    <div className="grid grid-cols-2 gap-1 text-xs text-gray-500">
                      {p.stop_loss && <span>SL {fmtPrice(p.stop_loss)}</span>}
                      {p.take_profit_1 && <span>TP1 {fmtPrice(p.take_profit_1)}</span>}
                      {p.take_profit_2 && <span>TP2 {fmtPrice(p.take_profit_2)}</span>}
                    </div>
                  )}
                  <div className="mt-1 grid grid-cols-2 gap-1 text-xs text-gray-500">
                    <span>Mode: <span className={!p.fee_mode || p.fee_mode === 'none' ? 'text-gray-400' : 'text-accent-yellow'}>{p.fee_mode === 'none' ? 'nessuna' : p.fee_mode === 'all' ? 'swap+slip' : p.fee_mode ?? '-'}</span></span>
                    <span>Swap fee {p.swap_fee_usd != null ? fmtUsd(p.swap_fee_usd) : '$0.00'}</span>
                    <span>Slip. {p.slippage_usd != null ? fmtUsd(p.slippage_usd) : '$0.00'}</span>
                  </div>
                </div>
              );
            })}
      </section>

      {/* ── POSIZIONI PERP ── */}
      <section className="space-y-2">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">
          Posizioni perp aperte {perp?.open_positions.length ? `(PnL ${fmtUsd(totalPerpPnl)})` : ''}
        </h3>
        {(perp?.open_positions.length ?? 0) === 0
          ? <EmptyState title="Nessuna posizione perp" detail="Le posizioni long/short appariranno qui." />
          : (perp?.open_positions ?? []).map((p) => {
              const pnl = Number(p.pnl_unrealized);
              const isGood = pnl >= 0;
              return (
                <div key={p.position_id} className="rounded-xl bg-dark-800 px-4 py-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-white">{p.asset} <span className="text-accent-blue">{p.side}</span> {p.leverage}x</p>
                      <p className="text-xs text-gray-500">Perp · {p.status}</p>
                    </div>
                    <div className={`text-right font-bold ${isGood ? 'text-accent-green' : 'text-accent-red'}`}>
                      <p>{isGood ? '+' : ''}{fmtUsd(pnl)}</p>
                      <p className="text-xs">{p.pnl_pct ?? '+0.00'}%</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-1 text-xs text-gray-400">
                    <span>Size {Number(p.size).toFixed(4)}</span>
                    <span>Entry {fmtPriceFull(p.entry_price)}</span>
                    <span>Now {fmtPriceFull(p.current_price)}</span>
                  </div>
                  {(p.stop_loss || p.liquidation_price) && (
                    <div className="grid grid-cols-2 gap-1 text-xs text-gray-500">
                      {p.stop_loss && <span>SL {fmtPrice(p.stop_loss)}</span>}
                      {p.liquidation_price && <span className="text-accent-red">Liq {fmtPrice(p.liquidation_price)}</span>}
                    </div>
                  )}
                  <div className="mt-1 grid grid-cols-2 gap-1 text-xs text-gray-500">
                    <span>Margin {p.margin_usd != null ? fmtUsd(p.margin_usd) : '$0.00'}</span>
                    <span>Mode: <span className={!p.fee_mode || p.fee_mode === 'none' ? 'text-gray-400' : p.fee_mode === 'maker' ? 'text-accent-green' : 'text-accent-yellow'}>{p.fee_mode ?? '-'}</span></span>
                    <span>Fee {p.opening_fee_usd != null ? fmtUsd(p.opening_fee_usd) : '$0.00'}</span>
                    <span>Slip. {p.slippage_usd != null ? fmtUsd(p.slippage_usd) : '$0.00'}</span>
                    <span className={Number(p.funding_accrued_usd ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}>Fund. {p.funding_accrued_usd != null ? fmtUsd(p.funding_accrued_usd) : '$0.00'}</span>
                  </div>
                </div>
              );
            })}
      </section>

    </div>
  );
};

type CoinSubTab = 'master' | 'spot' | 'perp';

const CoinsPane: FC<{
  eligibleTokens: string[];
  selectedAiSymbols: Set<string>;
  adminToken: string;
  saving: boolean;
  error: string;
  onToggle: (symbol: string) => void;
}> = ({ eligibleTokens, selectedAiSymbols, adminToken, saving, error, onToggle }) => {
  const [subTab, setSubTab] = useState<CoinSubTab>('master');
  const [query, setQuery] = useState('');
  const [spotData, setSpotData] = useState<AgentMarketWatchlistResponse | null>(null);
  const [perpData, setPerpData] = useState<AgentMarketWatchlistResponse | null>(null);
  const [marketSaving, setMarketSaving] = useState(false);
  const [marketError, setMarketError] = useState('');

  useEffect(() => {
    void fetchSpotWatchlist().then(setSpotData).catch(() => undefined);
    void fetchPerpWatchlist().then(setPerpData).catch(() => undefined);
  }, []);

  const normalizedQuery = query.trim().toUpperCase();
  const masterTokens = eligibleTokens.filter((s) => selectedAiSymbols.has(s.toUpperCase()));
  const filteredEligible = eligibleTokens.filter((s) => s.toUpperCase().includes(normalizedQuery));

  const spotSelected = useMemo(() => new Set((spotData?.selected_tokens ?? []).map((s) => s.toUpperCase())), [spotData]);
  const perpSelected = useMemo(() => new Set((perpData?.selected_tokens ?? []).map((s) => s.toUpperCase())), [perpData]);

  const handleMarketToggle = async (symbol: string, market: 'spot' | 'perp') => {
    if (!adminToken || marketSaving) return;
    setMarketSaving(true);
    setMarketError('');
    try {
      if (market === 'spot') {
        const current = new Set(spotData?.selected_tokens ?? []);
        if (current.has(symbol)) current.delete(symbol); else current.add(symbol);
        const result = await updateSpotWatchlist([...current], adminToken);
        setSpotData(result);
      } else {
        const current = new Set(perpData?.selected_tokens ?? []);
        if (current.has(symbol)) current.delete(symbol); else current.add(symbol);
        const result = await updatePerpWatchlist([...current], adminToken);
        setPerpData(result);
      }
    } catch {
      setMarketError('Errore salvataggio watchlist');
    } finally {
      setMarketSaving(false);
    }
  };

  const disabled = !adminToken || saving;
  const marketDisabled = !adminToken || marketSaving;

  return (
    <div className="space-y-4">
      <section className="rounded-xl bg-dark-800 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-white">Agent coins</h3>
            <p className="mt-0.5 truncate text-xs text-gray-500">
              {subTab === 'master' && `Eligible ${eligibleTokens.length} · Master ${masterTokens.length}`}
              {subTab === 'spot' && `Master ${masterTokens.length} · Spot ${spotData?.selected_count ?? 0}`}
              {subTab === 'perp' && `Master ${masterTokens.length} · Perp ${perpData?.selected_count ?? 0}`}
            </p>
          </div>
          <span className="rounded-full bg-accent-yellow/15 px-2 py-1 text-xs font-semibold text-accent-yellow">
            {subTab === 'master' ? masterTokens.length : subTab === 'spot' ? (spotData?.selected_count ?? 0) : (perpData?.selected_count ?? 0)}
          </span>
        </div>
        {!adminToken && <p className="mt-3 rounded-lg bg-dark-900 px-3 py-2 text-xs text-gray-500">Inserisci admin token in Setup per modificare.</p>}
        {(error || marketError) && <p className="mt-3 rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{marketError || error}</p>}
        <div className="mt-3 grid grid-cols-3 gap-1">
          {(['master', 'spot', 'perp'] as CoinSubTab[]).map((t) => (
            <button
              key={t}
              onClick={() => { setSubTab(t); setQuery(''); }}
              className={`rounded-lg py-1.5 text-xs font-semibold capitalize transition-colors ${subTab === t ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'}`}
            >
              {t}
            </button>
          ))}
        </div>
      </section>

      {subTab === 'master' && (
        <>
          <section className="space-y-2">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Selezionate</h3>
            {masterTokens.length > 0 ? (
              <div className="grid grid-cols-2 gap-2">
                {masterTokens.map((symbol) => (
                  <TokenToggle key={`sel-${symbol}`} symbol={symbol} selected disabled={disabled} onToggle={onToggle} />
                ))}
              </div>
            ) : (
              <EmptyState title="Nessuna coin attiva" detail="Seleziona una coin tradabile per passarla all'agente." />
            )}
          </section>
          <section className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Eligible</h3>
              {saving && <span className="text-xs text-accent-yellow">Saving</span>}
            </div>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search token"
              className="w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
            />
            <div className="grid grid-cols-2 gap-2">
              {filteredEligible.map((symbol) => (
                <TokenToggle key={symbol} symbol={symbol} selected={selectedAiSymbols.has(symbol.toUpperCase())} disabled={disabled} onToggle={onToggle} />
              ))}
            </div>
            {filteredEligible.length === 0 && <EmptyState title="Nessun token trovato" detail="La ricerca filtra solo l'universo eligible." />}
          </section>
        </>
      )}

      {(subTab === 'spot' || subTab === 'perp') && (() => {
        const isSpot = subTab === 'spot';
        const selected = isSpot ? spotSelected : perpSelected;
        const activeMasterTokens = masterTokens.filter((s) => s.toUpperCase().includes(normalizedQuery));
        return (
          <section className="space-y-2">
            <p className="px-1 text-xs text-gray-500">
              Seleziona le coin dalla master watchlist da assegnare al mercato <span className="font-semibold text-white">{subTab.toUpperCase()}</span>.
            </p>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search token"
              className="w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
            />
            {marketSaving && <p className="text-xs text-accent-yellow">Saving…</p>}
            {masterTokens.length === 0 ? (
              <EmptyState title="Master watchlist vuota" detail="Aggiungi prima coin alla master watchlist." />
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {activeMasterTokens.map((symbol) => (
                  <TokenToggle
                    key={symbol}
                    symbol={symbol}
                    selected={selected.has(symbol.toUpperCase())}
                    disabled={marketDisabled}
                    onToggle={(s) => void handleMarketToggle(s, subTab)}
                  />
                ))}
              </div>
            )}
            {activeMasterTokens.length === 0 && masterTokens.length > 0 && (
              <EmptyState title="Nessun token trovato" detail="La ricerca filtra la master watchlist." />
            )}
          </section>
        );
      })()}
    </div>
  );
};

const SetupPane: FC<{
  settings: AgentMobileSettings;
  onSettings: (settings: AgentMobileSettings) => void;
  adminToken: string;
  onAdminToken: (value: string) => void;
  validation: CredentialValidationResponse | null;
  agentStatus: AgentStatus | null;
  saving: boolean;
  actionError: string;
  onSave: () => void;
  onValidate: () => void;
  onKill: (state: KillSwitchState) => void;
  onCloseAll: () => void;
  onAdjustEquity: (amount: number) => void;
}> = ({
  settings,
  onSettings,
  adminToken,
  onAdminToken,
  validation,
  agentStatus,
  saving,
  actionError,
  onSave,
  onValidate,
  onKill,
  onCloseAll,
  onAdjustEquity,
}) => {
  const patch = (partial: Partial<AgentMobileSettings>) => onSettings({ ...settings, ...partial });
  const [equityInput, setEquityInput] = useState('');
  const equityValue = Number(equityInput);
  const equityValid = equityInput.trim() !== '' && Number.isFinite(equityValue) && equityValue !== 0;

  return (
    <div className="space-y-4">
      <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-3">
        <h3 className="text-sm font-semibold text-white">Admin session</h3>
        <input
          type="password"
          value={adminToken}
          onChange={(event) => onAdminToken(event.target.value)}
          placeholder="Admin token"
          autoComplete="off"
          className="w-full rounded-lg border border-dark-600 bg-dark-900 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
        />
      </section>

      <section className="rounded-xl border border-accent-red/20 bg-dark-800 px-4 py-4 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-white">Kill switch</h3>
            <p className="mt-0.5 text-xs text-gray-500 truncate">Soft stop blocca nuove entrate. Hard stop ferma tutto.</p>
          </div>
          <span className={`rounded-full px-2 py-1 text-xs font-semibold ${
            agentStatus?.kill_switch === 'hard_stop'
              ? 'bg-accent-red/20 text-accent-red'
              : agentStatus?.kill_switch === 'soft_stop' || agentStatus?.kill_switch === 'degraded'
                ? 'bg-accent-yellow/20 text-accent-yellow'
                : 'bg-accent-green/15 text-accent-green'
          }`}>
            {agentStatus?.kill_switch ?? 'unknown'}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <button onClick={() => onKill('running')} disabled={!adminToken || saving} className="rounded-lg bg-dark-700 px-2 py-2.5 text-xs font-semibold text-gray-300 disabled:opacity-40">Run</button>
          <button onClick={() => onKill('soft_stop')} disabled={!adminToken || saving} className="rounded-lg bg-accent-yellow/20 px-2 py-2.5 text-xs font-semibold text-accent-yellow disabled:opacity-40">Soft</button>
          <button onClick={() => onKill('hard_stop')} disabled={!adminToken || saving} className="rounded-lg bg-accent-red/20 px-2 py-2.5 text-xs font-semibold text-accent-red disabled:opacity-40">Hard</button>
        </div>
        {!adminToken && <p className="text-xs text-gray-600">Richiede admin token salvato.</p>}
      </section>

      <section className="rounded-xl border border-accent-red/30 bg-dark-800 px-4 py-4 space-y-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-white">Risk · Chiusura di emergenza</h3>
          <p className="mt-0.5 text-xs text-gray-500">Chiude tutte le posizioni spot e perp al prezzo di mercato e mette l'agente in pausa (hard stop). Riprende solo quando premi Riprendi.</p>
        </div>
        <button
          onClick={onCloseAll}
          disabled={!adminToken || saving}
          className="w-full rounded-lg bg-accent-red px-3 py-3 text-sm font-bold text-white disabled:opacity-40"
        >
          {saving ? 'Esecuzione...' : '⛔ Chiudi tutto & metti in pausa'}
        </button>
        <button
          onClick={() => onKill('running')}
          disabled={!adminToken || saving || agentStatus?.kill_switch === 'running'}
          className="w-full rounded-lg bg-accent-green/20 px-3 py-2.5 text-sm font-semibold text-accent-green disabled:opacity-40"
        >
          ▶ Riprendi agente
        </button>
        {!adminToken && <p className="text-xs text-gray-600">Richiede admin token salvato.</p>}
      </section>

      <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-white">Liquidità · Versamento / Prelievo</h3>
          <p className="mt-0.5 text-xs text-gray-500">Aggiunge (o toglie, con valore negativo) capitale come un deposito. Alza l'equity senza contare come PnL. Es: <span className="text-gray-400">200</span> = +200$, <span className="text-gray-400">-50</span> = −50$.</p>
        </div>
        <div className="flex gap-2">
          <input
            type="number"
            inputMode="decimal"
            value={equityInput}
            onChange={(event) => setEquityInput(event.target.value)}
            placeholder="es. 200 oppure -50"
            className="flex-1 min-w-0 bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
          />
          <button
            onClick={() => { if (equityValid) { onAdjustEquity(equityValue); setEquityInput(''); } }}
            disabled={!adminToken || saving || !equityValid}
            className="rounded-lg bg-accent-blue px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            Applica
          </button>
        </div>
        {!adminToken && <p className="text-xs text-gray-600">Richiede admin token salvato.</p>}
      </section>

      <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-3">
        <h3 className="text-sm font-semibold text-white">Onboarding</h3>
        <button onClick={onValidate} disabled={!adminToken || saving} className="w-full rounded-lg bg-accent-blue px-3 py-2 text-sm font-semibold text-white disabled:opacity-40">
          {saving ? 'Checking...' : 'Validate'}
        </button>
        {validation && (
          <div className="grid grid-cols-2 gap-2">
            {validation.checks.map((check) => (
              <div key={check.name} className="rounded-lg bg-dark-900 px-3 py-2">
                <p className="text-xs font-semibold text-white">{check.name}</p>
                <p className={check.configured ? 'text-xs text-accent-green' : 'text-xs text-accent-red'}>{check.status}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-xl bg-dark-800 px-4 py-3">
        <p className="text-xs text-gray-500">Per indirizzi e posizioni aperte usa il tab <span className="text-accent-blue font-semibold">Wallet</span>.</p>
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">General</h3>
        <div className="grid grid-cols-2 gap-3">
          <SelectInput label="Mode" value={settings.mode} onChange={(mode) => patch({ mode })} options={[
            { value: 'conservative', label: 'Conservative' },
            { value: 'semi_autonomous', label: 'Semi-auto' },
            { value: 'full_autonomous', label: 'Full auto' },
          ]} />
          <SelectInput label="Market" value={settings.markets_enabled} onChange={(markets_enabled) => patch({ markets_enabled })} options={[
            { value: 'spot', label: 'Spot' },
            { value: 'perp', label: 'Perp' },
            { value: 'both', label: 'Both' },
          ]} />
          <SelectInput label="Execution" value={settings.execution_mode} onChange={(execution_mode) => patch({ execution_mode })} options={[
            { value: 'dry_run', label: 'Dry-run' },
            { value: 'live', label: 'Live' },
          ]} />
          <NumberInput label="Test scaling %" value={settings.test_scaling_pct} onChange={(test_scaling_pct) => patch({ test_scaling_pct })} />
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Filtri mercato</h3>
        <ToggleInput
          label="Filtro inversione mercato"
          checked={settings.market_reversal_filter_enabled}
          onChange={(market_reversal_filter_enabled) => patch({ market_reversal_filter_enabled })}
        />
        <ToggleInput
          label="Breakeven Spot"
          checked={settings.spot_breakeven_enabled}
          onChange={(spot_breakeven_enabled) => patch({ spot_breakeven_enabled })}
        />
        <SelectInput
          label="Modalità breakeven Spot"
          value={settings.spot_breakeven_mode}
          onChange={(v) => patch({ spot_breakeven_mode: v })}
          options={[
            { value: 'atr', label: 'ATR (attuale)' },
            { value: 'tp1', label: 'Solo dopo TP1' },
          ]}
        />
        <ToggleInput
          label="Breakeven Perp"
          checked={settings.perp_breakeven_enabled}
          onChange={(perp_breakeven_enabled) => patch({ perp_breakeven_enabled })}
        />
        <SelectInput
          label="Modalità breakeven Perp"
          value={settings.perp_breakeven_mode}
          onChange={(v) => patch({ perp_breakeven_mode: v })}
          options={[
            { value: 'atr', label: 'ATR (attuale)' },
            { value: 'tp1', label: 'Solo dopo TP1' },
          ]}
        />
        <SelectInput
          label="Stop Loss Spot"
          value={settings.spot_sl_mode}
          onChange={(v) => patch({ spot_sl_mode: v })}
          options={[
            { value: 'atr', label: 'ATR (attuale)' },
            { value: 'lowest', label: 'Minimo 20 candele' },
          ]}
        />
        <SelectInput
          label="Stop Loss Perp"
          value={settings.perp_sl_mode}
          onChange={(v) => patch({ perp_sl_mode: v })}
          options={[
            { value: 'atr', label: 'ATR (attuale)' },
            { value: 'lowest', label: 'Min/Max 20 candele' },
          ]}
        />
        <ToggleInput
          label="Trailing Stop Spot"
          checked={settings.spot_trailing_enabled}
          onChange={(spot_trailing_enabled) => patch({ spot_trailing_enabled })}
        />
        <ToggleInput
          label="Trailing Stop Perp"
          checked={settings.perp_trailing_enabled}
          onChange={(perp_trailing_enabled) => patch({ perp_trailing_enabled })}
        />
        <ToggleInput
          label="Time Stop Spot"
          checked={settings.spot_time_stop_enabled}
          onChange={(spot_time_stop_enabled) => patch({ spot_time_stop_enabled })}
        />
        <ToggleInput
          label="Time Stop Perp"
          checked={settings.perp_time_stop_enabled}
          onChange={(perp_time_stop_enabled) => patch({ perp_time_stop_enabled })}
        />
        <ToggleInput
          label="Filtro shock BTC perp"
          checked={settings.perp_trend_shock_enabled}
          onChange={(perp_trend_shock_enabled) => patch({ perp_trend_shock_enabled })}
        />
        {settings.perp_trend_shock_enabled && (
          <div className="grid grid-cols-2 gap-3">
            <NumberInput label="ADX threshold" value={settings.perp_trend_shock_adx_threshold} onChange={(perp_trend_shock_adx_threshold) => patch({ perp_trend_shock_adx_threshold })} />
            <NumberInput label="NATR percentile" value={settings.perp_trend_shock_natr_percentile} onChange={(perp_trend_shock_natr_percentile) => patch({ perp_trend_shock_natr_percentile })} />
            <NumberInput label="Volume threshold" value={settings.perp_trend_shock_volume_threshold} onChange={(perp_trend_shock_volume_threshold) => patch({ perp_trend_shock_volume_threshold })} />
            <NumberInput label="Recovery checks" value={settings.perp_trend_shock_recovery_confirmations} onChange={(perp_trend_shock_recovery_confirmations) => patch({ perp_trend_shock_recovery_confirmations })} />
          </div>
        )}
        <ToggleInput
          label="Smart Stop Loss Perp"
          checked={settings.perp_smart_sl_enabled}
          onChange={(perp_smart_sl_enabled) => patch({ perp_smart_sl_enabled })}
        />
        {settings.perp_smart_sl_enabled && (
          <div className="grid grid-cols-2 gap-3">
            <NumberInput label="L1 frac" value={settings.perp_smart_sl_l1_frac} step={0.01} onChange={(perp_smart_sl_l1_frac) => patch({ perp_smart_sl_l1_frac })} />
            <NumberInput label="L2 frac" value={settings.perp_smart_sl_l2_frac} step={0.01} onChange={(perp_smart_sl_l2_frac) => patch({ perp_smart_sl_l2_frac })} />
            <NumberInput label="Split L1 %" value={settings.perp_smart_sl_split_l1} step={0.01} onChange={(perp_smart_sl_split_l1) => patch({ perp_smart_sl_split_l1 })} />
            <NumberInput label="Split L2 %" value={settings.perp_smart_sl_split_l2} step={0.01} onChange={(perp_smart_sl_split_l2) => patch({ perp_smart_sl_split_l2 })} />
            <NumberInput label="Split L3 %" value={settings.perp_smart_sl_split_l3} step={0.01} onChange={(perp_smart_sl_split_l3) => patch({ perp_smart_sl_split_l3 })} />
            <SelectInput label="Rebuy mode" value={settings.perp_smart_sl_rebuy_mode} onChange={(v) => patch({
              perp_smart_sl_rebuy_mode: v,
              ...(v === 'above_entry' ? { perp_smart_sl_confirmation_candles: 2, perp_smart_sl_max_reentries: 1 } : { perp_smart_sl_confirmation_candles: 3, perp_smart_sl_max_reentries: 2 }),
            })} options={[
              { value: 'above_entry', label: 'Sopra entry' },
              { value: 'delta', label: 'Delta per livello' },
            ]} />
            {settings.perp_smart_sl_rebuy_mode === 'above_entry' && (
              <>
                <NumberInput label="Rebuy % venduto" value={settings.perp_smart_sl_rebuy_above_entry_pct} step={1} onChange={(perp_smart_sl_rebuy_above_entry_pct) => patch({ perp_smart_sl_rebuy_above_entry_pct })} />
                <NumberInput label="R2 Split L1 %" value={settings.perp_smart_sl_split_l1_r2} step={0.01} onChange={(perp_smart_sl_split_l1_r2) => patch({ perp_smart_sl_split_l1_r2 })} />
                <NumberInput label="R2 Split L2 %" value={settings.perp_smart_sl_split_l2_r2} step={0.01} onChange={(perp_smart_sl_split_l2_r2) => patch({ perp_smart_sl_split_l2_r2 })} />
                <NumberInput label="R2 Split L3 %" value={settings.perp_smart_sl_split_l3_r2} step={0.01} onChange={(perp_smart_sl_split_l3_r2) => patch({ perp_smart_sl_split_l3_r2 })} />
              </>
            )}
            {settings.perp_smart_sl_rebuy_mode === 'delta' && (
              <>
                <NumberInput label="Delta L1" value={settings.perp_smart_sl_delta_l1} step={0.01} onChange={(perp_smart_sl_delta_l1) => patch({ perp_smart_sl_delta_l1 })} />
                <NumberInput label="Delta L2" value={settings.perp_smart_sl_delta_l2} step={0.01} onChange={(perp_smart_sl_delta_l2) => patch({ perp_smart_sl_delta_l2 })} />
              </>
            )}
            <NumberInput label="Candele conferma SSL" value={settings.perp_smart_sl_confirmation_candles} step={1} onChange={(perp_smart_sl_confirmation_candles) => patch({ perp_smart_sl_confirmation_candles: Math.round(perp_smart_sl_confirmation_candles) })} />
            <NumberInput label="Max reentries" value={settings.perp_smart_sl_max_reentries} step={1} onChange={(perp_smart_sl_max_reentries) => patch({ perp_smart_sl_max_reentries: Math.round(perp_smart_sl_max_reentries) })} />
            <ToggleInput label="Adegua TP dopo rebuy" checked={settings.perp_smart_sl_tp_adjust_after_rebuy} onChange={(perp_smart_sl_tp_adjust_after_rebuy) => patch({ perp_smart_sl_tp_adjust_after_rebuy })} />
            {settings.perp_smart_sl_tp_adjust_after_rebuy && (
              <NumberInput label="Delta recovery TP %" value={settings.perp_smart_sl_tp_recovery_delta_pct} step={1} onChange={(perp_smart_sl_tp_recovery_delta_pct) => patch({ perp_smart_sl_tp_recovery_delta_pct })} />
            )}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Risk globale</h3>
        <ToggleInput
          label="Allarme drawdown"
          checked={settings.drawdown_alert_enabled}
          onChange={(drawdown_alert_enabled) => patch({ drawdown_alert_enabled })}
        />
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Daily loss %" value={settings.daily_loss_limit_pct} onChange={(daily_loss_limit_pct) => patch({ daily_loss_limit_pct })} />
          <NumberInput label="Drawdown cap %" value={settings.drawdown_cap_pct} onChange={(drawdown_cap_pct) => patch({ drawdown_cap_pct })} />
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Grafico trade</h3>
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Candele post-chiusura (0=off)" value={settings.post_close_candles} step={1} onChange={(post_close_candles) => patch({ post_close_candles: Math.round(post_close_candles) })} />
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Spot — risk</h3>
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Size %" value={settings.spot_capital_per_trade_pct} onChange={(spot_capital_per_trade_pct) => patch({ spot_capital_per_trade_pct })} />
          <NumberInput label="Rischio %" value={settings.spot_per_trade_pct} step={0.1} onChange={(spot_per_trade_pct) => patch({ spot_per_trade_pct })} />
          <NumberInput label="Max posizioni" value={settings.spot_max_open_positions} onChange={(spot_max_open_positions) => patch({ spot_max_open_positions })} />
          <NumberInput label="Exposure %" value={settings.spot_max_exposure_pct} onChange={(spot_max_exposure_pct) => patch({ spot_max_exposure_pct })} />
          <NumberInput label="Slippage %" value={settings.spot_max_slippage_pct} step={0.1} onChange={(spot_max_slippage_pct) => patch({ spot_max_slippage_pct })} />
          <NumberInput label="Cooldown min" value={settings.spot_cooldown_minutes} onChange={(spot_cooldown_minutes) => patch({ spot_cooldown_minutes })} />
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Spot — strategia</h3>
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Confidence" value={settings.spot_confidence_threshold} step={0.01} onChange={(spot_confidence_threshold) => patch({ spot_confidence_threshold })} />
          <NumberInput label="Vol trigger %" value={settings.spot_volatility_trigger_pct} onChange={(spot_volatility_trigger_pct) => patch({ spot_volatility_trigger_pct })} />
          <NumberInput label="Rel volume" value={settings.spot_relative_volume_threshold} step={0.1} onChange={(spot_relative_volume_threshold) => patch({ spot_relative_volume_threshold })} />
          <NumberInput label="ATR stop" value={settings.spot_atr_stop_multiplier} step={0.1} onChange={(spot_atr_stop_multiplier) => patch({ spot_atr_stop_multiplier })} />
          <NumberInput label="Buffer Min20 %" value={settings.spot_structural_stop_buffer_pct} step={0.1} onChange={(spot_structural_stop_buffer_pct) => patch({ spot_structural_stop_buffer_pct })} />
          <NumberInput label="Chiudi a TP1 %" value={settings.spot_tp1_close_pct} step={5} onChange={(spot_tp1_close_pct) => patch({ spot_tp1_close_pct })} />
          <NumberInput label="Time Stop ore" value={settings.spot_time_stop_hours} step={1} onChange={(spot_time_stop_hours) => patch({ spot_time_stop_hours: Math.round(spot_time_stop_hours) })} />
          <SelectInput label="Fee mode (dry-run)" value={settings.spot_fee_mode} onChange={(v) => patch({ spot_fee_mode: v as 'all' | 'none' })} options={[
            { value: 'all', label: 'Swap fee + Slippage — 0.15%' },
            { value: 'none', label: 'Nessuna (strategia lorda)' },
          ]} />
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Perp — risk</h3>
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Size % (margine)" value={settings.perp_capital_per_trade_pct} onChange={(perp_capital_per_trade_pct) => patch({ perp_capital_per_trade_pct })} />
          <NumberInput label="Rischio %" value={settings.perp_per_trade_pct} step={0.1} onChange={(perp_per_trade_pct) => patch({ perp_per_trade_pct })} />
          <NumberInput label="Max posizioni" value={settings.perp_max_open_positions} onChange={(perp_max_open_positions) => patch({ perp_max_open_positions })} />
          <NumberInput label="Exposure %" value={settings.perp_max_exposure_pct} onChange={(perp_max_exposure_pct) => patch({ perp_max_exposure_pct })} />
          <NumberInput label="Slippage %" value={settings.perp_max_slippage_pct} step={0.1} onChange={(perp_max_slippage_pct) => patch({ perp_max_slippage_pct })} />
          <NumberInput label="Cooldown min" value={settings.perp_cooldown_minutes} onChange={(perp_cooldown_minutes) => patch({ perp_cooldown_minutes })} />
          <ToggleInput label="Margine fisso Perp" checked={settings.perp_fixed_margin_enabled} onChange={(perp_fixed_margin_enabled) => patch({ perp_fixed_margin_enabled })} />
          <NumberInput label="Margine fisso $" value={settings.perp_fixed_margin_usd} onChange={(perp_fixed_margin_usd) => patch({ perp_fixed_margin_usd })} />
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Perp — strategia</h3>
        <div className="grid grid-cols-2 gap-3">
          <SelectInput label="Direction" value={settings.perp_direction_mode} onChange={(perp_direction_mode) => patch({ perp_direction_mode })} options={[
            { value: 'long_only', label: 'Long' },
            { value: 'short_only', label: 'Short' },
            { value: 'long_short', label: 'Both' },
          ]} />
          <NumberInput label="Leva min (alta vol.)" value={settings.perp_min_leverage} onChange={(perp_min_leverage) => patch({ perp_min_leverage })} />
          <NumberInput label="Leva max (bassa vol.)" value={settings.perp_max_leverage} onChange={(perp_max_leverage) => patch({ perp_max_leverage })} />
          <NumberInput label="Value area %" value={settings.perp_value_area_pct} onChange={(perp_value_area_pct) => patch({ perp_value_area_pct })} />
          <NumberInput label="ATR stop" value={settings.perp_atr_stop_multiplier} step={0.1} onChange={(perp_atr_stop_multiplier) => patch({ perp_atr_stop_multiplier })} />
          <NumberInput label="Buffer Min/Max20 %" value={settings.perp_structural_stop_buffer_pct} step={0.1} onChange={(perp_structural_stop_buffer_pct) => patch({ perp_structural_stop_buffer_pct })} />
          <SelectInput label="Trailing ATR (adatta alla leva)" value={settings.perp_trailing_mode} onChange={(v) => patch({ perp_trailing_mode: v as 'largo' | 'stretto' })} options={[
            { value: 'largo', label: 'Largo — lascia correre' },
            { value: 'stretto', label: 'Stretto — blocca prima' },
          ]} />
          <NumberInput label="Trailing dist. % (0=solo ATR)" value={settings.perp_trailing_pnl_pct} step={0.1} onChange={(perp_trailing_pnl_pct) => patch({ perp_trailing_pnl_pct })} />
          <NumberInput label="Chiudi a TP1 %" value={settings.perp_tp1_close_pct} step={5} onChange={(perp_tp1_close_pct) => patch({ perp_tp1_close_pct })} />
          <NumberInput label="Time Stop ore" value={settings.perp_time_stop_hours} step={1} onChange={(perp_time_stop_hours) => patch({ perp_time_stop_hours: Math.round(perp_time_stop_hours) })} />
          <SelectInput label="Fee mode (dry-run)" value={settings.perp_fee_mode} onChange={(v) => patch({ perp_fee_mode: v as 'taker' | 'maker' | 'none' })} options={[
            { value: 'taker', label: 'Taker (market) — 0.06%' },
            { value: 'maker', label: 'Maker (limit) — 0.02%' },
            { value: 'none', label: 'Nessuna (strategia lorda)' },
          ]} />
        </div>
        <p className="px-1 text-xs text-gray-500">
          Leva modulata sulla volatilità ATR(72) in apertura: bassa volatilità → leva max, alta volatilità → leva min. Volatilità anomala (oltre il massimo storico) → leva forzata al minimo. Range 1–50.
        </p>
      </section>

      <button onClick={onSave} disabled={!adminToken || saving} className="w-full rounded-lg bg-accent-blue px-3 py-3 text-sm font-semibold text-white disabled:opacity-40">
        {saving ? 'Saving...' : 'Save agent settings'}
      </button>
      {actionError && <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{actionError}</p>}
    </div>
  );
};

const TradeCandleChart: FC<{ chart: NonNullable<TradeDetail['chart']> }> = ({ chart }) => {
  const candles = chart.candles ?? [];
  const postClose = chart.post_close_candles ?? [];
  const allCandles = [...candles, ...postClose];
  if (allCandles.length < 2) {
    return <p className="text-xs text-gray-500">Grafico non disponibile per questo trade.</p>;
  }
  // Geometria: area di plot + margine destro per i prezzi (Y) e inferiore per gli orari (X).
  const W = Math.max(340, allCandles.length * 8 + 58);
  const H = 200;
  const padX = 6;
  const padTop = 10;
  const axisW = 46;
  const axisH = 16;
  const plotR = W - axisW;
  const plotB = H - axisH;
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
  const y = (price: number) => padTop + (1 - (price - lo) / range) * (plotB - padTop);
  const colW = (plotR - padX) / allCandles.length;
  const cx = (i: number) => padX + colW * (i + 0.5);

  // Marker temporali: candela piu' vicina ad apertura/chiusura sull'intero grafico.
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

  // Etichette asse Y (prezzo).
  const fmtAxisPrice = (p: number) => {
    if (p >= 1000) return p.toFixed(0);
    if (p >= 1) return p.toFixed(2);
    if (p >= 0.01) return p.toFixed(4);
    return p.toPrecision(3);
  };
  const yTicks = [0, 1, 2, 3, 4].map((k) => lo + (range * k) / 4);

  // Etichette asse X (orario).
  const spanMs = ts(allCandles[allCandles.length - 1].t) - ts(allCandles[0].t);
  const fmtAxisTime = (iso: string) => {
    const d = new Date(iso);
    return spanMs > 24 * 3600 * 1000
      ? d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' })
      : d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  };
  const last = allCandles.length - 1;
  const xTickIdx = [0, Math.round(last / 3), Math.round((2 * last) / 3), last];

  const levelLine = (price: number | null, color: string, dash: string) =>
    price == null || Number.isNaN(price) ? null : (
      <line x1={padX} x2={plotR} y1={y(price)} y2={y(price)} stroke={color} strokeWidth="1" strokeDasharray={dash} opacity="0.7" />
    );

  const stopRefLine = (idx: number) => {
    const candle = allCandles[idx];
    if (!candle) return null;
    const gap = 3;
    const x = cx(idx);
    const topEnd = Math.max(padTop, y(candle.h) - gap);
    const bottomStart = Math.min(plotB, y(candle.l) + gap);
    return (
      <>
        {topEnd > padTop && (
          <line x1={x} x2={x} y1={padTop} y2={topEnd} stroke="#a855f7" strokeWidth="1" strokeDasharray="2 2" opacity="0.9" />
        )}
        {bottomStart < plotB && (
          <line x1={x} x2={x} y1={bottomStart} y2={plotB} stroke="#a855f7" strokeWidth="1" strokeDasharray="2 2" opacity="0.9" />
        )}
      </>
    );
  };

  // Linea verticale tratteggiata subito dopo la candela di chiusura.
  const closeLineX = postClose.length > 0 ? cx(exitIdx + 0.5) : null;

  return (
    <div className="overflow-x-auto pb-1">
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: `${W}px`, minWidth: '100%', height: 'auto' }}>
      {/* griglia + etichette asse Y */}
      {yTicks.map((p, k) => (
        <g key={`yt${k}`}>
          <line x1={padX} x2={plotR} y1={y(p)} y2={y(p)} stroke="#1f2937" strokeWidth="0.5" opacity="0.6" />
          <text x={plotR + 4} y={y(p)} fontSize="8" fill="#6b7280" dominantBaseline="middle">{fmtAxisPrice(p)}</text>
        </g>
      ))}
      {/* assi */}
      <line x1={plotR} x2={plotR} y1={padTop} y2={plotB} stroke="#374151" strokeWidth="0.5" />
      <line x1={padX} x2={plotR} y1={plotB} y2={plotB} stroke="#374151" strokeWidth="0.5" />
      {/* etichette asse X */}
      {xTickIdx.map((i, k) => (
        <text
          key={`xt${k}`}
          x={cx(i)}
          y={H - 4}
          fontSize="8"
          fill="#6b7280"
          textAnchor={k === 0 ? 'start' : k === xTickIdx.length - 1 ? 'end' : 'middle'}
        >
          {fmtAxisTime(allCandles[i].t)}
        </text>
      ))}
      {/* sfondo post-close */}
      {closeLineX != null && (
        <rect x={closeLineX} y={padTop} width={plotR - closeLineX} height={plotB - padTop} fill="#111827" opacity="0.4" />
      )}
      {/* Candles outside the active trade window are contextual and muted. */}
      {allCandles.map((c, i) => {
        const isPost = i >= candles.length;
        const isPreEntry = i < entryIdx;
        const up = c.c >= c.o;
        const color = isPost ? (up ? '#166534' : '#7f1d1d') : (up ? '#22c55e' : '#ef4444');
        const opacity = isPost || isPreEntry ? 0.55 : 1;
        const bodyTop = y(Math.max(c.o, c.c));
        const bodyBot = y(Math.min(c.o, c.c));
        const bw = Math.max(1, colW * 0.6);
        return (
          <g key={i} opacity={opacity}>
            <line x1={cx(i)} x2={cx(i)} y1={y(c.h)} y2={y(c.l)} stroke={color} strokeWidth="1" />
            <rect x={cx(i) - bw / 2} y={bodyTop} width={bw} height={Math.max(1, bodyBot - bodyTop)} fill={color} />
          </g>
        );
      })}
      {/* linea verticale tratteggiata di chiusura */}
      {closeLineX != null && (
        <line x1={closeLineX} x2={closeLineX} y1={padTop} y2={plotB} stroke="#6b7280" strokeWidth="1" strokeDasharray="3 2" opacity="0.8" />
      )}
      {stopRefIdx != null && (
        <>
          {stopRefLine(stopRefIdx)}
          <text x={Math.min(plotR - 4, cx(stopRefIdx) + 4)} y={padTop + 8} fontSize="8" fill="#c084fc">SL ref</text>
          {stopRefPrice != null && !Number.isNaN(stopRefPrice) && (
            <circle cx={cx(stopRefIdx)} cy={y(stopRefPrice)} r="3" fill="#a855f7" stroke="#0b0e11" strokeWidth="1" />
          )}
        </>
      )}
      {levelLine(sl, '#ef4444', '4 3')}
      {levelLine(tp1, '#22c55e', '4 3')}
      {levelLine(tp2, '#16a34a', '2 3')}
      {levelLine(entry, '#9ca3af', '1 0')}
      {/* marker ingresso/uscita */}
      <circle cx={cx(entryIdx)} cy={y(entry)} r="3.5" fill="#e5e7eb" stroke="#0b0e11" strokeWidth="1" />
      <circle cx={cx(exitIdx)} cy={y(exit)} r="3.5" fill={exitGood ? '#22c55e' : '#ef4444'} stroke="#0b0e11" strokeWidth="1" />
    </svg>
    </div>
  );
};

const TradeDetailScreen: FC<{ detail: TradeDetail; onBack: () => void }> = ({ detail, onBack }) => (
  <div className="space-y-4">
    <button onClick={onBack} className="rounded-lg bg-dark-800 px-3 py-2 text-sm font-semibold text-gray-300">
      Back
    </button>
    {detail.is_smart_sl ? (
      /* ── Vista dedicata per trade Smart SL (no grafico) ── */
      <section className="rounded-xl bg-dark-800 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-bold text-white">{detail.asset}</h3>
            <p className="text-xs text-gray-500">{detail.market} / {detail.direction}</p>
          </div>
          <span className={`rounded-full px-2 py-1 text-xs font-semibold ${detail.ssl_action === 'sell' ? 'bg-amber-500/15 text-amber-400' : 'bg-sky-500/15 text-sky-400'}`}>
            Smart SL {detail.ssl_action === 'sell' ? 'Sell' : 'Rebuy'} L{detail.ssl_level}
          </span>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <Stat label="Azione" value={detail.ssl_action === 'sell' ? 'Vendita parziale' : 'Riacquisto'} />
          <Stat label="Livello" value={`L${detail.ssl_level}`} />
          <Stat label="Prezzo esecuzione" value={fmtPriceFull(detail.current_or_exit_price)} />
          <Stat label="Size" value={detail.size} />
          <Stat label="Entry originale" value={fmtPriceFull(detail.original_entry_price ?? detail.entry_price)} />
          {detail.current_position_entry_price && detail.current_position_entry_price !== (detail.original_entry_price ?? detail.entry_price) && (
            <Stat label="Entry corrente" value={fmtPriceFull(detail.current_position_entry_price)} />
          )}
          <Stat label="Leverage" value={detail.leverage ? `${detail.leverage.toFixed(2)}x` : '-'} />
          {detail.ssl_action === 'sell' && (
            <Stat label="PnL parziale" value={`${detail.pnl_usd} / ${detail.pnl_pct}%`} tone={Number(detail.pnl_usd) >= 0 ? 'good' : 'bad'} />
          )}
          <Stat label="Exposure" value={fmtUsd(detail.exposure_usd)} />
        </div>
      </section>
    ) : (
      /* ── Vista normale con grafico ── */
      <>
        {detail.chart && (
          <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">{detail.chart.live ? 'Grafico posizione (live)' : 'Grafico del trade'}</h3>
              <span className="text-xs text-gray-500">{detail.chart.interval}</span>
            </div>
            <TradeCandleChart chart={detail.chart} />
            <div className="flex flex-wrap gap-3 text-[10px] text-gray-400">
              <span>⚪ Entry</span>
              <span className={Number(detail.chart.exit_price) >= Number(detail.chart.entry_price) ? 'text-accent-green' : 'text-accent-red'}>● {detail.chart.live ? 'Ora' : 'Exit'}</span>
              <span className="text-accent-red">- - SL</span>
              {detail.chart.stop_reference && <span className="text-purple-300">- - SL ref</span>}
              <span className="text-accent-green">- - TP</span>
            </div>
          </section>
        )}
        <section className="rounded-xl bg-dark-800 px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-bold text-white">{detail.asset}</h3>
              <p className="text-xs text-gray-500">{detail.market} / {detail.direction}</p>
            </div>
            <span className={detail.is_simulated ? 'rounded-full bg-accent-yellow/15 px-2 py-1 text-xs text-accent-yellow' : 'rounded-full bg-accent-green/15 px-2 py-1 text-xs text-accent-green'}>
              {detail.is_simulated ? 'dry-run' : 'live'}
            </span>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <Stat label="PnL" value={`${detail.pnl_usd} / ${detail.pnl_pct}%`} tone={Number(detail.pnl_usd) >= 0 ? 'good' : 'bad'} />
            <Stat label="Exposure" value={fmtUsd(detail.exposure_usd)} />
            <Stat label="Entry" value={fmtPriceFull(detail.entry_price)} />
            <Stat label="Now/Exit" value={fmtPriceFull(detail.current_or_exit_price)} />
            <Stat label="Size" value={detail.size} />
            <Stat label="Leverage" value={detail.leverage ? `${detail.leverage.toFixed(2)}x` : '-'} />
          </div>
          {detail.fee_mode && (
            <>
              <div className="mt-3 flex items-center gap-2">
                <span className="text-xs font-semibold uppercase text-gray-500">Costi posizione</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${detail.fee_mode === 'none' ? 'bg-gray-700 text-gray-300' : detail.fee_mode === 'maker' ? 'bg-accent-green/15 text-accent-green' : 'bg-accent-yellow/15 text-accent-yellow'}`}>
                  {detail.fee_mode === 'none' ? 'Nessuna fee' : detail.fee_mode === 'maker' ? 'Maker (limit)' : detail.fee_mode === 'all' ? 'Swap + Slippage' : 'Taker (market)'}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {detail.margin_usd != null && <Stat label="Margine" value={fmtUsd(detail.margin_usd)} />}
                {detail.opening_fee_usd != null && <Stat label="Fee applicata" value={fmtUsd(detail.opening_fee_usd)} tone="bad" />}
                {detail.taker_fee_usd != null && <Stat label="Fee taker (0.06%)" value={fmtUsd(detail.taker_fee_usd)} />}
                {detail.maker_fee_usd != null && <Stat label="Fee maker (0.02%)" value={fmtUsd(detail.maker_fee_usd)} />}
                {detail.funding_accrued_usd != null && <Stat label="Funding maturato" value={fmtUsd(detail.funding_accrued_usd)} tone={Number(detail.funding_accrued_usd) >= 0 ? 'good' : 'bad'} />}
                {detail.funding_rate_8h != null && <Stat label="Funding rate (8h)" value={`${(Number(detail.funding_rate_8h) * 100).toFixed(4)}%`} />}
                {detail.swap_fee_usd != null && <Stat label="Swap fee (0.05%)" value={fmtUsd(detail.swap_fee_usd)} tone="bad" />}
                {detail.gas_cost_bnb != null && <Stat label="Gas (BNB)" value={Number(detail.gas_cost_bnb).toFixed(6)} />}
                {detail.slippage_usd != null && Number(detail.slippage_usd) > 0 && <Stat label="Slippage" value={fmtUsd(detail.slippage_usd)} tone="bad" />}
              </div>
            </>
          )}
        </section>
        <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-2">
          <h3 className="text-sm font-semibold text-white">Risk levels</h3>
          {[
            ['Stop loss', detail.stop_loss],
            ...(detail.market === 'perp' ? [[
              detail.stop_reference_field === 'high' ? 'Max candela ref SL' : 'Min candela ref SL',
              detail.stop_reference_price,
            ] as [string, string | null | undefined]] : []),
            ...(detail.market === 'perp' ? [['Liquidation', detail.liquidation_price] as [string, string | null | undefined]] : []),
            ['Breakeven', detail.breakeven_price],
            ['Take profit 1', detail.take_profit_1],
            ['Take profit 2', detail.take_profit_2],
            ['Trailing stop', detail.trailing_stop],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between rounded-lg bg-dark-900 px-3 py-2 text-xs">
              <span className="text-gray-500">{label}</span>
              <span className={value ? 'text-white' : 'text-gray-600'}>
                {value ? fmtPriceFull(value) : (label === 'Trailing stop' ? 'Non attivo' : '---')}
              </span>
            </div>
          ))}
        </section>
      </>
    )}
    {detail.market === 'perp' && detail.smart_sl_levels && (
      <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">Smart Stop Loss</h3>
          {detail.smart_sl_protection_suspended && (
            <span className="rounded-full bg-amber-500/15 px-2 py-1 text-xs font-semibold text-amber-400">BE/Trail sospesi</span>
          )}
          {detail.smart_sl_reentries_exhausted && (
            <span className="rounded-full bg-red-500/15 px-2 py-1 text-xs font-semibold text-red-400">Reentries esauriti</span>
          )}
        </div>
        {detail.smart_sl_levels.map((price, idx) => {
          const stateInfo = detail.smart_sl_state_summary?.[idx];
          const statusLabel = stateInfo?.status === 'sold' ? 'Venduto' : stateInfo?.status === 'rebought' ? 'Ricomprato' : idx === 2 ? 'Classico SL' : 'In attesa';
          const statusColor = stateInfo?.status === 'sold' ? 'text-amber-400' : stateInfo?.status === 'rebought' ? 'text-sky-400' : 'text-gray-500';
          return (
            <div key={idx} className="rounded-lg bg-dark-900 px-3 py-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-gray-500">L{idx + 1} ({idx === 0 ? '25%' : idx === 1 ? '55%' : '20%'})</span>
                <span className="flex items-center gap-2">
                  <span className={statusColor}>{statusLabel}{stateInfo && stateInfo.reentries > 0 ? ` (${stateInfo.reentries}x)` : ''}</span>
                  <span className="text-white">{fmtPriceFull(price)}</span>
                </span>
              </div>
              {stateInfo?.fill_price && (
                <div className="mt-1 flex items-center justify-between text-amber-400/80">
                  <span>Fill vendita</span>
                  <span className="font-semibold">{fmtPriceFull(stateInfo.fill_price)}</span>
                </div>
              )}
              {stateInfo?.rebuy_fill_price && (
                <div className="mt-1 flex items-center justify-between text-sky-400/80">
                  <span>Fill rebuy</span>
                  <span className="font-semibold">{fmtPriceFull(stateInfo.rebuy_fill_price)}</span>
                </div>
              )}
            </div>
          );
        })}
        {(detail.smart_sl_original_tp1 || detail.smart_sl_original_tp2) && (
          <div className="rounded-lg bg-dark-900 px-3 py-2 text-xs space-y-1">
            <span className="text-gray-500 font-semibold">TP adeguati dopo rebuy</span>
            {detail.smart_sl_original_tp1 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">TP1 originale</span>
                <span className="text-gray-400 line-through">{fmtPriceFull(detail.smart_sl_original_tp1)}</span>
              </div>
            )}
            {detail.take_profit_1 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">TP1 nuovo</span>
                <span className="text-emerald-400 font-semibold">{fmtPriceFull(detail.take_profit_1)}</span>
              </div>
            )}
            {detail.smart_sl_original_tp2 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">TP2 originale</span>
                <span className="text-gray-400 line-through">{fmtPriceFull(detail.smart_sl_original_tp2)}</span>
              </div>
            )}
            {detail.take_profit_2 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">TP2 nuovo</span>
                <span className="text-emerald-400 font-semibold">{fmtPriceFull(detail.take_profit_2)}</span>
              </div>
            )}
          </div>
        )}
      </section>
    )}
    <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-2">
      <h3 className="text-sm font-semibold text-white">Timeline</h3>
      <p className="text-xs text-gray-500">Open {new Date(detail.opened_at).toLocaleString('it-IT')}</p>
      <p className="text-xs text-gray-500">Close {detail.closed_at ? new Date(detail.closed_at).toLocaleString('it-IT') : '-'}</p>
      <p className="text-xs text-gray-500">Reason {detail.close_reason ? (CLOSE_REASON_LABELS[detail.close_reason]?.label ?? detail.close_reason) : '-'}</p>
    </section>
  </div>
);

interface AgentTabProps {
  adminToken: string;
  onAdminToken: (value: string) => void;
  eligibleTokens: string[];
  selectedAiSymbols: Set<string>;
  watchlistSaving: boolean;
  watchlistError: string;
  onToggleAiSymbol: (symbol: string) => void;
}

// Cache a livello di modulo: conserva l'ultimo stato dell'agente tra unmount/mount
// (es. quando si cambia tab e si torna). Al rientro lo stato si inizializza con gli
// ultimi valori noti e l'aggiornamento avviene in silenzio, invece di mostrare i
// valori a 0 durante il primo fetch.
const agentCache: {
  pane: AgentPane;
  status: AgentStatus | null;
  spot: SpotView | null;
  perp: PerpView | null;
  global: GlobalView | null;
  equity: EquityCurveResponse | null;
  equityRange: EquityRange;
  decisions: AgentDecisionResponse | null;
  assetBreakdown: AssetBreakdownResponse | null;
  settings: AgentMobileSettings | null;
  execWallets: ExecutionWalletsResponse | null;
  claudeUsage: ClaudeUsageView | null;
  loaded: boolean;
} = {
  pane: 'spot', status: null, spot: null, perp: null, global: null, equity: null,
  equityRange: '24h', decisions: null, assetBreakdown: null, settings: null,
  execWallets: null, claudeUsage: null, loaded: false,
};

const AgentTab: FC<AgentTabProps> = ({
  adminToken,
  onAdminToken,
  eligibleTokens,
  selectedAiSymbols,
  watchlistSaving,
  watchlistError,
  onToggleAiSymbol,
}) => {
  const [pane, setPane] = useState<AgentPane>(agentCache.pane);
  const [status, setStatus] = useState<AgentStatus | null>(agentCache.status);
  const [spot, setSpot] = useState<SpotView | null>(agentCache.spot);
  const [perp, setPerp] = useState<PerpView | null>(agentCache.perp);
  const [global, setGlobal] = useState<GlobalView | null>(agentCache.global);
  const [equity, setEquity] = useState<EquityCurveResponse | null>(agentCache.equity);
  const [equityRange, setEquityRange] = useState<EquityRange>(agentCache.equityRange);
  const equityRangeRef = useRef<EquityRange>(equityRange);
  equityRangeRef.current = equityRange;
  const [decisions, setDecisions] = useState<AgentDecisionResponse | null>(agentCache.decisions);
  const [assetBreakdown, setAssetBreakdown] = useState<AssetBreakdownResponse | null>(agentCache.assetBreakdown);
  const [tradeDetail, setTradeDetail] = useState<TradeDetail | null>(null);
  const detailTradeIdRef = useRef<string | null>(null);
  const [settings, setSettings] = useState<AgentMobileSettings>(agentCache.settings ?? defaultSettings);
  const [execWallets, setExecWallets] = useState<ExecutionWalletsResponse | null>(agentCache.execWallets);
  const [claudeUsage, setClaudeUsage] = useState<ClaudeUsageView | null>(agentCache.claudeUsage);
  const [validation, setValidation] = useState<CredentialValidationResponse | null>(null);
  const [refreshing, setRefreshing] = useState(!agentCache.loaded);
  const [justSynced, setJustSynced] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const refreshInFlightRef = useRef(false);
  const fastRefreshInFlightRef = useRef(false);

  const loadActiveTradeDetail = useCallback(async (tradeId: string, enrichChart = false) => {
    const cached = getCachedTradeDetail(tradeId);
    if (cached && (!enrichChart || hasCompleteTradeChart(cached))) {
      if (detailTradeIdRef.current === tradeId) setTradeDetail(cached);
      return cached;
    }
    const detail = await fetchTradeDetailDeduped(tradeId, {
      enrichChart,
      timeoutMs: enrichChart ? TRADE_DETAIL_ENRICH_TIMEOUT_MS : TRADE_DETAIL_BASE_TIMEOUT_MS,
    });
    if (detailTradeIdRef.current === tradeId) {
      setTradeDetail(detail);
    }
    return detail;
  }, []);

  const prefetchTradeDetails = useCallback((tradeIds: Array<string | null | undefined>) => {
    const activeTradeId = detailTradeIdRef.current;
    const ids = Array.from(new Set(tradeIds.filter((id): id is string => Boolean(id))))
      .filter((id) => id !== activeTradeId && shouldPrefetchTradeDetail(id));
    if (ids.length === 0) return;

    const queue = [...ids];
    const nextRetryAt = Date.now() + TRADE_DETAIL_PREFETCH_RETRY_MS;
    ids.forEach((tradeId) => tradeDetailPrefetchRetryAt.set(tradeId, nextRetryAt));

    const workers = Array.from(
      { length: Math.min(TRADE_DETAIL_PREFETCH_CONCURRENCY, queue.length) },
      async () => {
        while (queue.length > 0) {
          const tradeId = queue.shift();
          if (!tradeId) return;
          try {
            let detail = getCachedTradeDetail(tradeId);
            if (!detail) {
              detail = await fetchTradeDetailDeduped(tradeId, { timeoutMs: TRADE_DETAIL_BASE_TIMEOUT_MS });
            }
          } catch {
            // Background warm-up: the tap handler still owns visible error handling.
          }
        }
      },
    );

    Promise.allSettled(workers).catch(() => {});
  }, []);

  const closeTradeDetail = useCallback(() => {
    detailTradeIdRef.current = null;
    setLoadingDetail(false);
    setTradeDetail(null);
  }, []);

  const refresh = useCallback(async (silent = false) => {
    if (refreshInFlightRef.current) return;
    if (fastRefreshInFlightRef.current) return;
    refreshInFlightRef.current = true;
    if (!silent) setRefreshing(true);
    try {
      // Caricamento progressivo: ogni scheda si popola appena la sua chiamata risponde,
      // senza aspettare la piu' lenta. I dati precedenti restano visibili nel frattempo.
      const activeTradeId = detailTradeIdRef.current;
      const detailFetch = activeTradeId && !hasCompleteCachedTradeDetail(activeTradeId)
        ? loadActiveTradeDetail(activeTradeId, true).catch(() => {})
        : Promise.resolve();
      const results = await Promise.allSettled([
        fetchAgentStatus().then(setStatus),
        fetchSpotView().then(setSpot),
        fetchPerpView().then(setPerp),
        fetchGlobalView().then(setGlobal),
        fetchAgentSettings().then((r) => setSettings(r.settings)),
        fetchEquityCurve(equityRangeRef.current).then(setEquity),
        fetchAgentDecisions().then(setDecisions),
        fetchAssetBreakdown().then(setAssetBreakdown),
        detailFetch,
      ]);
      const failed = results.filter((r) => r.status === 'rejected').length;
      setError(failed > 0 ? `${failed} endpoint non raggiungibili` : '');
      if (!silent) {
        setJustSynced(true);
        window.setTimeout(() => setJustSynced(false), 2500);
      }
    } finally {
      setRefreshing(false);
      refreshInFlightRef.current = false;
    }
  }, [loadActiveTradeDetail]);

  // Mirror dello stato nella cache di modulo: al prossimo mount (rientro nella tab)
  // i valori vengono ripristinati senza azzeramenti.
  useEffect(() => {
    agentCache.pane = pane;
    agentCache.status = status;
    agentCache.spot = spot;
    agentCache.perp = perp;
    agentCache.global = global;
    agentCache.equity = equity;
    agentCache.equityRange = equityRange;
    agentCache.decisions = decisions;
    agentCache.assetBreakdown = assetBreakdown;
    agentCache.settings = settings;
    agentCache.execWallets = execWallets;
    agentCache.claudeUsage = claudeUsage;
    if (status || spot || perp || global || equity) agentCache.loaded = true;
  }, [pane, status, spot, perp, global, equity, equityRange, decisions, assetBreakdown, settings, execWallets, claudeUsage]);

  useEffect(() => {
    // Al primo mount in assoluto mostra l'indicatore; ai rientri (cache popolata)
    // aggiorna in silenzio mantenendo i valori precedenti.
    refresh(agentCache.loaded);
  }, [refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      refresh();
    }, AGENT_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  // Refresh leggero: aggiorna solo le viste principali e salta se un ciclo e' gia' in corso.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (refreshInFlightRef.current) return;
      if (fastRefreshInFlightRef.current) return;
      fastRefreshInFlightRef.current = true;
      Promise.allSettled([
        fetchSpotView().then(setSpot),
        fetchPerpView().then(setPerp),
        fetchGlobalView().then(setGlobal),
      ]).finally(() => {
        fastRefreshInFlightRef.current = false;
      });
    }, AGENT_FAST_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (pane !== 'wallet') return;
    let active = true;
    const loadWallets = () => {
      fetchExecutionWallets()
        .then((value) => { if (active) setExecWallets(value); })
        .catch(() => {});
    };
    loadWallets();
    const timer = window.setInterval(loadWallets, 300_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [pane]);

  useEffect(() => {
    if (spot) {
      prefetchTradeDetails([
        ...spot.open_positions.map((position) => position.open_trade_id),
        ...spot.history.slice(0, TRADE_DETAIL_PREFETCH_LIMIT).map((trade) => trade.trade_id),
      ]);
    }
    if (perp) {
      prefetchTradeDetails([
        ...perp.open_positions.map((position) => position.open_trade_id),
        ...perp.history.slice(0, TRADE_DETAIL_PREFETCH_LIMIT).map((trade) => trade.trade_id),
      ]);
    }
  }, [spot, perp, prefetchTradeDetails]);

  // Refetch immediato della curva quando l'utente cambia il range (24h/7g/Tutto),
  // senza ricaricare tutte le altre schede.
  useEffect(() => {
    fetchEquityCurve(equityRange).then(setEquity).catch(() => {});
  }, [equityRange]);

  // Spesa API Claude: la carichiamo SOLO quando il pane Global e' attivo e con
  // cadenza ridotta (non cambia di secondo in secondo). Cosi' non appesantisce
  // gli altri pane ne' il refresh principale.
  useEffect(() => {
    if (pane !== 'global') return;
    let active = true;
    const load = () => { fetchClaudeUsage().then((v) => { if (active) setClaudeUsage(v); }).catch(() => {}); };
    load();
    const timer = window.setInterval(load, 300_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [pane]);

  const handleSave = async () => {
    setSaving(true);
    setActionError('');
    try {
      const response = await saveAgentSettings(settings, adminToken);
      setSettings(response.settings);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleValidate = async () => {
    setSaving(true);
    setActionError('');
    try {
      setValidation(await validateOnboarding(adminToken));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Validation failed');
    } finally {
      setSaving(false);
    }
  };

  const handleKill = async (state: KillSwitchState) => {
    setSaving(true);
    setActionError('');
    try {
      setStatus(await setKillSwitch(state, adminToken));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Kill switch failed');
    } finally {
      setSaving(false);
    }
  };

  const handleCloseAll = async () => {
    if (!window.confirm('Chiudere TUTTE le posizioni spot e perp al prezzo di mercato e mettere in pausa l\'agente?')) return;
    setSaving(true);
    setActionError('');
    try {
      const result = await riskCloseAll(adminToken);
      setStatus(result);
      await refresh(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Close-all failed');
    } finally {
      setSaving(false);
    }
  };

  const handleAdjustEquity = async (amount: number) => {
    const verb = amount >= 0 ? 'Versare' : 'Prelevare';
    const prep = amount >= 0 ? 'in' : 'da';
    if (!window.confirm(`${verb} ${Math.abs(amount).toFixed(2)}$ ${prep} liquidità?\n\nAggiorna l'equity, non il PnL.`)) return;
    setSaving(true);
    setActionError('');
    try {
      const result = await adjustEquity(amount, null, adminToken);
      window.alert(`Applicato ${amount >= 0 ? '+' : ''}${amount}$. Equity ora: ${Number(result.total_equity_usd).toFixed(2)}$.`);
      await refresh(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Adjust equity failed');
    } finally {
      setSaving(false);
    }
  };

  const handleTradeDetail = async (tradeId: string) => {
    detailTradeIdRef.current = tradeId;
    setActionError('');
    const cached = getCachedTradeDetail(tradeId);
    if (cached) {
      setTradeDetail(cached);
      setLoadingDetail(false);
      if (!hasCompleteTradeChart(cached)) {
        loadActiveTradeDetail(tradeId, true).catch(() => {});
      }
      return;
    }
    setLoadingDetail(true);
    try {
      await loadActiveTradeDetail(tradeId, true);
    } catch (err) {
      if (detailTradeIdRef.current === tradeId) {
        setActionError(err instanceof Error ? err.message : 'Unable to load trade detail');
      }
    } finally {
      if (detailTradeIdRef.current === tradeId) {
        setLoadingDetail(false);
      }
    }
    if (detailTradeIdRef.current === tradeId && !hasCompleteCachedTradeDetail(tradeId)) {
      loadActiveTradeDetail(tradeId, true).catch(() => {});
    }
  };

  const statusTone = useMemo(() => {
    if (status?.kill_switch === 'hard_stop') return 'text-accent-red';
    if (status?.kill_switch === 'soft_stop' || status?.kill_switch === 'degraded') return 'text-accent-yellow';
    return 'text-accent-green';
  }, [status]);

  return (
    <div className="space-y-4">
      {loadingDetail && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/70">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-dark-700 border-t-accent-yellow" />
          <p className="mt-3 text-sm text-gray-400">Caricamento dettaglio...</p>
          <button
            type="button"
            onClick={closeTradeDetail}
            className="mt-4 rounded-lg bg-dark-800 px-4 py-2 text-sm font-semibold text-gray-300"
          >
            Annulla
          </button>
        </div>
      )}
      {actionError && !tradeDetail && (
        <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{actionError}</p>
      )}
      {tradeDetail ? (
        <TradeDetailScreen detail={tradeDetail} onBack={closeTradeDetail} />
      ) : (
        <>
      <div className="rounded-xl bg-dark-800 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white">AI Agent</p>
            <p className="truncate text-xs text-gray-500">{status?.mode ?? settings.mode} - {status?.execution_mode ?? settings.execution_mode}</p>
          </div>
          <button
            onClick={() => void refresh()}
            disabled={refreshing}
            aria-label="Aggiorna"
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-dark-700 text-gray-300 disabled:opacity-70"
          >
            {refreshing ? (
              <svg className="h-4 w-4 animate-spin text-accent-blue" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
              </svg>
            ) : justSynced ? (
              <svg className="h-4 w-4 text-accent-green" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h5M20 20v-5h-5M5 9a7 7 0 0112-3m2 9a7 7 0 01-12 3" />
              </svg>
            )}
          </button>
        </div>
        <div className="mt-3 flex items-center justify-between rounded-lg bg-dark-900 px-3 py-2">
          <span className="text-xs text-gray-500">Runtime</span>
          <span className={`text-xs font-semibold ${statusTone}`}>{status?.kill_switch ?? 'loading'}</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-1.5">
        <SegmentButton id="spot" label="Spot" active={pane === 'spot'} onClick={setPane} />
        <SegmentButton id="perp" label="Perp" active={pane === 'perp'} onClick={setPane} />
        <SegmentButton id="global" label="Global" active={pane === 'global'} onClick={setPane} />
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        <SegmentButton id="wallet" label="Wallet" active={pane === 'wallet'} onClick={setPane} />
        <SegmentButton id="coins" label="Coins" active={pane === 'coins'} onClick={setPane} />
        <SegmentButton id="setup" label="Setup" active={pane === 'setup'} onClick={setPane} />
      </div>

      {error && <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{error}</p>}
      {watchlistError && pane !== 'coins' && (
        <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{watchlistError}</p>
      )}
      {pane === 'spot' && <SpotPane data={spot} onTrade={(tradeId) => void handleTradeDetail(tradeId)} />}
      {pane === 'perp' && <PerpPane data={perp} onTrade={(tradeId) => void handleTradeDetail(tradeId)} />}
      {pane === 'global' && <GlobalPane data={global} status={status} equity={equity} equityRange={equityRange} onEquityRange={setEquityRange} decisions={decisions} assetBreakdown={assetBreakdown} claudeUsage={claudeUsage} />}
      {pane === 'wallet' && <WalletPane execWallets={execWallets} spot={spot} perp={perp} />}
      {pane === 'coins' && (
        <CoinsPane
          eligibleTokens={eligibleTokens}
          selectedAiSymbols={selectedAiSymbols}
          adminToken={adminToken}
          saving={watchlistSaving}
          error={watchlistError}
          onToggle={onToggleAiSymbol}
        />
      )}
      {pane === 'setup' && (
        <SetupPane
          settings={settings}
          onSettings={setSettings}
          adminToken={adminToken}
          onAdminToken={onAdminToken}
          validation={validation}
          agentStatus={status}
          saving={saving}
          actionError={actionError}
          onSave={handleSave}
          onValidate={handleValidate}
          onKill={handleKill}
          onCloseAll={handleCloseAll}
          onAdjustEquity={handleAdjustEquity}
        />
      )}
        </>
      )}
    </div>
  );
};

export default AgentTab;
