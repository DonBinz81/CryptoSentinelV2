import { useCallback, useEffect, useMemo, useRef, useState, type FC } from 'react';
import {
  fetchAgentSettings,
  fetchAgentStatus,
  fetchAgentDecisions,
  fetchAssetBreakdown,
  fetchEquityCurve,
  type ClaudeUsageView,
  fetchClaudeUsage,
  fetchAsterWallet,
  fetchExecutionWallets,
  fetchGlobalView,
  fetchPerpView,
  fetchScannerStatus,
  fetchOperationalStats,
  type ScannerStatusResponse,
  type OperationalStats,
  fetchSpotView,
  saveAgentSettings,
  setKillSwitch,
  resetDailyCounter,
  resetDrawdownPeak,
  closePerpPosition,
  type ClosePerpPercentage,
  type ClosePerpPositionResponse,
  riskCloseAll,
  adjustEquity,
  validateOnboarding,
  fetchAgentWatchlist,
  fetchSpotWatchlist,
  updateSpotWatchlist,
  fetchPerpWatchlist,
  updatePerpWatchlist,
  type AgentDecisionResponse,
  type AgentMarketWatchlistResponse,
  type VenueAvailability,
  type WatchlistRanking,
  type AgentMobileSettings,
  type AgentStatus,
  type AssetBreakdownResponse,
  type CredentialValidationResponse,
  type EquityCurveResponse,
  type EquityRange,
  type AsterWalletView,
  type ExecutionWalletsResponse,
  type GlobalView,
  type KillSwitchState,
  type PerpView,
  type PerpPositionView,
  type SpotView,
  type TradeDetail,
  verifyAdminToken,
} from '../services/agentApi';
import { hapticLight } from '../utils/haptics';
import { TradeCandleChartLW } from './TradeCandleChartLW';
import { LEVEL_COLORS } from './tradeChartModel';
import { defaultSettings } from './agentDefaults';
import { GuardianBanner } from './GuardianBanner';
import { ScannerStatusPanel } from './ScannerStatusPanel';
import { DEV_PIN } from '../utils/devPin';
import { traduciErroreSalvataggio } from '../services/settingsErrorLabels';
import {
  getCachedTradeDetail,
  hasCompleteCachedTradeDetail,
  shouldPrefetchTradeDetail,
  schedulePrefetchRetry,
  fetchTradeDetailDeduped,
} from '../services/tradeDetailCache';

type AgentPane = 'spot' | 'perp' | 'global' | 'coins' | 'wallet' | 'setup';

const MICRO_PRICE_FULL_THRESHOLD = 0.000001;

const fmtUsd = (value: string | number | null | undefined) => {
  const n = Number(value ?? 0);
  return `$${n.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

/**
 * Come fmtUsd, ma distingue "assente" da "zero": rende `$--` quando il campo non
 * arriva, `$0,00` quando vale davvero zero.
 *
 * Serve ai campi aggiunti di recente. La CI pubblica un APK a ogni push, mentre
 * il backend si deploya a mano: esiste una finestra in cui l'app nuova parla con
 * un backend vecchio che quel campo non lo manda. Con fmtUsd si leggerebbe
 * `$0,00` — indistinguibile da "non hai scambiato niente", cioe' un numero
 * plausibile e falso. `fmtUsd` non e' stato cambiato: le sue decine di chiamate
 * esistenti si aspettano lo zero.
 */
const fmtUsdOpt = (value: string | number | null | undefined): string =>
  value == null || value === '' ? '$--' : fmtUsd(value);

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
  if (n >= 1000) return `$${n.toLocaleString('it-IT', { maximumFractionDigits: 2 })}`;
  if (n >= 1)    return `$${n.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
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
  const intStr = Math.trunc(Math.abs(n)).toLocaleString('it-IT');
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

const AGENT_REFRESH_MS = 45_000;
// Refresh leggero (solo posizioni/PnL). 15s evita accavallamenti quando provider esterni rallentano.
const AGENT_FAST_REFRESH_MS = 15_000;
const TRADE_DETAIL_BASE_TIMEOUT_MS = 20_000;
const TRADE_DETAIL_ENRICH_TIMEOUT_MS = 25_000;
// Matches the mobile history page size: open positions are always added on top.
const TRADE_DETAIL_PREFETCH_LIMIT = 8;
const TRADE_DETAIL_PREFETCH_CONCURRENCY = 2;

const EmptyState: FC<{ title: string; detail: string }> = ({ title, detail }) => (
  <div className="rounded-xl border border-dashed border-dark-600 bg-dark-800/60 px-4 py-8 text-center">
    <p className="text-sm font-semibold text-white">{title}</p>
    <p className="mt-1 text-xs text-gray-500 leading-relaxed">{detail}</p>
  </div>
);

/** Le due grandezze che il reset scelto azzera, coi rispettivi testi (NOTE/63, NOTE/83). */
type ResetKind = 'daily_loss' | 'drawdown_peak';

const RESET_COPY: Record<ResetKind, {
  domanda: string;
  spiegazione: string;
  avviso: string;
}> = {
  daily_loss: {
    domanda: 'Azzerare il conteggio di oggi?',
    spiegazione:
      'Il conteggio riparte da adesso. Il limite non cambia e continua a valere sul nuovo ' +
      'tratto: puoi perdere di nuovo fino alla stessa soglia prima che il blocco torni.',
    avviso:
      'Le perdite delle posizioni ancora aperte continuano a contare: l\'azzeramento riguarda ' +
      'solo quelle già chiuse.',
  },
  drawdown_peak: {
    domanda: 'Azzerare il picco del drawdown?',
    spiegazione:
      'Il picco di riferimento diventa l\'equity di adesso. Il cap non cambia e continua a ' +
      'valere sul nuovo tratto: puoi perdere di nuovo fino alla stessa soglia prima che il ' +
      'blocco torni.',
    avviso:
      'Le posizioni ancora aperte non scompaiono: qualunque calo, da adesso, torna a contare ' +
      'come nuovo drawdown dal nuovo riferimento.',
  },
};

/**
 * Conferma per azzerare un riferimento di rischio (NOTE/63 daily loss, NOTE/83
 * picco drawdown) — stessa cornice, testi diversi secondo `kind`.
 *
 * Tre livelli di attrito, voluti da David: l'admin token (verificato dal backend),
 * il PIN, e questi numeri davanti agli occhi. Quel limite serve proprio nel momento
 * in cui uno vuole scavalcarlo — dopo una giornata storta — quindi il gesto deve
 * costare qualcosa.
 */
const ResetCounterDialog: FC<{
  kind: ResetKind;
  guardrail: NonNullable<GlobalView['risk_guardrail']>;
  busy: boolean;
  error: string;
  onConfirm: () => void;
  onCancel: () => void;
}> = ({ kind, guardrail, busy, error, onConfirm, onCancel }) => {
  const [pin, setPin] = useState('');
  const pinOk = pin === DEV_PIN;
  const copy = RESET_COPY[kind];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-5">
      <div className="w-full max-w-sm rounded-xl border border-dark-600 bg-dark-800 p-4 space-y-3">
        <p className="text-sm font-bold text-white">{copy.domanda}</p>
        <p className="text-xs leading-5 text-gray-300">{copy.spiegazione}</p>
        <div className="grid grid-cols-2 gap-2 text-xs">
          {kind === 'daily_loss' ? (
            <>
              <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">
                Perdita oggi <b className="text-accent-red">{fmtPct(guardrail.daily_loss_used_pct)}</b>
              </span>
              <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">
                Limite <b className="text-white">{fmtPct(guardrail.daily_loss_limit_pct)}</b>
              </span>
            </>
          ) : (
            <>
              <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">
                Drawdown <b className="text-accent-red">{fmtPct(guardrail.drawdown_pct)}</b>
              </span>
              <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">
                Cap <b className="text-white">{fmtPct(Math.abs(guardrail.drawdown_cap_pct))}</b>
              </span>
            </>
          )}
        </div>
        <p className="text-[11px] leading-4 text-gray-500">{copy.avviso}</p>
        <div>
          <label className="text-[11px] text-gray-500">PIN</label>
          <input
            type="password"
            inputMode="numeric"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            className="mt-1 w-full rounded-lg bg-dark-900 px-3 py-2.5 text-sm text-white outline-none"
            placeholder="····"
          />
        </div>
        {error && <p className="text-xs text-accent-red">{error}</p>}
        <div className="flex gap-2 pt-1">
          <button
            onClick={onCancel}
            disabled={busy}
            className="flex-1 rounded-lg bg-dark-700 px-3 py-2.5 text-sm font-semibold text-gray-300 disabled:opacity-40"
          >
            Annulla
          </button>
          <button
            onClick={onConfirm}
            disabled={!pinOk || busy}
            className="flex-1 rounded-lg bg-accent-red px-3 py-2.5 text-sm font-bold text-white disabled:opacity-40"
          >
            {busy ? 'Attendi…' : 'Azzera'}
          </button>
        </div>
      </div>
    </div>
  );
};

/**
 * Il comando che ferma tutto (⛔ Chiudi tutto, nel banner del guardiano) e' sempre a
 * portata di mano. Quello che RIPARTE viveva solo dentro Setup: chi premeva
 * l'emergenza restava bloccato senza sapere dove andare a sbloccarsi (segnalato da
 * David, 02/09). Ora sta nella card "Runtime" in cima, lo stesso punto sempre
 * visibile su ogni scheda — non serve navigare per uscirne.
 */
export const ResumeAgentButton: FC<{
  killSwitch: KillSwitchState | undefined;
  adminToken: string;
  saving: boolean;
  onResume: () => void;
}> = ({ killSwitch, adminToken, saving, onResume }) => {
  if (!killSwitch || killSwitch === 'running') return null;
  return (
    <>
      <button
        onClick={onResume}
        disabled={!adminToken || saving}
        className="mt-2 w-full rounded-lg bg-accent-green/20 px-3 py-2.5 text-sm font-semibold text-accent-green disabled:opacity-40"
      >
        {saving ? 'Attendi…' : '▶ Riprendi agente'}
      </button>
      {!adminToken && (
        <p className="mt-1 text-[11px] text-gray-600">Per riprendere serve l&apos;admin token nel setup.</p>
      )}
    </>
  );
};

const RiskGuardrailBanner: FC<{ guardrail: GlobalView['risk_guardrail']; onOpenSetup?: () => void; onResetCounter?: (kind: ResetKind) => void }> = ({ guardrail, onOpenSetup, onResetCounter }) => {
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
      {/* I numeri devono essere QUELLI del blocco scattato. Prima si mostrava sempre
          drawdown e suo cap: con un blocco per perdita giornaliera si leggeva
          "9,28% su 15%" (sembri lontano dal limite) mentre il limite superato era
          un altro, -9,07% contro -8,00%. Un numero sbagliato accanto a un blocco
          e' peggio di nessun numero. */}
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        {guardrail.reason === 'daily_loss_limit_guard' ? (
          <>
            <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">Perdita oggi <b className="text-white">{fmtPct(guardrail.daily_loss_used_pct)}</b></span>
            <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">Limite <b className="text-white">{fmtPct(guardrail.daily_loss_limit_pct)}</b></span>
          </>
        ) : (
          <>
            <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">Drawdown <b className="text-white">{fmtPct(guardrail.drawdown_pct)}</b></span>
            <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">Cap <b className="text-white">{fmtPct(Math.abs(guardrail.drawdown_cap_pct))}</b></span>
          </>
        )}
      </div>
      {/* Quante volte il conteggio/picco e' stato azzerato oggi. Il limite resta
          aggirabile — e' una scelta di David — ma non silenziosamente. */}
      {(guardrail.daily_counter_resets_today ?? 0) > 0 && (
        <p className="mt-2 text-[11px] text-accent-yellow">
          Conteggio azzerato {guardrail.daily_counter_resets_today}
          {guardrail.daily_counter_resets_today === 1 ? ' volta' : ' volte'} oggi
          {guardrail.daily_counter_reset_at && ` · ultimo alle ${new Date(guardrail.daily_counter_reset_at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}`}
        </p>
      )}
      {(guardrail.drawdown_peak_resets_today ?? 0) > 0 && (
        <p className="mt-2 text-[11px] text-accent-yellow">
          Picco azzerato {guardrail.drawdown_peak_resets_today}
          {guardrail.drawdown_peak_resets_today === 1 ? ' volta' : ' volte'} oggi
          {guardrail.drawdown_peak_reset_at && ` · ultimo alle ${new Date(guardrail.drawdown_peak_reset_at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}`}
        </p>
      )}
      <div className="mt-3 space-y-2">
        {/* Il limite si allenta dal setup: da qui ci si arriva in un tocco invece di
            cercarlo. Non e' uno sblocco — il valore resta cambiato, quindi si vede
            di stare correndo senza rete. */}
        {onOpenSetup && (
          <button
            onClick={onOpenSetup}
            className="w-full rounded-lg border border-accent-red/40 px-3 py-2 text-xs font-semibold text-accent-red"
          >
            {guardrail.reason === 'daily_loss_limit_guard' ? 'Rivedi il limite giornaliero' : 'Rivedi i limiti di rischio'}
          </button>
        )}
        {/* Azzerare il riferimento scavalca una protezione del capitale: tre livelli
            di attrito voluti da David — admin token, PIN, e la conferma coi numeri. */}
        {guardrail.reason === 'daily_loss_limit_guard' && onResetCounter && (
          <button
            onClick={() => onResetCounter('daily_loss')}
            className="w-full rounded-lg bg-dark-700 px-3 py-2 text-xs font-semibold text-gray-300"
          >
            Azzera il conteggio di oggi
          </button>
        )}
        {guardrail.reason === 'drawdown_cap_guard' && onResetCounter && (
          <button
            onClick={() => onResetCounter('drawdown_peak')}
            className="w-full rounded-lg bg-dark-700 px-3 py-2 text-xs font-semibold text-gray-300"
          >
            Azzera il picco del drawdown
          </button>
        )}
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
        <SectionTitle>PnL cumulato</SectionTitle>
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

// `availability` arriva dal backend (venue + stato). Quando manca, il toggle si
// comporta esattamente come prima: la scheda master non conosce le venue.
// Una coin non disponibile non è selezionabile, ma se è GIÀ selezionata resta
// cliccabile: altrimenti le scelte salvate prima (es. COMP su Aster) non
// sarebbero più rimovibili dall'app.
const TokenToggle: FC<{
  symbol: string;
  selected: boolean;
  disabled: boolean;
  onToggle: (symbol: string) => void;
  availability?: VenueAvailability;
  rank?: number | null;
}> = ({ symbol, selected, disabled, onToggle, availability, rank }) => {
  const status = availability?.status;
  const blocked = status === 'unavailable' && !selected;
  const tone = selected
    ? 'border-accent-yellow/50 bg-accent-yellow/10 text-accent-yellow'
    : status === 'unavailable'
      ? 'border-accent-red/40 bg-accent-red/5 text-gray-500'
      : 'border-dark-700 bg-dark-800 text-gray-300';
  return (
    <button
      type="button"
      disabled={disabled || blocked}
      onClick={() => { hapticLight(); onToggle(symbol); }}
      title={availability?.reason}
      className={`flex flex-col gap-0.5 rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-45 ${tone}`}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-baseline gap-1.5">
          {/* Posizione globale per capitalizzazione (CoinMarketCap): BTC = 1. */}
          {rank != null && <span className="flex-shrink-0 text-[10px] text-gray-500">#{rank}</span>}
          <span className={`min-w-0 truncate text-sm font-semibold ${status === 'unavailable' ? 'line-through' : ''}`}>{symbol}</span>
        </span>
        <span className={`h-2.5 w-2.5 flex-shrink-0 rounded-full ${selected ? 'bg-accent-yellow' : 'bg-gray-600'}`} />
      </span>
      {availability && (
        <span className="flex items-center justify-between gap-2 text-[10px] leading-tight">
          <span className="truncate capitalize text-gray-500">{availability.venue}</span>
          <span
            className={
              status === 'available'
                ? 'flex-shrink-0 text-accent-green'
                : status === 'unavailable'
                  ? 'flex-shrink-0 text-accent-red'
                  : 'flex-shrink-0 text-gray-500'
            }
          >
            {status === 'available' ? '✓' : status === 'unavailable' ? 'Non disponibile' : 'Non verificato'}
          </span>
        </span>
      )}
    </button>
  );
};

// Punto interrogativo con spiegazione breve. Un solo riquadro aperto per volta:
// aprirne uno chiude gli altri (evento globale), e si chiude anche toccando
// altrove o scorrendo. Sta dentro <label>, quindi il click va fermato o
// attiverebbe il campo associato (sui toggle invertirebbe la spunta).
const HelpTip: FC<{ text: string; top?: boolean }> = ({ text, top }) => {
  // `pos` nullo = chiuso. Il riquadro è `fixed` e centrato sullo schermo, non
  // ancorato al "?": ancorandolo, i campi della colonna destra lo facevano
  // uscire dal bordo. Verticalmente sta sotto il "?", oppure sopra se in fondo
  // allo schermo non ci sta.
  // `top` forza invece la posizione in cima allo schermo: serve alle spiegazioni
  // lunghe, che superano qualsiasi altezza stimata e uscirebbero dal bordo
  // inferiore.
  const [pos, setPos] = useState<{ top: number; above: boolean } | null>(null);
  const idRef = useRef(`ht${Math.random().toString(36).slice(2, 9)}`);
  const btnRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!pos) return;
    const onOther = (e: Event) => { if ((e as CustomEvent).detail !== idRef.current) setPos(null); };
    const onAway = () => setPos(null);
    document.addEventListener('helptip:open', onOther as EventListener);
    document.addEventListener('click', onAway);
    window.addEventListener('scroll', onAway, true);
    window.addEventListener('resize', onAway);
    return () => {
      document.removeEventListener('helptip:open', onOther as EventListener);
      document.removeEventListener('click', onAway);
      window.removeEventListener('scroll', onAway, true);
      window.removeEventListener('resize', onAway);
    };
  }, [pos]);
  return (
    <>
      <button
        ref={btnRef}
        type="button"
        aria-label="Spiegazione"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (pos) { setPos(null); return; }
          if (top) {
            setPos({ top: 64, above: false });
          } else {
            const r = btnRef.current?.getBoundingClientRect();
            if (!r) return;
            const STIMA = 170; // altezza tipica del riquadro
            const above = r.bottom + STIMA > window.innerHeight;
            setPos({ top: above ? r.top - 8 : r.bottom + 8, above });
          }
          document.dispatchEvent(new CustomEvent('helptip:open', { detail: idRef.current }));
        }}
        className={`ml-1.5 inline-flex h-4 w-4 items-center justify-center rounded-full border text-[10px] font-bold leading-none transition-colors ${
          pos ? 'border-accent-blue bg-accent-blue text-white' : 'border-dark-600 text-gray-500'
        }`}
      >
        ?
      </button>
      {pos && (
        <span
          onClick={(e) => e.stopPropagation()}
          style={{
            top: pos.above ? undefined : pos.top,
            bottom: pos.above ? window.innerHeight - pos.top : undefined,
          }}
          className="fixed left-1/2 z-50 block max-h-[70vh] w-max max-w-[min(19rem,calc(100vw-2.5rem))] -translate-x-1/2 overflow-y-auto whitespace-pre-line rounded-xl border border-dark-600 bg-dark-900 px-4 py-3 text-[13px] font-normal leading-relaxed text-gray-200 shadow-2xl"
        >
          {text}
        </span>
      )}
    </>
  );
};

// Intestazione di sezione. Il colore segue il SIGNIFICATO, non il mercato: le
// linguette in alto dicono gia' se sei in Spot o Perp, mentre il colore dice che
// tipo di parametri stai guardando — rosso il rischio, blu la strategia, verde le
// protezioni, ambra i filtri, grigio il resto. La barretta a sinistra aggancia lo
// sguardo mentre si scorre una pagina lunga.
type SectionTone = 'rischio' | 'strategia' | 'protezioni' | 'filtri' | 'neutro';

const SECTION_TONES: Record<SectionTone, { text: string; bar: string }> = {
  rischio:    { text: 'text-accent-red',    bar: 'bg-accent-red' },
  strategia:  { text: 'text-accent-blue',   bar: 'bg-accent-blue' },
  protezioni: { text: 'text-accent-green',  bar: 'bg-accent-green' },
  filtri:     { text: 'text-accent-yellow', bar: 'bg-accent-yellow' },
  neutro:     { text: 'text-gray-300',      bar: 'bg-gray-500' },
};

const SectionTitle: FC<{ tone?: SectionTone; children: React.ReactNode }> = ({ tone = 'neutro', children }) => (
  <div className="flex items-center gap-2 px-1">
    <span className={`h-3.5 w-1 shrink-0 rounded-full ${SECTION_TONES[tone].bar}`} />
    <h3 className={`text-xs font-bold uppercase tracking-wide ${SECTION_TONES[tone].text}`}>{children}</h3>
  </div>
);

// Blocco richiudibile per le sezioni lunghe e di uso raro (Smart SL, shock BTC):
// partono chiuse, così la scheda Perp resta leggibile senza scorrere decine di
// campi che si toccano una volta ogni tanto.
const Collapsible: FC<{ title: string; count: number; children: React.ReactNode }> = ({ title, count, children }) => {
  const [open, setOpen] = useState(() => agentCache.openBlocks.includes(title));
  const toggle = () => setOpen((v) => !v);
  useEffect(() => {
    const rest = agentCache.openBlocks.filter((t) => t !== title);
    agentCache.openBlocks = open ? [...rest, title] : rest;
  }, [open, title]);
  return (
    <div className="rounded-lg border border-dark-700">
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
      >
        <span className="text-sm font-semibold text-white">{title}</span>
        <span className="flex items-center gap-2">
          <span className="rounded-full bg-dark-700 px-2 py-0.5 text-xs text-gray-400">{count}</span>
          <span className={`text-xs text-gray-500 transition-transform ${open ? 'rotate-90' : ''}`}>▶</span>
        </span>
      </button>
      {open && <div className="space-y-3 border-t border-dark-700 px-3 py-3">{children}</div>}
    </div>
  );
};

const NumberInput: FC<{
  label: string;
  value: number;
  step?: number;
  help?: string;
  /** Limiti dichiarati dal backend (Field ge/le in mobile_agent.py). Se presenti,
   * il valore viene riportato dentro il limite quando si esce dal campo, invece
   * di scoprirlo solo al salvataggio con un 422 che non dice quale campo aprire. */
  min?: number;
  max?: number;
  onChange: (value: number) => void;
}> = ({ label, value, step = 1, help, min, max, onChange }) => {
  const [raw, setRaw] = useState(String(value));
  const [limitato, setLimitato] = useState(false);
  useEffect(() => { setRaw(String(value)); }, [value]);
  return (
    <label className="block">
      <span className="text-xs text-gray-500">{label}</span>
      {help && <HelpTip text={help} />}
      <input
        type="number"
        step={step}
        min={min}
        max={max}
        value={raw}
        onChange={(e) => {
          const s = e.target.value;
          setRaw(s);
          setLimitato(false);
          const n = parseFloat(s);
          if (!Number.isNaN(n)) onChange(n);
        }}
        onBlur={() => {
          const n = parseFloat(raw);
          if (!Number.isNaN(n)) {
            const clamped = Math.min(max ?? n, Math.max(min ?? n, n));
            if (clamped !== n) {
              setLimitato(true);
              onChange(clamped);
              setRaw(String(clamped));
              return;
            }
          }
          setRaw(String(value));
        }}
        className="mt-1 w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
      />
      {limitato && (
        <span className="mt-0.5 block text-[11px] text-accent-yellow">
          Riportato al {raw === String(max) ? 'massimo' : 'minimo'} consentito ({raw})
        </span>
      )}
    </label>
  );
};

const SelectInput: FC<{
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  help?: string;
  onChange: (value: string) => void;
}> = ({ label, value, options, help, onChange }) => (
  <label className="block">
    <span className="text-xs text-gray-500">{label}</span>
    {help && <HelpTip text={help} />}
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
  help?: string;
  onChange: (checked: boolean) => void;
}> = ({ label, checked, help, onChange }) => (
  <label className="flex items-center justify-between gap-3 rounded-lg border border-dark-700 bg-dark-800 px-3 py-2">
    <span className="min-w-0 text-sm font-semibold text-white">
      {label}
      {help && <HelpTip text={help} />}
    </span>
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
  // Chiusure decise da una persona. Mancavano: il backend le mandava gia', ma
  // senza una voce qui il rendering le scartava in silenzio e in lista non si
  // vedeva nulla. Fucsia come il marker sul grafico, per non confonderle con
  // l'ambra dello Smart SL, che e' automatico.
  manual_partial_close: { label: '✂ Riduzione manuale', className: 'text-fuchsia-400' },
  manual_full_close: { label: '✂ Chiusura manuale', className: 'text-fuchsia-400' },
};

export const TradeHistoryList: FC<{
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
                    {/* Quota tolta da QUESTA chiusura (non cumulativa: quella e' il
                        badge sulla posizione aperta). Assente se non calcolabile. */}
                    {'manual_close_pct' in t && t.manual_close_pct != null && ` · −${Number(t.manual_close_pct).toFixed(0)}%`}
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

export const SpotPane: FC<{ data: SpotView | null; onTrade: (tradeId: string) => void }> = ({ data, onTrade }) => {
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
        <Stat label="Vol Tot" value={fmtUsdOpt(data?.volume_total_usd)} />
        <Stat label="Vol Day" value={fmtUsdOpt(data?.volume_today_usd)} />
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
          <SectionTitle>Spot history</SectionTitle>
          <TradeHistoryList trades={data!.history} market="spot" onTrade={onTrade} />
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessun trade oggi" detail="Lo storico si popola quando l'agente prepara o chiude operazioni spot." />
      )}
    </div>
  );
};

const CLOSE_PERCENTAGES: ClosePerpPercentage[] = [25, 50, 75, 100];

/** Un UUID per ogni TENTATIVO NUOVO (apertura modale, o ripartenza dopo un esito che
 * cambia i presupposti della richiesta). Sul retry di uno STESSO tentativo — errore di
 * rete, "execution_failed" — la chiave resta identica: e' quella che permette al
 * backend di riconoscere il retry e non chiudere una seconda fetta (NOTE/107). */
const nuovaIdempotencyKey = (): string =>
  (globalThis.crypto?.randomUUID?.() ?? `k-${Date.now()}-${Math.random().toString(36).slice(2)}`);

const fmtQty = (v: string | number, decimals = 4): string => Number(v).toFixed(decimals);

/**
 * Chiusura manuale (parziale o totale) di una posizione perp aperta (NOTE/107,
 * contratto congelato dalla chat A). Due protezioni obbligatorie per contratto:
 * l'Idempotency-Key copre il retry di rete, `expected_size` (sempre l'ultimo dato
 * mostrato) copre il doppio tap — la chiave da sola non lo intercetterebbe, perche'
 * un doppio tap genera due richieste con DUE chiavi diverse.
 */
export const ClosePositionModal: FC<{
  position: PerpPositionView;
  adminToken: string;
  onCancel: () => void;
  onClosed: () => void;
  /** Punto di innesto per il banco di anteprima: il banco ha VITE_BACKEND_API_BASE_URL
   * vuoto per regola condivisa (dev-preview/vite.config.mts), quindi la chiamata vera
   * fallirebbe subito su requireBackend(). In produzione non si passa mai — resta la
   * funzione reale, il comportamento non cambia di una virgola. */
  closeFn?: typeof closePerpPosition;
}> = ({ position, adminToken, onCancel, onClosed, closeFn = closePerpPosition }) => {
  const [percentage, setPercentage] = useState<ClosePerpPercentage | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<ClosePerpPositionResponse | null>(null);
  // La size mostrata: si aggiorna SOLO se il backend dice che era superata
  // (stale_position). expected_size manda sempre questo valore, mai quello
  // dell'apertura della modale se nel frattempo e' cambiato.
  const [shownSize, setShownSize] = useState(position.size);
  const idempotencyKeyRef = useRef(nuovaIdempotencyKey());

  const sizeNum = Number(shownSize);
  const pnlNum = Number(position.pnl_unrealized);
  const quotaQty = percentage != null ? (sizeNum * percentage) / 100 : null;
  const residuoQty = percentage != null ? sizeNum - (quotaQty ?? 0) : null;
  const quotaPnl = percentage != null ? (pnlNum * percentage) / 100 : null;

  const invia = async () => {
    if (!percentage || !adminToken || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      const esito = await closeFn(
        position.position_id,
        { percentage, expectedSize: shownSize },
        idempotencyKeyRef.current,
        adminToken,
      );
      setResult(esito);
      switch (esito.outcome) {
        case 'confirmed':
        case 'already_closed':
        case 'not_found':
          // Non si chiude subito: l'utente deve VEDERE l'esito (quantita' e prezzo
          // eseguiti, l'avviso forced_full se c'e') prima che la modale sparisca.
          // Il padre si aggiorna solo quando l'utente preme "Chiudi" qui sotto, mai
          // in anticipo sulla stima locale mostrata durante la scelta.
          break;
        case 'stale_position':
          // Presupposti cambiati: serve un tentativo NUOVO, non un retry — chiave
          // nuova, size aggiornata da quella che il backend riporta.
          if (esito.current_size) setShownSize(esito.current_size);
          idempotencyKeyRef.current = nuovaIdempotencyKey();
          break;
        case 'key_reused_with_different_payload':
          // Non dovrebbe mai succedere con questa logica di generazione chiavi;
          // se succede e' piu' sicuro ripartire da un tentativo nuovo.
          idempotencyKeyRef.current = nuovaIdempotencyKey();
          break;
        case 'in_progress':
        case 'invalid_request':
        case 'execution_failed':
          // execution_failed: STESSA chiave, e' un retry dello stesso tentativo —
          // la venue non ha confermato, non che la richiesta fosse sbagliata.
          break;
      }
    } catch (e) {
      // Errore di rete/timeout: non sappiamo se e' arrivato al backend. La chiave
      // resta la stessa apposta — il backend, sul retry, riconosce lo stesso
      // tentativo invece di eseguirne uno nuovo.
      setError(e instanceof Error ? e.message : 'Errore di rete: verifica prima di ritentare.');
    } finally {
      setSubmitting(false);
    }
  };

  const rendiEsito = () => {
    if (!result) return null;
    switch (result.outcome) {
      case 'confirmed': {
        const totale = result.position_status === 'closed';
        return (
          <div className="rounded-lg bg-accent-green/10 border border-accent-green/30 px-3 py-2.5 space-y-1">
            <p className="text-sm font-bold text-accent-green">
              {totale ? 'Posizione chiusa per intero' : `Chiusa la quota richiesta`}
            </p>
            {result.forced_full && (
              <p className="text-xs font-semibold text-accent-yellow">
                ⚠️ Il residuo era sotto la soglia negoziabile: chiusa PER INTERO, non solo la quota richiesta.
              </p>
            )}
            <p className="text-xs text-gray-300">
              Eseguito {fmtQty(result.executed_qty ?? '0')} a {fmtPrice(result.executed_price ?? '0')}
              {' · '}residuo {fmtQty(result.remaining_qty ?? '0')}
            </p>
            <p className="text-xs text-gray-400">PnL realizzato: {fmtUsd(result.realized_pnl_usd ?? '0')}</p>
          </div>
        );
      }
      case 'stale_position':
        return (
          <p className="rounded-lg bg-accent-yellow/10 border border-accent-yellow/30 px-3 py-2.5 text-xs text-accent-yellow">
            La size è cambiata da quando hai aperto la scheda — aggiornata qui sotto. Verifica e riconferma.
          </p>
        );
      case 'already_closed':
        return (
          <p className="rounded-lg bg-dark-900/60 px-3 py-2.5 text-xs text-gray-400">
            La posizione non è più aperta: probabilmente chiusa nel frattempo da un altro evento (stop, TP, guardiano).
          </p>
        );
      case 'not_found':
        return (
          <p className="rounded-lg bg-dark-900/60 px-3 py-2.5 text-xs text-gray-400">
            Posizione non trovata.
          </p>
        );
      case 'in_progress':
        return (
          <p className="rounded-lg bg-accent-yellow/10 border border-accent-yellow/30 px-3 py-2.5 text-xs text-accent-yellow">
            Un tentativo precedente è ancora in corso: attendi, non reinviare adesso. Riprova tra poco.
          </p>
        );
      case 'invalid_request':
        return (
          <p className="rounded-lg bg-accent-red/10 border border-accent-red/30 px-3 py-2.5 text-xs text-accent-red">
            {result.detail ?? 'Richiesta non valida.'}
          </p>
        );
      case 'key_reused_with_different_payload':
        return (
          <p className="rounded-lg bg-accent-red/10 border border-accent-red/30 px-3 py-2.5 text-xs text-accent-red">
            Anomalia interna del client, non tua: riprova, verrà usato un tentativo nuovo.
          </p>
        );
      case 'execution_failed':
        return (
          <p className="rounded-lg bg-accent-red/10 border border-accent-red/30 px-3 py-2.5 text-xs text-accent-red">
            La venue non ha confermato l'esecuzione. La posizione non è cambiata — puoi riprovare in sicurezza.
          </p>
        );
      default:
        return null;
    }
  };

  const chiusa = result?.outcome === 'confirmed' || result?.outcome === 'already_closed' || result?.outcome === 'not_found';
  const puoRiprovare = result != null && !chiusa && result.outcome !== 'in_progress';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-5">
      <div className="w-full max-w-sm rounded-2xl border border-dark-600 bg-dark-800 p-4 space-y-3 max-h-[85vh] overflow-y-auto">
        <div>
          <p className="text-sm font-bold text-white">
            {position.asset} {position.side} <span className="text-accent-blue">{position.leverage}x</span>
          </p>
          <p className="mt-0.5 text-xs text-gray-500">
            Size {fmtQty(shownSize)} · PnL{' '}
            <span className={pnlNum >= 0 ? 'text-accent-green' : 'text-accent-red'}>
              {fmtUsd(position.pnl_unrealized)} / {position.pnl_pct ?? '+0.00'}%
            </span>
          </p>
        </div>

        {!chiusa && (
          <>
            <div className="grid grid-cols-4 gap-1.5">
              {CLOSE_PERCENTAGES.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => { setPercentage(p); setResult(null); setError(''); }}
                  disabled={submitting}
                  className={`rounded-lg py-2.5 text-sm font-bold transition-colors disabled:opacity-40 ${
                    percentage === p ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-300'
                  }`}
                >
                  {p}%
                </button>
              ))}
            </div>

            {percentage != null && (
              <div className="rounded-lg bg-dark-900/60 px-3 py-2.5 space-y-1 text-xs text-gray-400">
                <div className="flex justify-between">
                  <span>Quota da chiudere (stima)</span>
                  <span className="text-white">{fmtQty(quotaQty ?? 0)}</span>
                </div>
                <div className="flex justify-between">
                  <span>Residuo stimato</span>
                  <span className="text-white">{fmtQty(residuoQty ?? 0)}</span>
                </div>
                <div className="flex justify-between">
                  <span>PnL stimato sulla quota</span>
                  <span className={(quotaPnl ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}>
                    {fmtUsd(quotaPnl ?? 0)}
                  </span>
                </div>
              </div>
            )}
          </>
        )}

        {(error || result) && (
          <div className="space-y-2">
            {error && (
              <p className="rounded-lg bg-accent-red/10 border border-accent-red/30 px-3 py-2.5 text-xs text-accent-red">
                {error}
              </p>
            )}
            {rendiEsito()}
          </div>
        )}

        {percentage != null && !chiusa && (
          <p className="text-[11px] leading-4 text-gray-500">
            Prezzo e PnL finali possono cambiare fra la conferma e l'esecuzione — quelli sopra sono una stima.
          </p>
        )}

        {!adminToken && (
          <p className="text-[11px] text-gray-600">Richiede admin token salvato.</p>
        )}

        <div className="flex gap-2 pt-1">
          <button
            type="button"
            // "Chiudi" dopo un esito definitivo avvisa il padre (la posizione e'
            // davvero cambiata, la card va ricaricata); "Annulla" prima di quel
            // momento no — non e' successo nulla da aggiornare.
            onClick={chiusa ? onClosed : onCancel}
            disabled={submitting}
            className="flex-1 rounded-lg bg-dark-700 px-3 py-2.5 text-sm font-semibold text-gray-300 disabled:opacity-40"
          >
            {chiusa ? 'Chiudi' : 'Annulla'}
          </button>
          {!chiusa && (
            <button
              type="button"
              onClick={() => void invia()}
              disabled={!percentage || !adminToken || submitting || result?.outcome === 'in_progress'}
              className="flex-1 rounded-lg bg-accent-red px-3 py-2.5 text-sm font-bold text-white disabled:opacity-40"
            >
              {submitting
                ? 'Chiusura in corso…'
                : puoRiprovare
                  ? 'Riprova'
                  : percentage
                    ? `Conferma chiusura ${percentage}%`
                    : 'Scegli una percentuale'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export const PerpPane: FC<{
  data: PerpView | null;
  onTrade: (tradeId: string) => void;
  adminToken: string;
  onClosed: () => void;
}> = ({ data, onTrade, adminToken, onClosed }) => {
  const [closeTarget, setCloseTarget] = useState<PerpPositionView | null>(null);
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
        <Stat label="Vol Tot" value={fmtUsdOpt(data?.volume_total_usd)} />
        <Stat label="Vol Day" value={fmtUsdOpt(data?.volume_today_usd)} />
      </div>
      {/* Senza questa riga un Vol Tot da migliaia di dollari su un conto da
          poche centinaia sembra un errore di calcolo: e' il nozionale, che con
          la leva e' un multiplo del capitale. */}
      <p className="px-1 text-[11px] text-gray-500">
        Vol = volume scambiato (nozionale, leva inclusa), non capitale impegnato.
      </p>
      {!hasActivity && (
        <EmptyState title="In attesa di segnali perp" detail="Nessuna posizione aperta e nessun trade registrato." />
      )}
      {hasPositions ? (
        <div className="space-y-2">
          {data!.open_positions.map((position) => (
            <div key={position.position_id} className="rounded-xl bg-dark-800 px-4 py-3">
              <button
                type="button"
                onClick={() => position.open_trade_id && onTrade(position.open_trade_id)}
                disabled={!position.open_trade_id}
                className="block w-full text-left disabled:cursor-default"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-white">{position.asset} {position.side}</p>
                    <span className="rounded-full bg-dark-700 px-2 py-1 text-xs text-accent-blue">{position.leverage}x</span>
                    {position.smart_sl_active && (
                      <span className={`rounded-full px-2 py-1 text-xs font-semibold ${position.smart_sl_levels_sold?.some(Boolean) ? 'bg-amber-900/40 text-amber-400' : 'bg-dark-700 text-gray-400'}`}>
                        SSL {position.smart_sl_levels_sold?.filter(Boolean).length ?? 0}/2
                      </span>
                    )}
                    {!!position.manual_close_count && (
                      <span className="rounded-full bg-amber-900/40 px-2 py-1 text-xs font-semibold text-amber-400">
                        ✂ {position.manual_close_count}×{position.manual_reduced_pct != null ? ` · −${Number(position.manual_reduced_pct).toFixed(0)}%` : ''}
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
                {!!position.manual_close_count && (
                  <p className="mt-1.5 text-xs text-amber-400/80">
                    Ridotta a mano {position.manual_close_count} volt{position.manual_close_count === 1 ? 'a' : 'e'}
                    {position.manual_reduced_pct != null ? `, size originale −${Number(position.manual_reduced_pct).toFixed(1)}%` : ''}
                  </p>
                )}
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
              {/* Chiusura manuale (NOTE/107): comando separato da "Chiudi tutto & metti
                  in pausa" del banner del guardiano — questo riduce/chiude UNA sola
                  posizione, non tocca il kill switch, non mette mai in pausa l'agente. */}
              <button
                type="button"
                onClick={() => setCloseTarget(position)}
                className="mt-2 w-full rounded-lg border border-accent-red/30 bg-accent-red/10 px-3 py-2 text-xs font-semibold text-accent-red"
              >
                Riduci / Chiudi
              </button>
            </div>
          ))}
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessuna posizione aperta" detail="Le posizioni perp long/short appariranno qui." />
      )}
      {closeTarget && (
        <ClosePositionModal
          position={closeTarget}
          adminToken={adminToken}
          onCancel={() => setCloseTarget(null)}
          onClosed={() => { setCloseTarget(null); onClosed(); }}
        />
      )}
      {hasHistory ? (
        <div className="space-y-2">
          <SectionTitle>Perp history</SectionTitle>
          <TradeHistoryList trades={data!.history} market="perp" onTrade={onTrade} />
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessun trade perp" detail="Lo storico perp si popola dopo le prime operazioni." />
      )}
    </div>
  );
};

export const GlobalPane: FC<{
  data: GlobalView | null;
  status: AgentStatus | null;
  equity: EquityCurveResponse | null;
  equityRange: EquityRange;
  onEquityRange: (r: EquityRange) => void;
  decisions: AgentDecisionResponse | null;
  assetBreakdown: AssetBreakdownResponse | null;
  claudeUsage: ClaudeUsageView | null;
  onOpenSetup?: () => void;
  adminToken?: string;
  onCounterReset?: () => void;
  operationalStats?: OperationalStats | null;
}> = ({ data, status, equity, equityRange, onEquityRange, decisions, assetBreakdown, claudeUsage, onOpenSetup, adminToken, onCounterReset, operationalStats = null }) => {
  const [resetKind, setResetKind] = useState<ResetKind | null>(null);
  const [resetBusy, setResetBusy] = useState(false);
  const [resetError, setResetError] = useState('');

  const confirmReset = async () => {
    if (!resetKind) return;
    if (!adminToken) { setResetError("Serve l'admin token: salvalo nel setup."); return; }
    setResetBusy(true);
    setResetError('');
    try {
      const esito = resetKind === 'daily_loss'
        ? await resetDailyCounter(adminToken, 'da app')
        : await resetDrawdownPeak(adminToken, 'da app');
      if (esito.status !== 'ok' && esito.status !== 'success') {
        setResetError(esito.reason ?? 'Il backend ha rifiutato la richiesta.');
        return;
      }
      setResetKind(null);
      onCounterReset?.();
    } catch (e) {
      setResetError(e instanceof Error ? e.message : 'Errore di rete.');
    } finally {
      setResetBusy(false);
    }
  };
  const hasHistory = (data?.pnl_history.length ?? 0) > 0;
  const hasPortfolio = Number(data?.total_equity_usd ?? 0) > 0 || Number(data?.initial_equity_usd ?? 0) > 0;
  const hasTradesToday = Number(data?.trades_today ?? 0) > 0;
  const sortedAssets = [...(assetBreakdown?.items ?? [])].sort((a, b) => Number(b.pnl_usd) - Number(a.pnl_usd));
  const bestAssets = sortedAssets.slice(0, 3);
  const worstAssets = sortedAssets.slice(-3).reverse();

  return (
    <div className="space-y-3">
      <RiskGuardrailBanner
        guardrail={data?.risk_guardrail}
        onOpenSetup={onOpenSetup}
        onResetCounter={(kind) => { setResetError(''); setResetKind(kind); }}
      />
      {resetKind && data?.risk_guardrail && (
        <ResetCounterDialog
          kind={resetKind}
          guardrail={data.risk_guardrail}
          busy={resetBusy}
          error={resetError}
          onConfirm={() => void confirmReset()}
          onCancel={() => setResetKind(null)}
        />
      )}
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
        <Stat label="Vol Tot" value={fmtUsdOpt(data?.volume_total_usd)} />
        <Stat label="Vol Day" value={fmtUsdOpt(data?.volume_today_usd)} />
        <Stat
          label="API Claude"
          value={claudeUsage != null ? `$${claudeUsage.total_cost_usd.toFixed(2)} / $${claudeUsage.budget_usd.toFixed(2)}` : '--'}
          tone={claudeUsage == null ? 'neutral' : claudeUsage.budget_pct >= 90 ? 'bad' : claudeUsage.budget_pct >= 70 ? 'neutral' : 'good'}
        />
      </div>
      {/* Il Global somma anche il perp: senza questa riga il Vol Tot sembra
          sproporzionato rispetto all'equity. */}
      <p className="px-1 text-[11px] text-gray-500">
        Vol = volume scambiato (nozionale, leva inclusa), non capitale impegnato.
      </p>
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
        <AssetRank title="Top asset" items={bestAssets} tone="protezioni" />
        <AssetRank title="Worst asset" items={worstAssets} tone="rischio" />
      </div>
      <section className="space-y-2">
        <SectionTitle>Ultime decisioni</SectionTitle>
        {(decisions?.items.length ?? 0) > 0 ? decisions!.items.slice(0, 3).map((item) => (
          <div key={item.decision_id} className="flex items-center justify-between rounded-lg bg-dark-800 px-3 py-2 text-xs">
            <span className="text-white">{item.action} {item.asset ?? '--'}</span>
            <span className="text-gray-500">{new Date(item.timestamp_utc).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        )) : (
          <EmptyState title="Nessuna decisione" detail="Le ultime valutazioni AI appariranno qui." />
        )}
      </section>
      {/* In fondo: si consulta, non si sorveglia. */}
      <SystemHealthPanel stats={operationalStats} status={status} />
    </div>
  );
};

/** Da quanto tempo un tick non batte, in forma leggibile. */
const etaTick = (iso: string | null | undefined): { testo: string; vecchio: boolean } | null => {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  return { testo: s < 60 ? `${s}s fa` : `${Math.floor(s / 60)} min fa`, vecchio: s >= 120 };
};

/** Codici del motore -> testo leggibile. Oggi `claude_unavailable` e' l'unico
 *  che il backend produca davvero (`agent/service.py:3312`); un codice
 *  sconosciuto si mostra COM'E', perche' nasconderlo perderebbe l'unica
 *  informazione disponibile su un guasto che non abbiamo previsto. */
const DEGRADO_LEGGIBILE: Record<string, string> = {
  claude_unavailable: 'Brain (Claude) non raggiungibile',
};

const leggiDegrado = (codice: string): string => DEGRADO_LEGGIBILE[codice] ?? codice;

/** Riga del pannello salute. Valore null => "non disponibile", mai un numero inventato. */
const RigaSalute: FC<{
  etichetta: string;
  valore: string | null;
  dettaglio?: string | null;
  punto?: string;
  tono?: string;
}> = ({ etichetta, valore, dettaglio, punto, tono = 'text-gray-300' }) => (
  <div className="flex items-start justify-between gap-3 py-1.5">
    <div className="flex items-center gap-2">
      {punto && <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${punto}`} />}
      <span className="whitespace-nowrap text-xs text-gray-400">{etichetta}</span>
    </div>
    <div className="min-w-0 text-right">
      {valore == null ? (
        <span className="text-xs italic text-gray-600">non disponibile</span>
      ) : (
        <span className={`text-xs font-semibold ${tono}`}>{valore}</span>
      )}
      {dettaglio && <p className="mt-0.5 text-[11px] text-gray-500">{dettaglio}</p>}
    </div>
  </div>
);

/**
 * Salute del sistema, in fondo al Global: informazione da consultare, non da
 * sorvegliare (scelta di David, 04/09).
 *
 * Il disco sta per primo perche' e' l'unico guasto che non da' alcun segnale
 * finche' non e' troppo tardi, e che quando esplode si presenta con la faccia di
 * una corruzione del database (NOTE/112): il 4 settembre era al 97%, a un giorno
 * e mezzo dal blocco, e nessun allarme lo copriva.
 */
export const SystemHealthPanel: FC<{ stats: OperationalStats | null; status: AgentStatus | null }> = ({ stats, status }) => {
  const d = stats?.disk ?? null;
  // Le soglie arrivano dal backend (risk.yaml), le stesse che fanno scattare
  // l'allarme: se il pannello ne usasse di proprie, potrebbe mostrare verde
  // mentre la notifica sta gia' suonando — due verita' diverse sulla stessa
  // cosa. I valori di ripiego servono solo a un backend piu' vecchio.
  const soglieAvviso = d?.warn_pct ?? 85;
  const soglieCritica = d?.critical_pct ?? 92;
  const tono = d == null
    ? null
    : d.used_pct >= soglieCritica
      ? { testo: 'text-accent-red', barra: 'bg-accent-red', punto: 'bg-accent-red' }
      : d.used_pct >= soglieAvviso
        ? { testo: 'text-accent-yellow', barra: 'bg-accent-yellow', punto: 'bg-accent-yellow' }
        : { testo: 'text-gray-300', barra: 'bg-accent-green', punto: 'bg-accent-green' };

  const problemi = stats?.degraded_reasons ?? null;
  const veloce = etaTick(status?.fast_loop_last_tick);
  const lento = etaTick(status?.slow_loop_last_tick);

  return (
    <section className="rounded-xl border border-dark-600 bg-dark-800 px-4 py-3">
      <p className="mb-2 text-sm font-bold text-white">Salute del sistema</p>

      {d && tono ? (
        <div className="py-1.5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className={`h-1.5 w-1.5 rounded-full ${tono.punto}`} />
              <span className="text-xs text-gray-400">Disco VPS</span>
            </div>
            <span className={`text-xs font-semibold ${tono.testo}`}>
              {d.used_pct}% · {(d.free_bytes / 1e9).toFixed(1)} GB liberi
            </span>
          </div>
          <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-dark-700">
            <div className={`h-full ${tono.barra}`} style={{ width: `${Math.min(100, d.used_pct)}%` }} />
          </div>
          {/* Un 97% da solo e' un numero: senza questa riga non dice cosa comporta. */}
          {d.used_pct >= soglieAvviso && (
            <p className="mt-1 text-[11px] text-accent-yellow">
              A disco pieno il database non riesce piu&apos; a scrivere: si presenta come una corruzione.
            </p>
          )}
        </div>
      ) : (
        <RigaSalute etichetta="Disco VPS" valore={null} />
      )}

      <div className="mt-1 border-t border-dark-700" />

      <RigaSalute
        etichetta="Database"
        valore={stats?.db_size_bytes != null ? `${Math.round(stats.db_size_bytes / 1e6)} MB` : null}
      />
      <RigaSalute
        etichetta="Cicli motore"
        valore={veloce || lento ? `veloce ${veloce?.testo ?? '—'} · lento ${lento?.testo ?? '—'}` : null}
        punto={veloce?.vecchio === false ? 'bg-accent-green' : 'bg-accent-yellow'}
      />
      <RigaSalute
        etichetta="Ultimo backup"
        valore={
          stats?.last_backup?.status == null
            ? null
            : stats.last_backup.status === 'ok' && stats.last_backup.integrity === 'ok'
              ? 'ok'
              : `${stats.last_backup.status}${stats.last_backup.integrity ? ` · integrita' ${stats.last_backup.integrity}` : ''}`
        }
        dettaglio={
          stats?.last_backup?.age_seconds != null
            ? `${Math.floor(stats.last_backup.age_seconds / 3600)}h fa`
            : null
        }
        punto={
          stats?.last_backup?.status == null
            ? undefined
            : stats.last_backup.status === 'ok' && stats.last_backup.integrity === 'ok'
              ? 'bg-accent-green'
              : 'bg-accent-red'
        }
        tono={stats?.last_backup?.status === 'ok' ? 'text-gray-300' : 'text-accent-red'}
      />
      <RigaSalute
        etichetta="Problemi attivi"
        valore={problemi == null ? null : problemi.length === 0 ? 'nessuno' : String(problemi.length)}
        dettaglio={problemi?.length ? problemi.map(leggiDegrado).join(' · ') : null}
        punto={problemi == null ? undefined : problemi.length ? 'bg-accent-red' : 'bg-accent-green'}
        tono={problemi?.length ? 'text-accent-red' : 'text-gray-300'}
      />
    </section>
  );
};

const AssetRank: FC<{ title: string; items: AssetBreakdownResponse['items']; tone?: SectionTone }> = ({ title, items, tone }) => (
  <section className="rounded-xl bg-dark-800 px-3 py-3">
    <SectionTitle tone={tone}>{title}</SectionTitle>
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

  // Wallet Aster (venue Perp): sola lettura. Il backend tiene una cache breve,
  // quindi il caricamento al montaggio non pesa sulla venue.
  const [aster, setAster] = useState<AsterWalletView | null>(null);
  useEffect(() => {
    let alive = true;
    fetchAsterWallet()
      .then((data) => { if (alive) setAster(data); })
      .catch(() => { if (alive) setAster(null); });
    return () => { alive = false; };
  }, []);

  return (
    <div className="space-y-4">

      {/* ── SUMMARY ── */}
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Spot" value={String(spot?.open_positions.length ?? 0)} />
        <Stat label="Perp" value={String(perp?.open_positions.length ?? 0)} />
        <Stat label="PnL aperto" value={fmtUsd(totalPnl)} tone={totalPnl >= 0 ? 'good' : 'bad'} />
      </div>

      {/* ── ASTER · venue Perp ── */}
      {aster?.configured && (
        <section className="space-y-2">
          <SectionTitle>
            Aster · venue Perp{aster.subaccount_name ? ` · ${aster.subaccount_name}` : ''}
          </SectionTitle>
          <div className="rounded-xl bg-dark-800 px-4 py-3 space-y-2">
            {/* Indirizzo per intero: e' qui che vanno versati i fondi. */}
            <button
              onClick={() => aster.subaccount_address && copyAddress(aster.subaccount_address)}
              className="w-full text-left rounded-lg bg-dark-900 px-3 py-2"
            >
              <p className="text-[11px] text-gray-500">Sub-account · qui vanno versati i fondi</p>
              <p className="font-mono text-xs text-gray-300 break-all leading-relaxed">{aster.subaccount_address}</p>
              <p className="mt-0.5 text-[11px] text-accent-blue">
                {copied === aster.subaccount_address ? '✓ Copiato' : 'Tocca per copiare'}
              </p>
            </button>

            <div className="flex items-center justify-between rounded-lg bg-dark-900 px-3 py-2">
              <div>
                <p className="text-sm font-semibold text-white">Saldo su Aster</p>
                <p className="text-[11px] text-gray-500">
                  wallet API {aster.api_wallet_address_short} · solo firma
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-white">
                  {aster.reachable ? `${aster.total_balance_usdt ?? '0.00'} USDT` : '—'}
                </p>
                <p className="text-[11px] text-gray-500">
                  {aster.open_positions != null ? `${aster.open_positions} posizioni` : ''}
                </p>
              </div>
            </div>

            {aster.reachable && aster.balances.length === 0 && (
              <p className="text-[11px] text-gray-500 px-1">
                Nessun asset: il sub-account non è ancora finanziato.
              </p>
            )}
            {aster.error && <p className="text-[11px] text-accent-red px-1">{aster.error}</p>}
          </div>
        </section>
      )}

      {/* ── WALLET ATTIVO ── */}
      <section className="space-y-2">
        <SectionTitle>
          Wallet attivo · {execWallets?.network ?? '—'} (chain {execWallets?.chain_id ?? '—'})
        </SectionTitle>
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
        <SectionTitle tone="strategia">
          Posizioni spot aperte {spot?.open_positions.length ? `(${fmtUsd(totalSpotValue)} valore)` : ''}
        </SectionTitle>
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
        <SectionTitle tone="strategia">
          Posizioni perp aperte {perp?.open_positions.length ? `(PnL ${fmtUsd(totalPerpPnl)})` : ''}
        </SectionTitle>
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
  const [ranking, setRanking] = useState<WatchlistRanking>({});

  useEffect(() => {
    void fetchSpotWatchlist().then(setSpotData).catch(() => undefined);
    void fetchPerpWatchlist().then(setPerpData).catch(() => undefined);
    // La GET master copre tutto l'universo eligible, quindi una sola chiamata
    // serve il ranking a tutte e tre le schede.
    void fetchAgentWatchlist().then((d) => setRanking(d.ranking ?? {})).catch(() => undefined);
  }, []);

  const normalizedQuery = query.trim().toUpperCase();
  const rankOf = (symbol: string): number | null => ranking[symbol.toUpperCase()]?.rank ?? null;
  // Ordine per capitalizzazione: chi non ha un rank finisce in fondo, in ordine
  // alfabetico, invece di mescolarsi alle prime posizioni.
  const byMarketCap = (symbols: string[]): string[] =>
    [...symbols].sort((a, b) => {
      const ra = rankOf(a);
      const rb = rankOf(b);
      if (ra != null && rb != null) return ra - rb;
      if (ra != null) return -1;
      if (rb != null) return 1;
      return a.localeCompare(b);
    });

  const masterTokens = byMarketCap(eligibleTokens.filter((s) => selectedAiSymbols.has(s.toUpperCase())));
  const filteredEligible = byMarketCap(eligibleTokens.filter((s) => s.toUpperCase().includes(normalizedQuery)));

  const spotSelected = useMemo(() => new Set((spotData?.selected_tokens ?? []).map((s) => s.toUpperCase())), [spotData]);
  const perpSelected = useMemo(() => new Set((perpData?.selected_tokens ?? []).map((s) => s.toUpperCase())), [perpData]);

  const handleMarketToggle = async (symbol: string, market: 'spot' | 'perp') => {
    if (!adminToken || marketSaving) return;
    setMarketSaving(true);
    setMarketError('');
    try {
      // La PUT risponde con la sola selezione: la disponibilità va riportata
      // dallo stato precedente, altrimenti i badge sparirebbero a ogni tocco.
      if (market === 'spot') {
        const current = new Set(spotData?.selected_tokens ?? []);
        if (current.has(symbol)) current.delete(symbol); else current.add(symbol);
        const result = await updateSpotWatchlist([...current], adminToken);
        setSpotData((prev) => ({ ...result, availability: result.availability ?? prev?.availability }));
      } else {
        const current = new Set(perpData?.selected_tokens ?? []);
        if (current.has(symbol)) current.delete(symbol); else current.add(symbol);
        const result = await updatePerpWatchlist([...current], adminToken);
        setPerpData((prev) => ({ ...result, availability: result.availability ?? prev?.availability }));
      }
    } catch (e) {
      // Il messaggio del backend va mostrato: con un catch muto un 400
      // "Assets not in the master watchlist: TRX" diventava un generico
      // "Errore salvataggio watchlist" e la causa restava invisibile.
      const detail = e instanceof Error ? e.message : String(e);
      setMarketError(`Errore salvataggio watchlist — ${detail}`);
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
            <SectionTitle>Selezionate</SectionTitle>
            {masterTokens.length > 0 ? (
              <div className="grid grid-cols-2 gap-2">
                {masterTokens.map((symbol) => (
                  <TokenToggle key={`sel-${symbol}`} symbol={symbol} selected disabled={disabled} onToggle={onToggle} rank={rankOf(symbol)} />
                ))}
              </div>
            ) : (
              <EmptyState title="Nessuna coin attiva" detail="Seleziona una coin tradabile per passarla all'agente." />
            )}
          </section>
          <section className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <SectionTitle>Eligible</SectionTitle>
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
                <TokenToggle key={symbol} symbol={symbol} selected={selectedAiSymbols.has(symbol.toUpperCase())} disabled={disabled} onToggle={onToggle} rank={rankOf(symbol)} />
              ))}
            </div>
            {filteredEligible.length === 0 && <EmptyState title="Nessun token trovato" detail="La ricerca filtra solo l'universo eligible." />}
          </section>
        </>
      )}

      {(subTab === 'spot' || subTab === 'perp') && (() => {
        const isSpot = subTab === 'spot';
        const selected = isSpot ? spotSelected : perpSelected;
        const activeMasterTokens = masterTokens.filter((s) => s.toUpperCase().includes(normalizedQuery));  // masterTokens e' gia' ordinata per capitalizzazione
        // Disponibilità: sempre dal backend. Se il campo manca (venue non
        // raggiungibile) si ricade su "unknown", che avvisa senza bloccare.
        const availabilityMap = (isSpot ? spotData : perpData)?.availability;
        const availabilityFor = (symbol: string): VenueAvailability => {
          const entry = availabilityMap?.[symbol.toUpperCase()];
          const value = isSpot ? entry?.spot : entry?.perp;
          return value ?? { venue: isSpot ? 'pancakeswap' : 'aster', status: 'unknown' };
        };
        const blockedCount = activeMasterTokens.filter(
          (s) => availabilityFor(s).status === 'unavailable' && !selected.has(s.toUpperCase()),
        ).length;
        return (
          <section className="space-y-2">
            <p className="px-1 text-xs text-gray-500">
              Seleziona le coin dalla master watchlist da assegnare al mercato <span className="font-semibold text-white">{subTab.toUpperCase()}</span>.
              {' '}Venue: <span className="font-semibold text-white">{isSpot ? 'PancakeSwap' : 'Aster'}</span>.
            </p>
            {blockedCount > 0 && (
              <p className="px-1 text-xs text-accent-red">
                {blockedCount} {blockedCount === 1 ? 'coin non è quotata' : 'coin non sono quotate'} su {isSpot ? 'PancakeSwap' : 'Aster'}: non selezionabili.
              </p>
            )}
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
                    availability={availabilityFor(symbol)}
                    rank={rankOf(symbol)}
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

type SetupTab = 'generale' | 'spot' | 'perp' | 'sistema';

const SETUP_TABS: Array<{ id: SetupTab; label: string }> = [
  { id: 'generale', label: 'Generale' },
  { id: 'spot', label: 'Spot' },
  { id: 'perp', label: 'Perp' },
  { id: 'sistema', label: 'Sistema' },
];

export const SetupPane: FC<{
  settings: AgentMobileSettings;
  onSettings: (settings: AgentMobileSettings) => void;
  adminToken: string;
  onAdminToken: (value: string) => void;
  validation: CredentialValidationResponse | null;
  agentStatus: AgentStatus | null;
  saving: boolean;
  actionError: string;
  dirty: boolean;
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
  dirty,
  onSave,
  onValidate,
  onKill,
  onCloseAll,
  onAdjustEquity,
}) => {
  const patch = (partial: Partial<AgentMobileSettings>) => onSettings({ ...settings, ...partial });
  // Sotto-schede del setup: separano i parametri per mercato (stesso schema di CoinsPane).
  // I settings restano un unico oggetto: cambiare scheda non tocca né i valori né il dirty.
  const [setupTab, setSetupTab] = useState<SetupTab>(agentCache.setupTab);
  useEffect(() => { agentCache.setupTab = setupTab; }, [setupTab]);
  const [equityInput, setEquityInput] = useState('');
  const equityValue = Number(equityInput);
  const equityValid = equityInput.trim() !== '' && Number.isFinite(equityValue) && equityValue !== 0;

  // Verifica del token contro il backend, con debounce sulla digitazione.
  // Senza feedback il token "restava li'" senza dire se era stato accettato.
  const [adminCheck, setAdminCheck] = useState<'idle' | 'checking' | 'valid' | 'invalid' | 'unreachable'>('idle');
  useEffect(() => {
    if (!adminToken) { setAdminCheck('idle'); return; }
    setAdminCheck('checking');
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const ok = await verifyAdminToken(adminToken);
        if (!cancelled) setAdminCheck(ok ? 'valid' : 'invalid');
      } catch {
        if (!cancelled) setAdminCheck('unreachable');
      }
    }, 600);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [adminToken]);

  return (
    <div className="space-y-4">
      {/* Fuori dalle schede: deve restare a portata da qualunque punto del setup. */}
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
        {/* Prima lo stato, poi il comando. Il pulsante "Riprendi" restava visibile ma
            disabilitato anche ad agente attivo: sembrava un bottone rotto invece che
            uno stato, e durante il drawdown del 19/08 ha fatto credere a David che
            l'agente fosse fermo. Ora il badge dice come sta, e si vede solo il comando
            che ha senso premere adesso. */}
        <div className="flex items-center gap-2 rounded-lg bg-dark-900/60 px-3 py-2">
          <span
            className={`h-2 w-2 flex-shrink-0 rounded-full ${
              agentStatus?.kill_switch === 'running' ? 'bg-accent-green' : 'bg-accent-yellow'
            }`}
          />
          <span
            className={`text-xs font-bold uppercase tracking-wide ${
              agentStatus?.kill_switch === 'running' ? 'text-accent-green' : 'text-accent-yellow'
            }`}
          >
            {agentStatus?.kill_switch === 'running' ? 'Agente attivo' : 'Agente in pausa'}
          </span>
        </div>
        {agentStatus?.kill_switch !== 'running' && (
          <button
            onClick={() => onKill('running')}
            disabled={!adminToken || saving}
            className="w-full rounded-lg bg-accent-green/20 px-3 py-2.5 text-sm font-semibold text-accent-green disabled:opacity-40"
          >
            ▶ Riprendi agente
          </button>
        )}
        {!adminToken && <p className="text-xs text-gray-600">Richiede admin token salvato.</p>}
      </section>

      <div className="grid grid-cols-4 gap-1">
        {SETUP_TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setSetupTab(t.id)}
            className={`rounded-lg py-1.5 text-xs font-semibold transition-colors ${
              setupTab === t.id ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {setupTab === 'sistema' && (
        <>
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
        {adminCheck !== 'idle' && (
          <p className={`text-xs flex items-center gap-1.5 ${
            adminCheck === 'valid' ? 'text-accent-green'
            : adminCheck === 'invalid' ? 'text-accent-red'
            : 'text-gray-500'
          }`}>
            {adminCheck === 'checking' && (
              <>
                <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>
                Verifica del token…
              </>
            )}
            {adminCheck === 'valid' && '✓ Admin attivo — funzioni privilegiate sbloccate'}
            {adminCheck === 'invalid' && '✗ Token non valido: il backend lo rifiuta'}
            {adminCheck === 'unreachable' && 'Backend non raggiungibile — impossibile verificare ora'}
          </p>
        )}
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
        <h3 className="text-sm font-semibold text-white">
          Onboarding
          <HelpTip top text={'Controlla quali servizi esterni sono impostati sul backend:\n\nCMC — i prezzi delle monete\nClaude — il modello che valuta i segnali\nWallet — l\'indirizzo e la chiave per operare\nBSC RPC — il collegamento alla blockchain\nFCM — le notifiche push sul telefono\nTWAK — le credenziali dell\'exchange\nx402 — i pagamenti in USDC\n\nVerde "ready" = il valore c\'è. Rosso "missing" = manca.\n\nControlla solo che siano impostati, non che funzionino davvero. Richiede l\'admin token.'} />
        </h3>
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
        </>
      )}

      {setupTab === 'generale' && (
        <>
      <section className="space-y-3">
        <SectionTitle>General</SectionTitle>
        <div className="grid grid-cols-2 gap-3">
          <SelectInput label="Mode" help={'Quanta libertà ha l\'agente:\n\nConservative — solo i segnali migliori\nSemi-auto — più operazioni, filtri più larghi\nFull auto — massima autonomia'} value={settings.mode} onChange={(mode) => patch({ mode })} options={[
            { value: 'conservative', label: 'Conservative' },
            { value: 'semi_autonomous', label: 'Semi-auto' },
            { value: 'full_autonomous', label: 'Full auto' },
          ]} />
          <SelectInput label="Market" help={'Su quali mercati opera:\n\nSpot — compra la moneta vera, niente leva\nPerp — contratti con leva, guadagna anche al ribasso\nBoth — entrambi i mercati'} value={settings.markets_enabled} onChange={(markets_enabled) => patch({ markets_enabled })} options={[
            { value: 'spot', label: 'Spot' },
            { value: 'perp', label: 'Perp' },
            { value: 'both', label: 'Both' },
          ]} />
          <SelectInput label="Execution" help={'Se le operazioni sono reali o simulate:\n\nDry run — simulate, nessun soldo vero in gioco\nLive — ordini veri sull\'exchange'} value={settings.execution_mode} onChange={(execution_mode) => patch({ execution_mode })} options={[
            { value: 'dry_run', label: 'Dry-run' },
            { value: 'live', label: 'Live' },
          ]} />
          <NumberInput label="Test scaling %" help={'Riduce la dimensione di ogni operazione a questa percentuale. Serve per provare la strategia con importi ridotti: a 10% ogni trade vale un decimo del normale.'} value={settings.test_scaling_pct} onChange={(test_scaling_pct) => patch({ test_scaling_pct })} />
        </div>
      </section>

      <section className="space-y-3">
        <SectionTitle tone="filtri">Filtri globali</SectionTitle>
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Liquidità minima $" help={'Soglia di liquidità sotto la quale una coin viene scartata: sotto questa cifra il libro degli ordini è troppo sottile e il prezzo scivola quando si entra o si esce.'} value={settings.min_pool_liquidity_usd} step={1000} onChange={(min_pool_liquidity_usd) => patch({ min_pool_liquidity_usd })} />
        </div>
        <ToggleInput
          label="Filtro inversione mercato — Spot"
          help="Blocca le nuove entrate spot quando il mercato sta girando contro la direzione del segnale. Sullo spot ha senso: la strategia segue il trend, e questo evita di comprare proprio mentre si ribalta."
          checked={settings.spot_market_reversal_filter_enabled}
          onChange={(spot_market_reversal_filter_enabled) => patch({ spot_market_reversal_filter_enabled })}
        />
        <ToggleInput
          label="Filtro inversione mercato — Perp"
          help="Stesso filtro sul perp, dove però lavora al contrario: la strategia perp compra i rientri, e questo blocca i long proprio quando il prezzo scende. Misurato su BTC: tiene bloccata una direzione o l'altra il 99,7% del tempo. Default spento."
          checked={settings.perp_market_reversal_filter_enabled}
          onChange={(perp_market_reversal_filter_enabled) => patch({ perp_market_reversal_filter_enabled })}
        />
      </section>

      <section className="space-y-3">
        <SectionTitle tone="rischio">Risk globale</SectionTitle>
        <ToggleInput
          label="Allarme drawdown"
          help={'Manda una notifica quando la perdita dal massimo raggiunto supera la soglia. Non ferma nulla: avvisa e basta.'} checked={settings.drawdown_alert_enabled}
          onChange={(drawdown_alert_enabled) => patch({ drawdown_alert_enabled })}
        />
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Daily loss %" help="Perdita massima in una giornata, in percentuale sul capitale. Raggiunta la soglia l'agente smette di aprire nuove posizioni fino al giorno dopo. Si scrive negativa: −8 significa −8%." value={settings.daily_loss_limit_pct} onChange={(daily_loss_limit_pct) => patch({ daily_loss_limit_pct })} />
          <NumberInput label="Drawdown cap %" help={'Perdita massima tollerata dal picco di capitale. Superata, l\'agente si ferma del tutto e non riapre finché non lo riavvii tu. Si scrive negativa: −15 significa −15%.'} value={settings.drawdown_cap_pct} onChange={(drawdown_cap_pct) => patch({ drawdown_cap_pct })} />
        </div>
      </section>

      <section className="space-y-3">
        <SectionTitle>Grafico trade</SectionTitle>
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Candele post-chiusura (0=off)" help={'Quante candele mostrare nel grafico dopo la chiusura di un trade, per vedere com\'è andata dopo l\'uscita. Zero le nasconde. Massimo 288 (24 ore a 5 minuti).'} value={settings.post_close_candles} step={1} min={0} max={288} onChange={(post_close_candles) => patch({ post_close_candles: Math.round(post_close_candles) })} />
          <NumberInput label="Candele prima dell'apertura" help={'Quante candele di contesto mostrare prima dell\'ingresso del trade. Massimo 288 (24 ore a 5 minuti). Non tocca il calcolo dello stop, solo il grafico.'} value={settings.chart_pre_open_candles} step={1} min={1} max={288} onChange={(chart_pre_open_candles) => patch({ chart_pre_open_candles: Math.round(chart_pre_open_candles) })} />
        </div>
      </section>
        </>
      )}

      {setupTab === 'spot' && (
        <>
      <section className="space-y-3">
        <SectionTitle tone="rischio">Spot — risk</SectionTitle>
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Size %" help={'Quanta parte del capitale impegnare in ogni singola operazione spot. Al 4% con 1000$ investi 40$ per trade.'} value={settings.spot_capital_per_trade_pct} onChange={(spot_capital_per_trade_pct) => patch({ spot_capital_per_trade_pct })} />
          <NumberInput label="Rischio %" help={'Quanto sei disposto a perdere su una singola operazione, in percentuale sul capitale. Da qui viene calcolata la dimensione della posizione: rischio più basso, posizione più piccola.'} value={settings.spot_per_trade_pct} step={0.1} onChange={(spot_per_trade_pct) => patch({ spot_per_trade_pct })} />
          <NumberInput label="Max posizioni" help={'Quante posizioni spot possono restare aperte insieme. Più alto significa più diversificazione ma anche più capitale immobilizzato.'} value={settings.spot_max_open_positions} onChange={(spot_max_open_positions) => patch({ spot_max_open_positions })} />
          <NumberInput label="Exposure %" help={'Tetto al capitale investito in tutte le posizioni spot sommate. Impedisce di ritrovarsi con tutto il capitale sul mercato nello stesso momento.'} value={settings.spot_max_exposure_pct} onChange={(spot_max_exposure_pct) => patch({ spot_max_exposure_pct })} />
          <NumberInput label="Slippage %" help={'Scarto massimo accettato fra il prezzo previsto e quello di esecuzione. Oltre questa soglia l\'ordine viene annullato invece di essere eseguito a un prezzo peggiore.'} value={settings.spot_max_slippage_pct} step={0.1} onChange={(spot_max_slippage_pct) => patch({ spot_max_slippage_pct })} />
          <NumberInput label="Cooldown min" help={'Minuti di attesa prima di riaprire sullo stesso asset dopo una chiusura. Evita di rientrare subito sullo stesso movimento.'} value={settings.spot_cooldown_minutes} onChange={(spot_cooldown_minutes) => patch({ spot_cooldown_minutes })} />
        </div>
      </section>

      <section className="space-y-3">
        <SectionTitle tone="strategia">Spot — strategia</SectionTitle>
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Confidence" help={'Quanto deve essere forte un segnale per essere accettato. Alzarlo riduce le operazioni ma tiene solo le più convincenti.'} value={settings.spot_confidence_threshold} step={0.01} onChange={(spot_confidence_threshold) => patch({ spot_confidence_threshold })} />
          <NumberInput label="Vol trigger %" help={'Movimento minimo di prezzo perché una situazione venga considerata un\'occasione. Sotto questa soglia il mercato è troppo fermo per operare.'} value={settings.spot_volatility_trigger_pct} onChange={(spot_volatility_trigger_pct) => patch({ spot_volatility_trigger_pct })} />
          <NumberInput label="Rel volume" help={'Quante volte il volume deve superare la sua media per confermare il segnale. A 1.5 serve volume una volta e mezza il normale: filtra i movimenti senza partecipazione.'} value={settings.spot_relative_volume_threshold} step={0.1} onChange={(spot_relative_volume_threshold) => patch({ spot_relative_volume_threshold })} />
          <NumberInput label="ATR stop" help={'Distanza dello stop loss dall\'ingresso, misurata in ATR (la volatilità media). Più alto significa stop più largo: meno stop presi per caso, ma perdite più grandi quando scatta.'} value={settings.spot_atr_stop_multiplier} step={0.1} onChange={(spot_atr_stop_multiplier) => patch({ spot_atr_stop_multiplier })} />
          <NumberInput label="Buffer Min20 %" help={'Cuscinetto sotto il minimo delle ultime candele, quando lo stop è di tipo strutturale. Serve a non farsi prendere lo stop per un soffio.'} value={settings.spot_structural_stop_buffer_pct} step={0.1} onChange={(spot_structural_stop_buffer_pct) => patch({ spot_structural_stop_buffer_pct })} />
          <NumberInput label="N° candele per calcolo stop" help={'Su quante candele cercare il minimo che fa da stop strutturale. Poche candele = stop vicino, esce prima; molte = stop largo, lascia respirare. Nessun rapporto con le candele mostrate nel grafico.'} value={settings.spot_structural_stop_lookback_candles} step={1} onChange={(spot_structural_stop_lookback_candles) => patch({ spot_structural_stop_lookback_candles: Math.round(spot_structural_stop_lookback_candles) })} />
          <NumberInput label="Chiudi a TP1 %" help={'Quanta parte della posizione chiudere al primo obiettivo. Al 50% incassi metà e lasci correre il resto.'} value={settings.spot_tp1_close_pct} step={5} onChange={(spot_tp1_close_pct) => patch({ spot_tp1_close_pct })} />
          <NumberInput label="Time Stop ore" help={'Dopo quante ore chiudere una posizione che non è andata né a target né a stop. Libera capitale bloccato in operazioni che non si muovono.'} value={settings.spot_time_stop_hours} step={1} onChange={(spot_time_stop_hours) => patch({ spot_time_stop_hours: Math.round(spot_time_stop_hours) })} />
          <SelectInput label="Fee mode (dry-run)" help={'Quali costi simulare nel dry run:\n\nSwap fee + Slippage — realistico, 0.15%\nNessuna — strategia lorda, senza costi'} value={settings.spot_fee_mode} onChange={(v) => patch({ spot_fee_mode: v as 'all' | 'none' })} options={[
            { value: 'all', label: 'Swap fee + Slippage — 0.15%' },
            { value: 'none', label: 'Nessuna (strategia lorda)' },
          ]} />
        </div>
      </section>

      <section className="space-y-3">
        <SectionTitle tone="protezioni">Spot — protezioni</SectionTitle>
        <ToggleInput
          label="Breakeven Spot"
          help={'Sposta lo stop al prezzo d\'ingresso quando il trade è in guadagno, così l\'operazione non può più chiudere in perdita.'} checked={settings.spot_breakeven_enabled}
          onChange={(spot_breakeven_enabled) => patch({ spot_breakeven_enabled })}
        />
        <SelectInput
          label="Modalità breakeven Spot"
          help={'Quando spostare lo stop a pareggio:\n\nATR — appena il guadagno raggiunge la soglia di volatilità\nSolo dopo TP1 — solo dopo aver incassato il primo obiettivo'} value={settings.spot_breakeven_mode}
          onChange={(v) => patch({ spot_breakeven_mode: v })}
          options={[
            { value: 'atr', label: 'ATR (attuale)' },
            { value: 'tp1', label: 'Solo dopo TP1' },
          ]}
        />
        <SelectInput
          label="Stop Loss Spot"
          help={'Come calcolare lo stop loss:\n\nATR — distanza fissa basata sulla volatilità\nMinimo 20 candele — sotto il minimo recente, stop più largo e più aderente al grafico'} value={settings.spot_sl_mode}
          onChange={(v) => patch({ spot_sl_mode: v })}
          options={[
            { value: 'atr', label: 'ATR (attuale)' },
            { value: 'lowest', label: 'Minimo 20 candele' },
          ]}
        />
        <ToggleInput
          label="Trailing Stop Spot"
          help={'Fa salire lo stop dietro al prezzo mentre il trade guadagna, per proteggere il profitto già maturato. Lo stop non scende mai.'} checked={settings.spot_trailing_enabled}
          onChange={(spot_trailing_enabled) => patch({ spot_trailing_enabled })}
        />
        <ToggleInput
          label="Time Stop Spot"
          help={'Attiva la chiusura per tempo scaduto. Le ore si impostano nella sezione strategia.'} checked={settings.spot_time_stop_enabled}
          onChange={(spot_time_stop_enabled) => patch({ spot_time_stop_enabled })}
        />
      </section>
        </>
      )}

      {setupTab === 'perp' && (
        <>
      <section className="space-y-3">
        <SectionTitle tone="rischio">Perp — risk</SectionTitle>
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Size % (margine)" help={'Quanto margine impegnare in ogni operazione, in percentuale sul capitale. Con la leva il valore controllato sul mercato è molto più grande del margine.'} value={settings.perp_capital_per_trade_pct} onChange={(perp_capital_per_trade_pct) => patch({ perp_capital_per_trade_pct })} />
          <NumberInput label="Rischio %" help={'Quanto sei disposto a perdere su un singolo trade. Da qui si calcola la dimensione: la perdita allo stop resta questa cifra, qualunque sia la leva.'} value={settings.perp_per_trade_pct} step={0.1} onChange={(perp_per_trade_pct) => patch({ perp_per_trade_pct })} />
          <NumberInput label="Max posizioni" help={'Quante posizioni perp possono restare aperte insieme.'} value={settings.perp_max_open_positions} onChange={(perp_max_open_positions) => patch({ perp_max_open_positions })} />
          <NumberInput label="Exposure %" help={'Tetto al margine impegnato in tutte le posizioni perp sommate.'} value={settings.perp_max_exposure_pct} onChange={(perp_max_exposure_pct) => patch({ perp_max_exposure_pct })} />
          <NumberInput label="Slippage %" help={'Scarto massimo accettato fra prezzo previsto ed effettivo. Oltre, l\'ordine viene annullato.'} value={settings.perp_max_slippage_pct} step={0.1} onChange={(perp_max_slippage_pct) => patch({ perp_max_slippage_pct })} />
          <NumberInput label="Cooldown min" help={'Minuti di attesa prima di riaprire sullo stesso asset dopo una chiusura.'} value={settings.perp_cooldown_minutes} onChange={(perp_cooldown_minutes) => patch({ perp_cooldown_minutes })} />
          <ToggleInput label="Margine fisso Perp" help={'Usa sempre lo stesso margine in dollari per ogni trade, invece di calcolarlo in percentuale sul capitale.'} checked={settings.perp_fixed_margin_enabled} onChange={(perp_fixed_margin_enabled) => patch({ perp_fixed_margin_enabled })} />
          <NumberInput label="Margine fisso $" help={'Il margine fisso in dollari per ogni operazione, quando l\'opzione qui sopra è accesa.'} value={settings.perp_fixed_margin_usd} onChange={(perp_fixed_margin_usd) => patch({ perp_fixed_margin_usd })} />
        </div>
      </section>

      <section className="space-y-3">
        <SectionTitle tone="strategia">Perp — strategia</SectionTitle>
        <div className="grid grid-cols-2 gap-3">
          <SelectInput label="Direction" help={'In che direzione può operare:\n\nLong e short — sfrutta salite e discese\nSolo long — apre solo al rialzo\nSolo short — apre solo al ribasso'} value={settings.perp_direction_mode} onChange={(perp_direction_mode) => patch({ perp_direction_mode })} options={[
            { value: 'long_only', label: 'Long' },
            { value: 'short_only', label: 'Short' },
            { value: 'long_short', label: 'Both' },
          ]} />
          <NumberInput label="Leva min (alta vol.)" help={'Leva usata quando la volatilità è alta. Mercato agitato, leva bassa: si rischia meno su movimenti ampi.'} value={settings.perp_min_leverage} onChange={(perp_min_leverage) => patch({ perp_min_leverage })} />
          <NumberInput label="Leva max (bassa vol.)" help={'Leva usata quando la volatilità è bassa. Mercato calmo, leva alta: serve più leva per un guadagno sensato.'} value={settings.perp_max_leverage} onChange={(perp_max_leverage) => patch({ perp_max_leverage })} />
          <NumberInput label="Value area %" help={'Quanta parte del volume definisce la zona di prezzo dove il mercato ha scambiato di più. Il segnale nasce ai bordi di questa zona.'} value={settings.perp_value_area_pct} onChange={(perp_value_area_pct) => patch({ perp_value_area_pct })} />
          <NumberInput label="ATR stop" help={'Distanza dello stop dall\'ingresso in ATR, quando lo stop è di tipo ATR. Più alto, stop più largo.'} value={settings.perp_atr_stop_multiplier} step={0.1} onChange={(perp_atr_stop_multiplier) => patch({ perp_atr_stop_multiplier })} />
          <NumberInput label="Buffer Min/Max20 %" help={'Cuscinetto oltre il minimo (o massimo) recente, quando lo stop è strutturale. Evita di farsi prendere lo stop per un soffio.'} value={settings.perp_structural_stop_buffer_pct} step={0.1} onChange={(perp_structural_stop_buffer_pct) => patch({ perp_structural_stop_buffer_pct })} />
          <NumberInput label="N° candele per calcolo stop" help={'Su quante candele cercare il minimo (o massimo) che fa da stop strutturale. Poche candele = stop vicino, esce prima; molte = stop largo, lascia respirare. Nessun rapporto con le candele mostrate nel grafico.'} value={settings.perp_structural_stop_lookback_candles} step={1} onChange={(perp_structural_stop_lookback_candles) => patch({ perp_structural_stop_lookback_candles: Math.round(perp_structural_stop_lookback_candles) })} />
          <NumberInput label="Filtro R:R min (0=off)" help={'Rapporto minimo fra guadagno atteso al primo obiettivo e perdita allo stop. A 1.2 servono almeno 1.2 di guadagno per 1 di rischio, altrimenti il segnale viene scartato. Zero disattiva il filtro.'} value={settings.perp_min_rr} step={0.1} onChange={(perp_min_rr) => patch({ perp_min_rr })} />
          <NumberInput label="TP1 (× ATR)" help={'Distanza del primo obiettivo dall\'ingresso, in ATR. Più basso significa incassare prima ma meno.'} value={settings.perp_tp1_atr_multiplier} step={0.1} onChange={(perp_tp1_atr_multiplier) => patch({ perp_tp1_atr_multiplier })} />
          <NumberInput label="TP2 (× ATR)" help={'Distanza del secondo obiettivo, in ATR. È il traguardo del residuo dopo il primo incasso.'} value={settings.perp_tp2_atr_multiplier} step={0.1} onChange={(perp_tp2_atr_multiplier) => patch({ perp_tp2_atr_multiplier })} />
          <div className="col-span-2">
            <ToggleInput
              label="Trailing Stop Perp"
              help={'Interruttore generale del trailing sul perp: da spento, lo stop non insegue mai il prezzo, nemmeno con la protezione qui sotto impostata su Trailing ATR. Il Profit Lock continua invece a funzionare.'}
              checked={settings.perp_trailing_enabled}
              onChange={(perp_trailing_enabled) => patch({ perp_trailing_enabled })}
            />
          </div>
          <SelectInput label="Protezione profitto (post-TP1)" help={'Come proteggere il profitto dopo il primo incasso:\n\nOff — nessuna protezione\nTrailing ATR — lo stop insegue il prezzo\nProfit Lock — uscite parziali a scalini fra i due obiettivi'} value={settings.perp_protection_mode} onChange={(v) => patch({ perp_protection_mode: v as 'off' | 'trailing' | 'profit_lock' })} options={[
            { value: 'off', label: 'Off — solo breakeven' },
            { value: 'trailing', label: 'Trailing ATR' },
            { value: 'profit_lock', label: 'Profit Lock (ratchet)' },
          ]} />
          {settings.perp_protection_mode === 'trailing' && (
            <SelectInput label="Trailing ATR (adatta alla leva)" help={'Quanto stretto insegue il trailing:\n\nLargo — lascia respirare, esce più tardi\nStretto — protegge prima, ma esce sui rimbalzi'} value={settings.perp_trailing_mode} onChange={(v) => patch({ perp_trailing_mode: v as 'largo' | 'stretto' })} options={[
              { value: 'largo', label: 'Largo — lascia correre' },
              { value: 'stretto', label: 'Stretto — blocca prima' },
            ]} />
          )}
          {settings.perp_protection_mode === 'trailing' && (
            <NumberInput label="Trailing dist. % (0=solo ATR)" help={'Distanza fissa del trailing in percentuale. A zero il trailing usa solo l\'ATR.'} value={settings.perp_trailing_pnl_pct} step={0.1} onChange={(perp_trailing_pnl_pct) => patch({ perp_trailing_pnl_pct })} />
          )}
          <NumberInput label="Chiudi a TP1 %" help={'Quanta parte della posizione chiudere al primo obiettivo. Il resto prosegue verso il secondo, gestito dalla protezione scelta qui sotto.'} value={settings.perp_tp1_close_pct} step={5} onChange={(perp_tp1_close_pct) => patch({ perp_tp1_close_pct })} />
          <NumberInput label="Time Stop ore" help={'Dopo quante ore chiudere una posizione ferma, che non ha raggiunto né obiettivo né stop.'} value={settings.perp_time_stop_hours} step={1} onChange={(perp_time_stop_hours) => patch({ perp_time_stop_hours: Math.round(perp_time_stop_hours) })} />
          <SelectInput label="Fee mode (dry-run)" help={'Quali costi simulare nel dry run:\n\nTaker — ordini a mercato, 0.06%\nMaker — ordini limite, 0.02%\nNessuna — strategia lorda'} value={settings.perp_fee_mode} onChange={(v) => patch({ perp_fee_mode: v as 'taker' | 'maker' | 'none' })} options={[
            { value: 'taker', label: 'Taker (market) — 0.06%' },
            { value: 'maker', label: 'Maker (limit) — 0.02%' },
            { value: 'none', label: 'Nessuna (strategia lorda)' },
          ]} />
        </div>
        {settings.perp_protection_mode === 'profit_lock' && (
          <div className="space-y-2 rounded-lg border border-gray-700 p-3">
            <p className="text-xs font-semibold text-gray-400">Scalini ratchet — punto del tratto TP1→TP2 → quota del residuo da chiudere</p>
            {settings.perp_profit_lock_steps.map((stepPair, i) => (
              <div key={i} className="grid grid-cols-2 gap-3">
                <NumberInput label={`Livello ${i + 1} (%)`} help={'A che punto del tratto fra primo e secondo obiettivo scatta questo scalino.\n\nAl 50% è a metà strada, al 95% quasi al traguardo.'} value={Math.round(stepPair[0] * 100)} step={5} onChange={(v) => {
                  const next = settings.perp_profit_lock_steps.map((s, j) => (j === i ? [Math.max(0, Math.min(100, v)) / 100, s[1]] : s)) as Array<[number, number]>;
                  patch({ perp_profit_lock_steps: next });
                }} />
                <NumberInput label={`Chiudi ${i + 1} (%)`} help={'Quanta parte del residuo risulta chiusa in totale a questo scalino.\n\nLe quote sono cumulative: 25 poi 50 vuol dire chiudere un quarto e poi arrivare a metà, non un quarto e poi un altro mezzo.'} value={Math.round(stepPair[1] * 100)} step={5} onChange={(v) => {
                  const next = settings.perp_profit_lock_steps.map((s, j) => (j === i ? [s[0], Math.max(0, Math.min(100, v)) / 100] : s)) as Array<[number, number]>;
                  patch({ perp_profit_lock_steps: next });
                }} />
              </div>
            ))}
            <p className="text-xs text-gray-500">
              Livelli e quote crescenti. Le quote sono <span className="text-gray-400">cumulative</span> sul residuo rimasto dopo il TP1:
              50→25 / 70→50 / 95→80 significa che al 95% del tratto si è chiuso l'80% in tutto, e il 20% corre verso il TP2.
            </p>
            <div className="grid grid-cols-2 gap-3 border-t border-gray-700 pt-3">
              <NumberInput label="Breakeven ratchet (% del tratto)" help={'Dove si ferma tutto se il prezzo torna indietro, in percentuale del tratto fra primo e secondo obiettivo. Al 50% chiude a metà strada.'} value={settings.perp_ratchet_breakeven_pct} step={5}
                onChange={(v) => patch({ perp_ratchet_breakeven_pct: Math.max(0, Math.min(100, v)) })} />
              <NumberInput label="Si arma dallo scalino n." help={'Da quale scalino in poi si arma quella protezione. Prima di quello scalino restano attivi solo stop loss e breakeven normale.'} value={settings.perp_ratchet_breakeven_after_step} step={1}
                onChange={(v) => patch({ perp_ratchet_breakeven_after_step: Math.max(1, Math.min(settings.perp_profit_lock_steps.length, Math.round(v))) })} />
            </div>
            <p className="text-xs text-gray-500">Raggiunto quello scalino, un rientro chiude tutto a quel punto del tratto TP1→TP2.</p>
            <div className="border-t border-gray-700 pt-3">
              <ToggleInput label="Lascia correre oltre il TP2" help={'Se il prezzo supera il secondo obiettivo di slancio non chiude: lascia correre il residuo con un trailing. Se invece lo tocca esatto, chiude come sempre.'} checked={settings.perp_ratchet_run_beyond_tp2}
                onChange={(v) => patch({ perp_ratchet_run_beyond_tp2: v })} />
              {settings.perp_ratchet_run_beyond_tp2 && (
                <div className="mt-2">
                  <NumberInput label="Trailing oltre TP2 (% dal massimo)" help={'Quanto sta lontano il trailing dal massimo raggiunto, oltre il secondo obiettivo. All\'1% chiude appena il prezzo rientra dell\'1% dal picco.'} value={settings.perp_ratchet_trailing_pct} step={0.5}
                    onChange={(v) => patch({ perp_ratchet_trailing_pct: Math.max(0.1, Math.min(20, v)) })} />
                </div>
              )}
              <p className="mt-1 text-xs text-gray-500">
                Se il prezzo supera il TP2 di slancio non si chiude: parte un trailing a questa distanza dal massimo raggiunto.
                Toccando il TP2 esatto, invece, si chiude come sempre.
              </p>
            </div>
          </div>
        )}
        <p className="px-1 text-xs text-gray-500">
          Leva modulata sulla volatilità ATR(72) in apertura: bassa volatilità → leva max, alta volatilità → leva min. Volatilità anomala (oltre il massimo storico) → leva forzata al minimo. Range 1–50.
        </p>
      </section>

      <section className="space-y-3">
        <SectionTitle tone="protezioni">Perp — protezioni</SectionTitle>
        <ToggleInput
          label="Breakeven Perp"
          help={'Sposta lo stop al prezzo d\'ingresso quando il trade è in guadagno: da lì in poi l\'operazione non può più chiudere in perdita.'} checked={settings.perp_breakeven_enabled}
          onChange={(perp_breakeven_enabled) => patch({ perp_breakeven_enabled })}
        />
        <SelectInput
          label="Modalità breakeven Perp"
          help={'Quando spostare lo stop a pareggio:\n\nATR — appena il guadagno raggiunge la soglia di volatilità\nSolo dopo TP1 — solo dopo il primo incasso'} value={settings.perp_breakeven_mode}
          onChange={(v) => patch({ perp_breakeven_mode: v })}
          options={[
            { value: 'atr', label: 'ATR (attuale)' },
            { value: 'tp1', label: 'Solo dopo TP1' },
          ]}
        />
        {settings.perp_breakeven_enabled && (
          <NumberInput
            label="BE profitto min $ (0=solo costi)"
            help={'Guadagno minimo da lasciare sul tavolo quando lo stop va a pareggio. A zero copre solo i costi; alzandolo, il pareggio diventa un piccolo utile garantito.'} value={settings.perp_breakeven_min_profit_usd}
            step={0.05}
            onChange={(perp_breakeven_min_profit_usd) => patch({ perp_breakeven_min_profit_usd: Math.max(0, perp_breakeven_min_profit_usd) })}
          />
        )}
        <SelectInput
          label="Stop Loss Perp"
          help={'Come calcolare lo stop loss:\n\nATR — distanza fissa sulla volatilità\nMin/Max 20 candele — sotto il minimo (o sopra il massimo) recente: più largo e più aderente al grafico'} value={settings.perp_sl_mode}
          onChange={(v) => patch({ perp_sl_mode: v })}
          options={[
            { value: 'atr', label: 'ATR (attuale)' },
            { value: 'lowest', label: 'Min/Max 20 candele' },
          ]}
        />
        <ToggleInput
          label="Time Stop Perp"
          help={'Attiva la chiusura per tempo scaduto. Le ore si impostano nella sezione strategia.'} checked={settings.perp_time_stop_enabled}
          onChange={(perp_time_stop_enabled) => patch({ perp_time_stop_enabled })}
        />
        <ToggleInput
          label="Filtro shock BTC perp"
          help={'Blocca le nuove aperture quando Bitcoin è in una fase anomala, perché in quei momenti tutto il mercato si muove insieme e i segnali sui singoli asset valgono meno. Serve almeno il verificarsi di due delle tre condizioni qui sotto.'} checked={settings.perp_trend_shock_enabled}
          onChange={(perp_trend_shock_enabled) => patch({ perp_trend_shock_enabled })}
        />
        {settings.perp_trend_shock_enabled && (
          <Collapsible title="Soglie del filtro shock BTC" count={4}>
          <div className="grid grid-cols-2 gap-3">
            <NumberInput label="ADX threshold" help={'Quanto deve essere forte il trend di Bitcoin perché conti come segnale d\'allarme. Sopra questa soglia vale un punto su tre.'} value={settings.perp_trend_shock_adx_threshold} onChange={(perp_trend_shock_adx_threshold) => patch({ perp_trend_shock_adx_threshold })} />
            <NumberInput label="NATR percentile" help={'Quanto in alto deve stare la volatilità di Bitcoin rispetto al suo passato. A 90 significa: più alta del 90% delle volte. Vale un punto.'} value={settings.perp_trend_shock_natr_percentile} onChange={(perp_trend_shock_natr_percentile) => patch({ perp_trend_shock_natr_percentile })} />
            <NumberInput label="Volume threshold" help={'Quante volte il volume di Bitcoin deve superare la sua media per contare come allarme. Vale un punto.'} value={settings.perp_trend_shock_volume_threshold} onChange={(perp_trend_shock_volume_threshold) => patch({ perp_trend_shock_volume_threshold })} />
            <NumberInput label="Recovery checks" help={'Quanti controlli consecutivi tranquilli servono prima di tornare a operare. Più alto, più prudente nel rientrare.'} value={settings.perp_trend_shock_recovery_confirmations} onChange={(perp_trend_shock_recovery_confirmations) => patch({ perp_trend_shock_recovery_confirmations })} />
          </div>
          </Collapsible>
        )}
        <ToggleInput
          label="Smart Stop Loss Perp"
          help={'Invece di subire lo stop in un colpo solo, vende a pezzi mentre il prezzo scende verso lo stop, per ridurre la perdita. Può poi ricomprare se il prezzo rimbalza.'} checked={settings.perp_smart_sl_enabled}
          onChange={(perp_smart_sl_enabled) => patch({ perp_smart_sl_enabled })}
        />
        {settings.perp_smart_sl_enabled && (
          <Collapsible title="Parametri Smart Stop Loss" count={20}>
            {/* Vendite a scaglioni: riducono la perdita, sempre attive con lo Smart SL */}
            <div className="grid grid-cols-2 gap-3">
              <NumberInput label="L1 frac" help={'Dove sta il primo livello di vendita, come frazione della strada fra ingresso e stop. A 0.35 scatta al 35% del percorso verso lo stop.'} value={settings.perp_smart_sl_l1_frac} step={0.01} onChange={(perp_smart_sl_l1_frac) => patch({ perp_smart_sl_l1_frac })} />
              <NumberInput label="L2 frac" help={'Dove sta il secondo livello di vendita, sempre come frazione della strada verso lo stop.'} value={settings.perp_smart_sl_l2_frac} step={0.01} onChange={(perp_smart_sl_l2_frac) => patch({ perp_smart_sl_l2_frac })} />
              <NumberInput label="Split L1 %" help={'Quanta parte della posizione vendere al primo livello.'} value={settings.perp_smart_sl_split_l1} step={0.01} onChange={(perp_smart_sl_split_l1) => patch({ perp_smart_sl_split_l1 })} />
              <NumberInput label="Split L2 %" help={'Quanta parte vendere al secondo livello.'} value={settings.perp_smart_sl_split_l2} step={0.01} onChange={(perp_smart_sl_split_l2) => patch({ perp_smart_sl_split_l2 })} />
              <NumberInput label="Split L3 %" help={'Quanta parte lasciare in piedi fino allo stop vero e proprio. Le tre quote devono sommare a 1.'} value={settings.perp_smart_sl_split_l3} step={0.01} onChange={(perp_smart_sl_split_l3) => patch({ perp_smart_sl_split_l3 })} />
              <NumberInput label="Candele conferma SSL" help={'Quante candele da 5 minuti devono confermare prima di vendere o ricomprare. Più alto significa meno reazioni ai falsi movimenti, ma reazione più lenta.'} value={settings.perp_smart_sl_confirmation_candles} step={1} onChange={(perp_smart_sl_confirmation_candles) => patch({ perp_smart_sl_confirmation_candles: Math.round(perp_smart_sl_confirmation_candles) })} />
            </div>

            {/* Rebuy: rientri dopo la vendita. max_reentries=0 = spenti (default consigliato). */}
            <ToggleInput
              label="Disattiva rebuy (consigliato)"
              help={'Spegne il riacquisto dopo le vendite dello Smart SL: quello che è stato venduto resta venduto.\n\nÈ la scelta prudente, perché il rebuy può far rientrare in un mercato che continua a scendere.'}
              checked={settings.perp_smart_sl_max_reentries === 0}
              onChange={(disattiva) => patch({ perp_smart_sl_max_reentries: disattiva ? 0 : 1 })}
            />
            {settings.perp_smart_sl_max_reentries === 0 ? (
              <p className="text-xs text-gray-500 px-1">
                Rebuy spenti: dopo le vendite a scaglioni la posizione non rientra.
                Sui 301 trade V1 i rebuy hanno pesato −70&nbsp;USD su 6 sole posizioni.
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <SelectInput label="Rebuy mode" help={'Come ricomprare dopo aver venduto:\n\nSopra l\'ingresso — ricompra tutto quando il prezzo torna sopra il prezzo d\'entrata\nA livelli — ricompra a scaglioni sui rimbalzi'} value={settings.perp_smart_sl_rebuy_mode} onChange={(v) => patch({
                  perp_smart_sl_rebuy_mode: v,
                  ...(v === 'above_entry' ? { perp_smart_sl_confirmation_candles: 2 } : { perp_smart_sl_confirmation_candles: 3 }),
                })} options={[
                  { value: 'above_entry', label: 'Sopra entry' },
                  { value: 'delta', label: 'Delta per livello' },
                ]} />
                <NumberInput label="Max reentries" help={'Quanti cicli vendi-e-ricompra sono ammessi sulla stessa posizione. A zero il rebuy è spento e la vendita è definitiva.'} value={settings.perp_smart_sl_max_reentries} step={1} onChange={(perp_smart_sl_max_reentries) => patch({ perp_smart_sl_max_reentries: Math.max(1, Math.round(perp_smart_sl_max_reentries)) })} />
                {settings.perp_smart_sl_rebuy_mode === 'above_entry' && (
                  <>
                    <NumberInput label="Rebuy % venduto" help={'Quanta parte di ciò che è stato venduto viene ricomprata, quando il prezzo risale sopra il prezzo d\'ingresso.\n\nA 100 rientra tutto in una volta; sotto 100 rientra solo in parte e il resto resta liquidato.'}value={settings.perp_smart_sl_rebuy_above_entry_pct} step={1} onChange={(perp_smart_sl_rebuy_above_entry_pct) => patch({ perp_smart_sl_rebuy_above_entry_pct })} />
                    <NumberInput label="R2 Split L1 %" help={'Se un livello è già stato venduto e poi ricomprato, e il prezzo ci torna sopra, si vende una seconda volta con questa quota invece di quella normale.\n\nÈ calcolata sulla posizione di partenza, non su quanto resta.'}value={settings.perp_smart_sl_split_l1_r2} step={0.01} onChange={(perp_smart_sl_split_l1_r2) => patch({ perp_smart_sl_split_l1_r2 })} />
                    <NumberInput label="R2 Split L2 %" help={'Quota del secondo giro per il secondo livello, quando è già stato venduto e ricomprato una volta.\n\nAnche questa è calcolata sulla posizione di partenza.'}value={settings.perp_smart_sl_split_l2_r2} step={0.01} onChange={(perp_smart_sl_split_l2_r2) => patch({ perp_smart_sl_split_l2_r2 })} />
                    <NumberInput label="R2 Split L3 %" help={'Quanta parte lasciare in piedi fino allo stop, nel secondo giro di vendite. Con quote 75 e 20 sopra, qui resta il 5%.'}value={settings.perp_smart_sl_split_l3_r2} step={0.01} onChange={(perp_smart_sl_split_l3_r2) => patch({ perp_smart_sl_split_l3_r2 })} />
                  </>
                )}
                {settings.perp_smart_sl_rebuy_mode === 'delta' && (
                  <>
                    <NumberInput label="Delta L1" help={'Quanto deve rimbalzare il prezzo per ricomprare il primo scaglione.\n\nSi misura dal prezzo a cui hai venduto, come frazione della distanza fra ingresso e stop: a 0.08 basta un rimbalzo dell\'8% di quella distanza.'}value={settings.perp_smart_sl_delta_l1} step={0.01} onChange={(perp_smart_sl_delta_l1) => patch({ perp_smart_sl_delta_l1 })} />
                    <NumberInput label="Delta L2" help={'Quanto deve rimbalzare il prezzo per ricomprare il secondo scaglione.\n\nStessa misura del primo: frazione della distanza fra ingresso e stop, contata dal prezzo di vendita.'}value={settings.perp_smart_sl_delta_l2} step={0.01} onChange={(perp_smart_sl_delta_l2) => patch({ perp_smart_sl_delta_l2 })} />
                  </>
                )}
                <ToggleInput label="Adegua TP dopo rebuy" help={'Dopo un rebuy sposta gli obiettivi più in là, in modo che le uscite rimaste recuperino anche le perdite già incassate durante le vendite.'} checked={settings.perp_smart_sl_tp_adjust_after_rebuy} onChange={(perp_smart_sl_tp_adjust_after_rebuy) => patch({ perp_smart_sl_tp_adjust_after_rebuy })} />
                {settings.perp_smart_sl_tp_adjust_after_rebuy && (
                  <NumberInput label="Delta recovery TP %" help={'Quanto guadagno extra pretendere oltre il semplice recupero delle perdite, quando gli obiettivi vengono spostati.'} value={settings.perp_smart_sl_tp_recovery_delta_pct} step={1} onChange={(perp_smart_sl_tp_recovery_delta_pct) => patch({ perp_smart_sl_tp_recovery_delta_pct })} />
                )}
              </div>
            )}
          </Collapsible>
        )}
      </section>
        </>
      )}

      {dirty && !saving && (
        <p className="rounded-lg border border-accent-yellow/30 bg-accent-yellow/10 px-3 py-2 text-xs text-accent-yellow">
          Modifiche non salvate — l'aggiornamento automatico è in pausa finché non salvi.
        </p>
      )}
      <button
        onClick={onSave}
        disabled={!adminToken || saving}
        className={`w-full rounded-lg px-3 py-3 text-sm font-semibold text-white disabled:opacity-40 ${dirty ? 'bg-accent-orange' : 'bg-accent-blue'}`}
      >
        {saving ? 'Salvataggio…' : dirty ? 'Salva le modifiche' : 'Salva impostazioni agente'}
      </button>
      {actionError && <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{actionError}</p>}
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
            <TradeCandleChartLW
              chart={detail.chart}
              breakeven={detail.breakeven_price}
              trailing={detail.trailing_stop}
              smartSlLevels={detail.smart_sl_levels}
              smartSlState={detail.smart_sl_state_summary}
            />
            <div className="flex flex-wrap gap-3 text-[10px] text-gray-400">
              {/* La legenda prende i colori dalla stessa palette del grafico: se un
                  livello cambia tinta, qui non resta indietro. */}
              <span style={{ color: LEVEL_COLORS.entry }}>⬆ E = ingresso</span>
              {/* Su una posizione ancora aperta il prezzo "adesso" non è un evento con un
                  verso giusto o sbagliato: niente più freccia verde/rossa, solo una riga
                  di riferimento come le altre (scelta di David, 20/08). Su un trade chiuso
                  l'uscita resta un evento preciso, marcato con la freccia colorata. */}
              {detail.chart.live ? (
                <span style={{ color: LEVEL_COLORS.now }}>- - Ora</span>
              ) : (
                <span className={Number(detail.chart.exit_price) >= Number(detail.chart.entry_price) ? 'text-accent-green' : 'text-accent-red'}>⬇ {detail.close_reason ? 'Uscita' : 'Exit'}</span>
              )}
              <span style={{ color: LEVEL_COLORS.sl }}>- - SL</span>
              {detail.smart_sl_levels && <span style={{ color: LEVEL_COLORS.s2 }}>- - S1/S2 Smart SL (✓ = venduto)</span>}
              {detail.chart.stop_reference && <span style={{ color: LEVEL_COLORS.ref }}>▮ candela dello stop</span>}
              {!!detail.chart.manual_closes?.length && (
                <span style={{ color: LEVEL_COLORS.manual }}>✂ chiusura manuale</span>
              )}
              {detail.breakeven_price != null && <span style={{ color: LEVEL_COLORS.be }}>- - BE = pareggio</span>}
              {detail.trailing_stop != null && <span style={{ color: LEVEL_COLORS.trl }}>- - TRL = trailing</span>}
              <span style={{ color: LEVEL_COLORS.tp1 }}>- - TP1</span>
              <span style={{ color: LEVEL_COLORS.tp2 }}>- - TP2</span>
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
            {/* Su un trade di chiusura il backend riporta il prezzo di USCITA, non
                quello corrente: chiamarlo "Now/Exit" faceva sembrare fermo il prezzo. */}
            <Stat
              label={detail.close_reason ? 'Uscita' : 'Prezzo ora'}
              value={fmtPriceFull(detail.current_or_exit_price)}
            />
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
  scannerStatus: ScannerStatusResponse | null;
  global: GlobalView | null;
  equity: EquityCurveResponse | null;
  equityRange: EquityRange;
  decisions: AgentDecisionResponse | null;
  assetBreakdown: AssetBreakdownResponse | null;
  settings: AgentMobileSettings | null;
  execWallets: ExecutionWalletsResponse | null;
  claudeUsage: ClaudeUsageView | null;
  loaded: boolean;
  // Stato del setup: sotto-scheda attiva e blocchi richiudibili aperti. Sta qui e
  // non in useState perche' il pannello viene smontato a ogni cambio di vista, e
  // tornando indietro si ripartiva sempre da "Generale" con tutto richiuso.
  setupTab: SetupTab;
  openBlocks: string[];
} = {
  pane: 'spot', status: null, spot: null, perp: null, scannerStatus: null, global: null, equity: null,
  equityRange: '24h', decisions: null, assetBreakdown: null, settings: null,
  execWallets: null, claudeUsage: null, loaded: false,
  setupTab: 'generale', openBlocks: [],
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
  const [scannerStatus, setScannerStatus] = useState<ScannerStatusResponse | null>(agentCache.scannerStatus);
  const [operationalStats, setOperationalStats] = useState<OperationalStats | null>(null);
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
  // "Dirty": l'utente sta modificando il Setup e non ha ancora salvato. Il
  // refresh periodico (45s) NON deve sovrascrivere le sue spunte con lo stato
  // del server: prima di questo flag il pannello "tornava indietro" da solo.
  const [settingsDirty, setSettingsDirty] = useState(false);
  const settingsDirtyRef = useRef(false);
  const handleSettingsChange = useCallback((next: AgentMobileSettings) => {
    settingsDirtyRef.current = true;
    setSettingsDirty(true);
    setSettings(next);
  }, []);
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
    // hasCompleteCachedTradeDetail (non hasCompleteTradeChart sul solo dato) tiene
    // conto anche dell'eta': su un trade live "completo una volta" non basta piu'.
    if (cached && (!enrichChart || hasCompleteCachedTradeDetail(tradeId))) {
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
    schedulePrefetchRetry(ids);

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
        fetchScannerStatus().then(setScannerStatus),
        fetchOperationalStats().then(setOperationalStats),
        fetchAgentSettings().then((r) => {
          // Con modifiche in corso non salvate, la copia locale ha precedenza.
          if (!settingsDirtyRef.current) setSettings(r.settings);
        }),
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
    agentCache.scannerStatus = scannerStatus;
    agentCache.global = global;
    agentCache.equity = equity;
    agentCache.equityRange = equityRange;
    agentCache.decisions = decisions;
    agentCache.assetBreakdown = assetBreakdown;
    agentCache.settings = settings;
    agentCache.execWallets = execWallets;
    agentCache.claudeUsage = claudeUsage;
    if (status || spot || perp || global || equity) agentCache.loaded = true;
  }, [pane, status, spot, perp, scannerStatus, global, equity, equityRange, decisions, assetBreakdown, settings, execWallets, claudeUsage]);

  useEffect(() => {
    // Al primo mount in assoluto mostra l'indicatore; ai rientri (cache popolata)
    // aggiorna in silenzio mantenendo i valori precedenti.
    refresh(agentCache.loaded);
  }, [refresh]);

  useEffect(() => {
    // document.hidden: in background i tick bruciano radio/batteria per dati che
    // nessuno guarda; al rientro in foreground il listener qui sotto recupera.
    const timer = window.setInterval(() => {
      if (!document.hidden) refresh();
    }, AGENT_REFRESH_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') refresh(true);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [refresh]);

  // Refresh leggero: aggiorna solo le viste principali e salta se un ciclo e' gia' in corso.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.hidden) return;
      if (refreshInFlightRef.current) return;
      if (fastRefreshInFlightRef.current) return;
      fastRefreshInFlightRef.current = true;
      Promise.allSettled([
        fetchSpotView().then(setSpot),
        fetchPerpView().then(setPerp),
        fetchGlobalView().then(setGlobal),
        fetchScannerStatus().then(setScannerStatus),
        fetchOperationalStats().then(setOperationalStats),
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
      settingsDirtyRef.current = false;
      setSettingsDirty(false);
      setSettings(response.settings);
    } catch (err) {
      setActionError(err instanceof Error ? traduciErroreSalvataggio(err.message) : 'Save failed');
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
      if (!hasCompleteCachedTradeDetail(tradeId)) {
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
        <ResumeAgentButton
          killSwitch={status?.kill_switch}
          adminToken={adminToken}
          saving={saving}
          onResume={() => void handleKill('running')}
        />
      </div>

      <GuardianBanner
        guardian={status?.guardian}
        killSwitch={status?.kill_switch}
        adminToken={adminToken}
        busy={saving}
        onPause={() => void handleKill('soft_stop')}
        onCloseAll={() => void handleCloseAll()}
        onGuardianChanged={() => void refresh()}
      />

      <ScannerStatusPanel status={scannerStatus} />

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
      {pane === 'perp' && <PerpPane data={perp} onTrade={(tradeId) => void handleTradeDetail(tradeId)} adminToken={adminToken} onClosed={() => void refresh()} />}
      {pane === 'global' && <GlobalPane data={global} status={status} equity={equity} equityRange={equityRange} onEquityRange={setEquityRange} decisions={decisions} assetBreakdown={assetBreakdown} claudeUsage={claudeUsage} adminToken={adminToken} onCounterReset={() => void refresh()} operationalStats={operationalStats} onOpenSetup={() => { setPane('setup'); agentCache.setupTab = 'generale'; }} />}
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
          onSettings={handleSettingsChange}
          dirty={settingsDirty}
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
