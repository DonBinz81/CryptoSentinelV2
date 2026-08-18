// Modello del grafico della posizione: decide COSA mostrare, non COME disegnarlo.
//
// Estratto da TradeCandleChart senza cambiarne la logica: qui vivono i conti
// (livelli, marker, scala, etichette degli assi), mentre il disegno resta al
// componente. Cosi' il rendering puo' cambiare tecnologia senza che nessuna
// informazione si perda per strada, e i due renderer leggono la stessa lista.
import type { TradeDetail } from '../services/agentApi';

type Chart = NonNullable<TradeDetail['chart']>;
type Candle = Chart['candles'][number];

export type TradeChartLevelKey = 'sl' | 's1' | 's2' | 'be' | 'trl' | 'tp1' | 'tp2' | 'entry';

export interface TradeChartLevel {
  key: TradeChartLevelKey;
  price: number;
  tag: string;
  color: string;
  dash: string;
  /** Livello gia' eseguito: tratto piu' marcato ed etichetta in grassetto. */
  strong: boolean;
}

export interface TradeChartModel {
  /** Candele del trade seguite da quelle successive alla chiusura. */
  candles: Candle[];
  /** Quante delle candele iniziali appartengono al trade (le altre sono post-chiusura). */
  tradeCandleCount: number;
  /** Livelli nell'ordine in cui vanno disegnati (i successivi coprono i precedenti). */
  levels: TradeChartLevel[];
  /** Direzione del trade: decide il verso della freccia d'ingresso. */
  isLong: boolean;
  entryIndex: number;
  entryPrice: number;
  exitIndex: number;
  exitPrice: number;
  /** Uscita in guadagno rispetto all'ingresso: decide il colore del marker. */
  exitGood: boolean;
  stopRefIndex: number | null;
  stopRefPrice: number | null;
  /** Estremi verticali: comprendono candele E livelli, cosi' nulla resta fuori vista. */
  scaleLow: number;
  scaleHigh: number;
  yTicks: number[];
  yLabels: string[];
  xTickIndexes: number[];
  xLabels: string[];
}

/** Formato del prezzo sull'asse: piu' decimali quanto piu' il prezzo e' piccolo. */
export function formatAxisPrice(p: number): string {
  if (p >= 1000) return p.toFixed(0);
  if (p >= 1) return p.toFixed(2);
  if (p >= 0.01) return p.toFixed(4);
  return p.toPrecision(3);
}

/** Formato dell'orario sull'asse: data se il grafico copre piu' di un giorno. */
export function formatAxisTime(iso: string, spanMs: number): string {
  const d = new Date(iso);
  return spanMs > 24 * 3600 * 1000
    ? d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' })
    : d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}

/**
 * Palette dei livelli, presa dal design system di TradingView e organizzata per
 * significato invece che per gusto: il rischio scala dal rosso all'ambra, gli
 * obiettivi sono verdi, i riferimenti restano neutri e la protezione dinamica
 * (trailing) e' blu. Cosi' il colore dice subito che cosa sta succedendo.
 */
export const LEVEL_COLORS = {
  sl: '#f23645',    // rosso: la perdita massima accettata
  s2: '#ff9800',    // ambra: seconda soglia di uscita parziale in perdita
  s1: '#ffb74d',    // ambra chiara: prima soglia, la meno grave
  be: '#787b86',    // grigio neutro: pareggio, ne' rischio ne' obiettivo
  entry: '#d1d4dc', // bianco tenue: il riferimento da cui si misura tutto
  trl: '#3dabff',   // blu: protezione dinamica che segue il prezzo
  tp1: '#089981',   // verde: primo obiettivo
  tp2: '#26c6a5',   // verde piu' chiaro: obiettivo finale, piu' lontano
  ref: '#8b5cf6',   // viola: la candela da cui e' stato calcolato lo stop. Sta fuori
                    // dalle tre famiglie (rischio, obiettivi, neutri) perche' non e' un
                    // livello operativo ma un dato di costruzione.
} as const;

const ts = (s: string) => new Date(s).getTime();

const nearest = (target: number, pool: Candle[]) => {
  let best = 0;
  let bestD = Infinity;
  pool.forEach((c, i) => { const d = Math.abs(ts(c.t) - target); if (d < bestD) { bestD = d; best = i; } });
  return best;
};

const atOrBefore = (target: number, pool: Candle[]) => {
  let best = -1;
  pool.forEach((c, i) => { if (ts(c.t) <= target) best = i; });
  return best >= 0 ? best : nearest(target, pool);
};

const num = (v: string | null | undefined): number | null => (v != null ? Number(v) : null);

/** Ritorna null quando non c'e' abbastanza materiale per un grafico (meno di 2 candele). */
export function buildTradeChartModel(
  chart: Chart,
  breakeven?: string | null,
  trailing?: string | null,
  smartSlLevels?: string[] | null,
  smartSlState?: { status: string }[] | null,
): TradeChartModel | null {
  const tradeCandles = chart.candles ?? [];
  const postClose = chart.post_close_candles ?? [];
  const candles = [...tradeCandles, ...postClose];
  if (candles.length < 2) return null;

  const entry = Number(chart.entry_price);
  const exit = Number(chart.exit_price);
  const sl = num(chart.stop_loss);
  const tp1 = num(chart.take_profit_1);
  const tp2 = num(chart.take_profit_2);
  const be = num(breakeven);
  const trail = num(trailing);
  // Smart SL: [L1, L2, L3]; L3 = stop iniziale, gia' rappresentato dalla linea SL.
  const s1 = smartSlLevels?.[0] != null ? Number(smartSlLevels[0]) : null;
  const s2 = smartSlLevels?.[1] != null ? Number(smartSlLevels[1]) : null;
  const s1Sold = smartSlState?.[0]?.status === 'sold';
  const s2Sold = smartSlState?.[1]?.status === 'sold';

  // Livelli di uscita — pastello tenue, tag per livello; Smart SL in gradazione
  // arancio (perdita parziale, tra BE giallo e SL rosso), ✓ = gia' eseguito.
  const candidates: (TradeChartLevel | null)[] = [
    sl == null ? null : { key: 'sl', price: sl, tag: 'SL', color: LEVEL_COLORS.sl, dash: '4 3', strong: false },
    s1 == null ? null : { key: 's1', price: s1, tag: s1Sold ? 'S1 ✓' : 'S1', color: LEVEL_COLORS.s1, dash: '4 4', strong: s1Sold },
    s2 == null ? null : { key: 's2', price: s2, tag: s2Sold ? 'S2 ✓' : 'S2', color: LEVEL_COLORS.s2, dash: '4 4', strong: s2Sold },
    be == null ? null : { key: 'be', price: be, tag: 'BE', color: LEVEL_COLORS.be, dash: '3 3', strong: false },
    trail == null ? null : { key: 'trl', price: trail, tag: 'TRL', color: LEVEL_COLORS.trl, dash: '3 3', strong: false },
    tp1 == null ? null : { key: 'tp1', price: tp1, tag: 'TP1', color: LEVEL_COLORS.tp1, dash: '4 3', strong: false },
    tp2 == null ? null : { key: 'tp2', price: tp2, tag: 'TP2', color: LEVEL_COLORS.tp2, dash: '2 3', strong: false },
    { key: 'entry', price: entry, tag: 'E', color: LEVEL_COLORS.entry, dash: '1 0', strong: false },
  ];
  const levels = candidates.filter((l): l is TradeChartLevel => l != null && !Number.isNaN(l.price));

  // La scala comprende anche il prezzo di uscita, che non e' una linea ma un marker.
  const scalePrices = [entry, exit, sl, tp1, tp2, be, trail, s1, s2]
    .filter((v): v is number => v != null && !Number.isNaN(v));
  let scaleHigh = Math.max(...candles.map((c) => c.h), ...scalePrices);
  let scaleLow = Math.min(...candles.map((c) => c.l), ...scalePrices);
  if (scaleHigh === scaleLow) { scaleHigh += 1; scaleLow -= 1; }
  const range = scaleHigh - scaleLow;

  const stopRefIndex = chart.stop_reference?.t ? nearest(ts(chart.stop_reference.t), candles) : null;
  const stopRefPrice = sl ?? (chart.stop_reference?.price != null ? Number(chart.stop_reference.price) : null);

  const yTicks = [0, 1, 2, 3, 4].map((k) => scaleLow + (range * k) / 4);
  const spanMs = ts(candles[candles.length - 1].t) - ts(candles[0].t);
  const last = candles.length - 1;
  const xTickIndexes = [0, Math.round(last / 3), Math.round((2 * last) / 3), last];

  return {
    candles,
    tradeCandleCount: tradeCandles.length,
    levels,
    isLong: String(chart.side).toLowerCase() !== 'short',
    entryIndex: nearest(ts(chart.opened_at), candles),
    entryPrice: entry,
    exitIndex: atOrBefore(ts(chart.closed_at), candles),
    exitPrice: exit,
    exitGood: exit >= entry,
    stopRefIndex,
    stopRefPrice,
    scaleLow,
    scaleHigh,
    yTicks,
    yLabels: yTicks.map(formatAxisPrice),
    xTickIndexes,
    xLabels: xTickIndexes.map((i) => formatAxisTime(candles[i].t, spanMs)),
  };
}
