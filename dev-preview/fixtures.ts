// Banco di anteprima — dati finti, deterministici, nessuna chiamata di rete.
// Coprono i casi che il grafico deve saper rappresentare.
import type { TradeDetail } from '../src/services/agentApi';

type Chart = NonNullable<TradeDetail['chart']>;
type Candle = Chart['candles'][number];

const START = Date.parse('2026-08-18T06:00:00Z');
const STEP = 5 * 60 * 1000; // 5 minuti

// Serie deterministica (nessun random): oscillazione + deriva.
function series(n: number, base: number, drift: number, amp: number, from = 0): Candle[] {
  const out: Candle[] = [];
  for (let i = 0; i < n; i++) {
    const k = from + i;
    const mid = base + drift * k + amp * Math.sin(k / 3.1);
    const o = mid + amp * 0.12 * Math.cos(k / 2.3);
    const c = mid + amp * 0.12 * Math.sin(k / 1.7);
    const h = Math.max(o, c) + amp * 0.22;
    const l = Math.min(o, c) - amp * 0.22;
    out.push({ t: new Date(START + k * STEP).toISOString(), o, h, l, c });
  }
  return out;
}

export interface Caso {
  nome: string;
  descrizione: string;
  chart: Chart;
  breakeven?: string | null;
  trailing?: string | null;
  smartSlLevels?: string[] | null;
  smartSlState?: { status: string }[] | null;
}

/**
 * Costruisce un caso realistico: i livelli si ricavano DALLE candele, non a mano.
 * L'ingresso e' la chiusura della candela di apertura e l'uscita quella della
 * candela di chiusura, come avviene davvero; SL e TP sono distanze percentuali
 * dall'ingresso, nel verso giusto per long e short.
 */
function caso(opts: {
  nome: string;
  descrizione: string;
  candles: Candle[];
  post?: Candle[];
  side: 'long' | 'short';
  openIdx: number;
  closeIdx: number;
  slPct: number;
  tp1Pct: number;
  tp2Pct: number;
  bePct?: number | null;
  trlPct?: number | null;
  smartSl?: boolean;
  s1Sold?: boolean;
  live?: boolean;
  decimals?: number;
}): Caso {
  const dec = opts.decimals ?? 2;
  const n = (v: number) => v.toFixed(dec);
  const entry = opts.candles[opts.openIdx].c;
  const exit = opts.candles[opts.closeIdx].c;
  const dir = opts.side === 'long' ? 1 : -1;
  const at = (pct: number) => entry * (1 + (dir * pct) / 100);
  const sl = at(-opts.slPct);
  const smart = opts.smartSl
    ? [n(entry + (sl - entry) * 0.35), n(entry + (sl - entry) * 0.65), n(sl)]
    : null;
  return {
    nome: opts.nome,
    descrizione: opts.descrizione,
    chart: {
      interval: '5m',
      market: 'perp',
      side: opts.side,
      entry_price: n(entry),
      exit_price: n(exit),
      stop_loss: n(sl),
      take_profit_1: n(at(opts.tp1Pct)),
      take_profit_2: n(at(opts.tp2Pct)),
      liquidation_price: null,
      opened_at: opts.candles[opts.openIdx].t,
      closed_at: opts.candles[opts.closeIdx].t,
      live: opts.live ?? false,
      stop_reference: opts.smartSl
        ? { t: opts.candles[Math.max(0, opts.openIdx - 4)].t, price: n(sl), field: 'low', pre_candles: 20, inferred: false }
        : null,
      candles: opts.candles,
      post_close_candles: opts.post ?? [],
    },
    breakeven: opts.bePct == null ? null : n(at(opts.bePct)),
    trailing: opts.trlPct == null ? null : n(at(opts.trlPct)),
    smartSlLevels: smart,
    smartSlState: smart
      ? [{ status: opts.s1Sold ? 'sold' : 'armed' }, { status: 'armed' }, { status: 'armed' }]
      : null,
  };
}

const casoA = caso({
  nome: 'A — LONG completo',
  descrizione: 'Tutti i livelli, S1 venduto, riferimento stop, candele post-chiusura',
  candles: series(48, 100, 0.09, 1.2),
  post: series(10, 100, 0.09, 1.2, 48),
  side: 'long',
  openIdx: 6,
  closeIdx: 40,
  slPct: 2.2,
  tp1Pct: 2.2,
  tp2Pct: 4.8,
  bePct: 0.45,
  trlPct: 2.9,
  smartSl: true,
  s1Sold: true,
});

const casoB = caso({
  nome: 'B — SHORT minimo',
  descrizione: 'Solo SL, TP1, TP2, ingresso e uscita: nessun livello opzionale',
  candles: series(36, 50, 0.05, 0.55),
  side: 'short',
  openIdx: 4,
  closeIdx: 33,
  slPct: 2.6,
  tp1Pct: 1.8,
  tp2Pct: 3.4,
});

const casoC = caso({
  nome: 'C — LIVE, prezzo micro',
  descrizione: 'Posizione aperta e prezzi con molti decimali (formattazione asse)',
  candles: series(30, 0.00042, 0.0000006, 0.000004),
  side: 'long',
  openIdx: 5,
  closeIdx: 29,
  slPct: 2.1,
  tp1Pct: 2.4,
  tp2Pct: 4.2,
  bePct: 0.5,
  smartSl: true,
  live: true,
  decimals: 6,
});

const casoD = caso({
  nome: 'D — livelli fuori scala',
  descrizione: 'TP2 e SL lontanissimi dalle candele: devono restare visibili',
  candles: series(40, 200, 0.02, 0.8),
  side: 'long',
  openIdx: 3,
  closeIdx: 37,
  slPct: 6.2,
  tp1Pct: 0.9,
  tp2Pct: 7.4,
  bePct: 0.25,
});

// E — trade appena aperto: il breakeven non e' ancora armato e il trailing non
// esiste, quindi quelle due linee NON devono comparire.
const casoE = caso({
  nome: 'E — prima del TP1',
  descrizione: 'Breakeven non ancora armato e trailing assente: le linee non devono esserci',
  candles: series(26, 80, 0.04, 0.5),
  side: 'long',
  openIdx: 4,
  closeIdx: 25,
  slPct: 2.0,
  tp1Pct: 1.6,
  tp2Pct: 3.2,
  bePct: null,
  trlPct: null,
  smartSl: true,
});

// F — oltre il TP2: il ratchet non chiude, lascia correre con il trailing.
// La linea TRL e' il prezzo a cui vendera' se il mercato torna indietro.
const casoF = caso({
  nome: 'F — oltre il TP2, trailing che corre',
  descrizione: 'TP1 e TP2 superati: la linea TRL e la distanza dicono dove vendera',
  candles: series(44, 30, 0.05, 0.3),
  side: 'long',
  openIdx: 3,
  closeIdx: 43,
  slPct: 2.4,
  tp1Pct: 1.5,
  tp2Pct: 3.0,
  bePct: 0.3,
  trlPct: 5.2,
  smartSl: true,
  s1Sold: false,
});

export const CASI: Caso[] = [casoA, casoB, casoC, casoD, casoE, casoF];
