import { type FC } from 'react';
import type { TradeDetail } from '../services/agentApi';
import { buildTradeChartModel, LEVEL_COLORS, type TradeChartLevel } from './tradeChartModel';

export const TradeCandleChart: FC<{
  chart: NonNullable<TradeDetail['chart']>;
  breakeven?: string | null;
  trailing?: string | null;
  smartSlLevels?: string[] | null;
  smartSlState?: { status: string }[] | null;
}> = ({ chart, breakeven, trailing, smartSlLevels, smartSlState }) => {
  const model = buildTradeChartModel(chart, breakeven, trailing, smartSlLevels, smartSlState);
  if (model === null) {
    return <p className="text-xs text-gray-500">Grafico non disponibile per questo trade.</p>;
  }
  const allCandles = model.candles;
  // Geometria: area di plot + margine destro per i prezzi (Y) e inferiore per gli orari (X).
  const W = Math.max(340, allCandles.length * 8 + 58);
  const H = 200;
  const padX = 6;
  const padTop = 10;
  const axisW = 46;
  const axisH = 16;
  const plotR = W - axisW;
  const plotB = H - axisH;
  const range = model.scaleHigh - model.scaleLow;
  const y = (price: number) => padTop + (1 - (price - model.scaleLow) / range) * (plotB - padTop);
  const colW = (plotR - padX) / allCandles.length;
  const cx = (i: number) => padX + colW * (i + 0.5);

  // Linea di livello con etichetta: tag right-aligned appena sopra la linea, dentro il
  // plot (l'asse destro resta ai tick di prezzo). strong=true = livello già eseguito.
  const levelLine = ({ key, price, color, dash, tag, strong }: TradeChartLevel) => (
    <g key={key} opacity={strong ? 0.85 : 0.5}>
      <line x1={padX} x2={plotR} y1={y(price)} y2={y(price)} stroke={color} strokeWidth={strong ? 1.4 : 1} strokeDasharray={dash} />
      <text x={plotR - 3} y={y(price) - 2.5} fontSize="7" fill={color} textAnchor="end" fontWeight={strong ? 600 : 400}>
        {tag}
      </text>
    </g>
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
          <line x1={x} x2={x} y1={padTop} y2={topEnd} stroke={LEVEL_COLORS.ref} strokeWidth="1" strokeDasharray="2 2" opacity="0.9" />
        )}
        {bottomStart < plotB && (
          <line x1={x} x2={x} y1={bottomStart} y2={plotB} stroke={LEVEL_COLORS.ref} strokeWidth="1" strokeDasharray="2 2" opacity="0.9" />
        )}
      </>
    );
  };

  // Linea verticale tratteggiata subito dopo la candela di chiusura.
  const closeLineX = model.exitIndex < allCandles.length - 1 ? cx(model.exitIndex + 0.5) : null;

  return (
    <div className="overflow-x-auto pb-1">
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: `${W}px`, minWidth: '100%', height: 'auto' }}>
      {/* griglia + etichette asse Y */}
      {model.yTicks.map((p, k) => (
        <g key={`yt${k}`}>
          <line x1={padX} x2={plotR} y1={y(p)} y2={y(p)} stroke="#1f2937" strokeWidth="0.5" opacity="0.6" />
          <text x={plotR + 4} y={y(p)} fontSize="8" fill="#6b7280" dominantBaseline="middle">{model.yLabels[k]}</text>
        </g>
      ))}
      {/* assi */}
      <line x1={plotR} x2={plotR} y1={padTop} y2={plotB} stroke="#374151" strokeWidth="0.5" />
      <line x1={padX} x2={plotR} y1={plotB} y2={plotB} stroke="#374151" strokeWidth="0.5" />
      {/* etichette asse X */}
      {model.xTickIndexes.map((i, k) => (
        <text
          key={`xt${k}`}
          x={cx(i)}
          y={H - 4}
          fontSize="8"
          fill="#6b7280"
          textAnchor={k === 0 ? 'start' : k === model.xTickIndexes.length - 1 ? 'end' : 'middle'}
        >
          {model.xLabels[k]}
        </text>
      ))}
      {/* sfondo post-close */}
      {closeLineX != null && (
        <rect x={closeLineX} y={padTop} width={plotR - closeLineX} height={plotB - padTop} fill="#111827" opacity="0.4" />
      )}
      {/* Candles outside the active trade window are contextual and muted. */}
      {allCandles.map((c, i) => {
        const isPost = i > model.exitIndex; // spente dall'uscita in poi, non dalla fine dello snapshot
        const isPreEntry = i < model.entryIndex;
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
      {model.stopRefIndex != null && (
        <>
          {stopRefLine(model.stopRefIndex)}
          <text x={Math.min(plotR - 4, cx(model.stopRefIndex) + 4)} y={padTop + 8} fontSize="8" fill={LEVEL_COLORS.ref}>SL ref</text>
          {model.stopRefPrice != null && !Number.isNaN(model.stopRefPrice) && (
            <circle cx={cx(model.stopRefIndex)} cy={y(model.stopRefPrice)} r="3" fill={LEVEL_COLORS.ref} stroke="#0b0e11" strokeWidth="1" />
          )}
        </>
      )}
      {/* Livelli di uscita: ordine e aspetto vengono dal modello. */}
      {model.levels.map(levelLine)}
      {/* marker ingresso/uscita */}
      <circle cx={cx(model.entryIndex)} cy={y(model.entryPrice)} r="3.5" fill="#e5e7eb" stroke="#0b0e11" strokeWidth="1" />
      <circle cx={cx(model.exitIndex)} cy={y(model.exitPrice)} r="3.5" fill={model.exitGood ? '#22c55e' : '#ef4444'} stroke="#0b0e11" strokeWidth="1" />
    </svg>
    </div>
  );
};
