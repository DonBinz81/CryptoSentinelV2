// Grafico della posizione disegnato con lightweight-charts (TradingView).
//
// Legge lo STESSO modello del grafico SVG (tradeChartModel): stessi livelli,
// stessi marker, stessa scala. Qui cambia solo il disegno — piu' zoom, pan e
// mirino nativi — e la sorgente delle candele resta il backend.
import { useEffect, useMemo, useRef, useState, type FC } from 'react';
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
  type SeriesMarker,
} from 'lightweight-charts';
import type { TradeDetail } from '../services/agentApi';
import { buildTradeChartModel, formatAxisPrice, LEVEL_COLORS } from './tradeChartModel';

/** Traduce il tratteggio SVG del modello nello stile di linea della libreria. */
function lineStyleFor(dash: string): LineStyle {
  if (dash === '1 0') return LineStyle.Solid;
  if (dash === '2 3') return LineStyle.Dotted;
  if (dash === '6 4') return LineStyle.LargeDashed;
  return LineStyle.Dashed;
}

/** Colore con trasparenza: la libreria non ha l'opacita' per singola candela. */
function faded(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

// Candele nei colori standard delle piattaforme professionali; le candele fuori
// dalla finestra del trade usano le stesse tinte spente.
// Il marker d'ingresso ha lo stesso bianco della linea E: freccia e livello sono
// la stessa informazione, il momento e il prezzo dell'ingresso.
/** Quanto la sigla sta sopra la sua linea. Serve anche a capire se esce in cima. */
const LABEL_OFFSET_PX = 13;

const ENTRY_MARKER = LEVEL_COLORS.entry;
const CANDLE_UP = '#089981';
const CANDLE_DOWN = '#f23645';
const CANDLE_UP_MUTED = '#0b5f52';
const CANDLE_DOWN_MUTED = '#8c2129';

const seconds = (iso: string) => Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;

const localTime = (epochSeconds: number) =>
  new Date(epochSeconds * 1000).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });

const localDateTime = (epochSeconds: number) =>
  new Date(epochSeconds * 1000).toLocaleString('it-IT', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });

// Scelta di David (18/08): il PREZZO di ogni livello sta nella scala di destra,
// insieme agli altri prezzi; sulla linea resta solo la SIGLA, in caratteri minuti.
// SL, TP1 e TP2 restano distinguibili perche' scritti in grassetto.
const KEY_LEVELS = new Set(['sl', 'tp1', 'tp2']);

export const TradeCandleChartLW: FC<{
  chart: NonNullable<TradeDetail['chart']>;
  breakeven?: string | null;
  trailing?: string | null;
  smartSlLevels?: string[] | null;
  smartSlState?: { status: string }[] | null;
  height?: number;
}> = ({ chart, breakeven, trailing, smartSlLevels, smartSlState, height = 280 }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  // Etichette dei livelli che non stanno sull'asse: le posiziona il componente,
  // perche' la libreria mostra il nome del livello solo insieme all'etichetta d'asse.
  const [inlineLabels, setInlineLabels] = useState<
    { key: string; text: string; color: string; bold: boolean; top: number; lane: number }[]
  >([]);
  // Larghezza dell'asse dei prezzi: le etichette si fermano prima, altrimenti
  // finirebbero sopra i numeri della scala.
  const [priceAxisWidth, setPriceAxisWidth] = useState(0);
  // Firma dell'ultimo posizionamento: durante il trascinamento il calcolo gira a
  // ogni fotogramma, ma si ridisegna solo quando qualcosa e' davvero cambiato.
  const lastPlacementRef = useRef('');

  // Il modello va calcolato una volta per dato ricevuto: senza questo verrebbe
  // ricostruito a ogni render, l'effetto sotto ripartirebbe e il ricalcolo delle
  // etichette (che aggiorna lo stato) si richiamerebbe all'infinito.
  // Distanza fra il trailing e l'ultimo prezzo, in percentuale: e' il margine che
  // il trailing lascia correre prima di vendere, quello che si tara nel setup perp.
  const trailingGapPct = useMemo(() => {
    if (trailing == null) return null;
    const trl = Number(trailing);
    const last = Number(chart.exit_price);
    if (!isFinite(trl) || !isFinite(last) || last === 0) return null;
    return `${(Math.abs((last - trl) / last) * 100).toFixed(1)}%`;
  }, [trailing, chart.exit_price]);

  const model = useMemo(
    () => buildTradeChartModel(chart, breakeven, trailing, smartSlLevels, smartSlState),
    [chart, breakeven, trailing, smartSlLevels, smartSlState],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container || model === null) return;

    const c = createChart(container, {
      width: container.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#0b0e11' },
        textColor: '#6b7280',
        fontSize: 10,
        attributionLogo: false,
      },
      grid: { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#1f2937', minimumWidth: 56 },
      timeScale: {
        borderColor: '#1f2937',
        timeVisible: true,
        secondsVisible: false,
        // La libreria etichetta in UTC: qui si riporta all'ora locale, come fa
        // il grafico attuale, altrimenti gli stessi dati sembrano di un altro orario.
        tickMarkFormatter: (time: number) => localTime(time),
      },
      localization: {
        priceFormatter: formatAxisPrice,
        timeFormatter: (time: number) => localDateTime(time),
      },
      // Nessun gesto bloccato: pinch sul tempo, trascinamento sulla scala dei
      // prezzi per allargare o stringere in verticale. Le sigle dei livelli
      // restano agganciate perche' vengono riposizionate durante il gesto.
    });
    chartRef.current = c;

    const series = c.addSeries(CandlestickSeries, {
      upColor: CANDLE_UP,
      downColor: CANDLE_DOWN,
      borderVisible: false,
      wickUpColor: CANDLE_UP,
      wickDownColor: CANDLE_DOWN,
      priceLineVisible: false,
      lastValueVisible: false,
      // I livelli devono restare in vista anche quando cadono fuori dalle candele:
      // senza questo, uno stop o un TP2 lontani sparirebbero dalla vista.
      // I margini servono: senza di essi la libreria ignora il range richiesto e
      // torna a scalare sulle sole candele, nascondendo i livelli lontani.
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: model.scaleLow, maxValue: model.scaleHigh },
        margins: { above: 6, below: 6 },
      }),
    });
    seriesRef.current = series;

    // Candele: fuori dalla finestra del trade restano attenuate, come nel grafico
    // attuale (prima dell'ingresso = contesto, dopo la chiusura = mercato successivo).
    series.setData(
      model.candles.map((candle, i) => {
        // Dopo l'USCITA, non dopo la fine dello snapshot: il trade e' finito li',
        // e tutto cio' che viene dopo e' mercato che non ci riguarda piu'.
        const post = i > model.exitIndex;
        const preEntry = i < model.entryIndex;
        const up = candle.c >= candle.o;
        const base = post ? (up ? CANDLE_UP_MUTED : CANDLE_DOWN_MUTED) : up ? CANDLE_UP : CANDLE_DOWN;
        // La candela da cui e' stato ricavato lo stop si evidenzia in viola: dice
        // da sola da dove viene il livello, senza aggiungere marker sopra.
        const color =
          i === model.stopRefIndex
            ? LEVEL_COLORS.ref
            : post || preEntry
              ? faded(base, 0.55)
              : base;
        return {
          time: seconds(candle.t),
          open: candle.o,
          high: candle.h,
          low: candle.l,
          close: candle.c,
          color,
          wickColor: color,
          borderColor: color,
        };
      }),
    );

    for (const level of model.levels) {
      series.createPriceLine({
        price: level.price,
        color: level.color,
        lineWidth: 1,
        lineStyle: lineStyleFor(level.dash),
        axisLabelVisible: true,
        axisLabelColor: '#0b0e11',
        axisLabelTextColor: level.color,
        title: '',
      });
    }

    // Prezzo di ogni chiusura manuale, come linea orizzontale. Il marker dice
    // QUANDO e QUANTO; la linea dice A CHE PREZZO, ed e' l'informazione che
    // serve a giudicare la decisione: quell'uscita sta sopra o sotto l'entry,
    // sopra o sotto il TP che il prezzo ha poi toccato.
    //
    // Punteggiata e sottile di proposito: e' un EVENTO GIA' AVVENUTO, non un
    // livello attivo come SL o TP, e non deve competere con le righe che dicono
    // cosa succedera'.
    for (const mc of model.manualCloses) {
      series.createPriceLine({
        price: mc.price,
        color: LEVEL_COLORS.manual,
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        axisLabelColor: '#0b0e11',
        axisLabelTextColor: LEVEL_COLORS.manual,
        title: '',
      });
    }

    const markers: SeriesMarker<UTCTimestamp>[] = [
      {
        // L'ingresso segue la direzione del trade: freccia in su sotto la candela
        // se e' un long, in giu' sopra la candela se e' uno short.
        time: seconds(model.candles[model.entryIndex].t),
        position: model.isLong ? 'belowBar' : 'aboveBar',
        color: ENTRY_MARKER,
        shape: model.isLong ? 'arrowUp' : 'arrowDown',
      },
    ];
    // Su una posizione ANCORA APERTA il prezzo "adesso" non e' un evento — cambia
    // ogni tick, non ha un verso giusto o sbagliato — quindi non e' piu' una freccia
    // verde/rossa: e' una riga tratteggiata leggera come le altre, col prezzo sulla
    // scala di destra (scelta di David, 20/08). Su un trade CHIUSO invece l'uscita
    // e' un evento preciso, a un prezzo e un istante precisi: li' la freccia resta.
    if (!chart.live) {
      markers.push({
        time: seconds(model.candles[model.exitIndex].t),
        position: 'aboveBar',
        color: model.exitGood ? CANDLE_UP : CANDLE_DOWN,
        shape: 'arrowDown',
      });
    }
    // Chiusure decise da una persona: restano visibili per sempre, perche'
    // vengono dalle righe immutabili dei trade e non da un calcolo al volo.
    for (const mc of model.manualCloses) {
      markers.push({
        time: seconds(model.candles[mc.index].t),
        position: 'belowBar',
        color: LEVEL_COLORS.manual,
        shape: 'circle',
        // Niente testo qui: lo porta l'etichetta inline, che sa separarsi da
        // quelle vicine. I testi dei marker nativi invece si sovrappongono.
      });
    }
    // I marker vanno in ordine di tempo, altrimenti la libreria li rifiuta.
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    createSeriesMarkers(series, markers);

    if (chart.live) {
      series.createPriceLine({
        price: model.exitPrice,
        color: LEVEL_COLORS.now,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        axisLabelColor: '#0b0e11',
        axisLabelTextColor: LEVEL_COLORS.now,
        title: '',
      });
    }

    c.timeScale().fitContent();
    // La chiusura manuale cade sull'ULTIMA candela, e fitContent() la incolla al
    // bordo: senza un po' d'aria la sua etichetta ("✂ 50%") esce dal grafico
    // tagliata a meta'. Il margine si aggiunge solo quando quei marker ci sono,
    // per non cambiare l'inquadratura di tutti gli altri grafici.
    if (model.manualCloses.length > 0) {
      c.timeScale().applyOptions({ rightOffset: 5 });
    }

    // Distanza sotto la quale due sigle si sovrapporrebbero.
    const MIN_GAP_PX = 10;
    const placeInlineLabels = () => {
      // Livelli e chiusure manuali nella STESSA lista: cosi' le chiusure
      // ereditano la separazione a corsie gia' scritta per i livelli, invece di
      // avere un impianto proprio. Le chiusure portano il prezzo eseguito, che
      // e' un livello a tutti gli effetti per chi guarda.
      const voci: { key: string; price: number; tag: string; color: string; forte: boolean }[] = [
        ...model.levels.map((l) => ({
          key: l.key as string,
          price: l.price,
          tag: l.key === 'trl' && trailingGapPct != null ? `${l.tag} ${trailingGapPct}` : l.tag,
          color: l.color,
          forte: KEY_LEVELS.has(l.key) || l.strong,
        })),
        ...model.manualCloses.map((mc, i) => ({
          key: `manual-${i}`,
          price: mc.price,
          tag: `✂ ${mc.tag}`,
          color: LEVEL_COLORS.manual,
          forte: false,
        })),
      ];
      const placed = voci
        .map((level) => {
          const coordinate = series.priceToCoordinate(level.price);
          // priceToCoordinate NON torna null per i livelli fuori vista: restituisce
          // comunque un numero, negativo sopra il grafico o maggiore dell'altezza
          // sotto. Senza questo controllo, zoomando le sigle uscivano dal riquadro
          // e finivano sparse nella pagina (TP2 sopra la card, SL dentro la scheda
          // del trade). Chi esce non si disegna: il suo prezzo resta comunque
          // leggibile nella scala di destra finche' la linea e' in vista.
          if (coordinate == null) return null;
          const y = coordinate as number;
          if (y - LABEL_OFFSET_PX < 0 || y > height) return null;
          return {
            key: level.key,
            text: level.tag,
            color: level.color,
            bold: level.forte,
            top: coordinate as number,
            lane: 0,
          };
        })
        .filter((label): label is NonNullable<typeof label> => label != null)
        .sort((a, b) => a.top - b.top);
      // Livelli quasi coincidenti (tipico di E e BE): la sigla NON si sposta in
      // alto — resterebbe a un'altezza che non e' quella della sua linea — ma si
      // affianca in una colonna piu' a sinistra, restando allineata al suo prezzo.
      let previousTop = -Infinity;
      let lane = 0;
      for (const label of placed) {
        lane = label.top - previousTop < MIN_GAP_PX ? lane + 1 : 0;
        label.lane = lane;
        previousTop = label.top;
      }
      const axisWidth = series.priceScale().width();
      const signature = `${axisWidth}|${placed
        .map((l) => `${l.key}:${Math.round(l.top)}:${l.lane}:${l.text}`)
        .join(',')}`;
      if (signature === lastPlacementRef.current) return;
      lastPlacementRef.current = signature;
      setInlineLabels(placed);
      setPriceAxisWidth(axisWidth);
    };
    placeInlineLabels();
    c.timeScale().subscribeVisibleLogicalRangeChange(placeInlineLabels);

    // Trascinando la scala dei prezzi la libreria non emette eventi: senza questo
    // le sigle resterebbero ferme mentre le linee si spostano. Il ricalcolo gira
    // solo mentre un dito e' sul grafico, non a vuoto.
    let interacting = false;
    let frame = 0;
    const followGesture = () => {
      if (!interacting) return;
      placeInlineLabels();
      frame = requestAnimationFrame(followGesture);
    };
    const onPointerDown = (event: PointerEvent) => {
      // Toccando la scala dei prezzi si passa alla scala manuale: senza questo il
      // range imposto dal modello verrebbe riapplicato a ogni ridisegno e il
      // trascinamento verticale non avrebbe alcun effetto visibile.
      const fromRight = container.clientWidth - event.offsetX;
      if (fromRight <= series.priceScale().width()) {
        series.priceScale().setAutoScale(false);
      }
      if (interacting) return;
      interacting = true;
      frame = requestAnimationFrame(followGesture);
    };
    const onPointerUp = () => {
      if (!interacting) return;
      interacting = false;
      cancelAnimationFrame(frame);
      placeInlineLabels();
    };
    container.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);

    const onResize = () => {
      c.applyOptions({ width: container.clientWidth });
      placeInlineLabels();
    };
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      container.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);
      cancelAnimationFrame(frame);
      c.timeScale().unsubscribeVisibleLogicalRangeChange(placeInlineLabels);
      c.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [model, height, trailingGapPct, chart.live]);

  if (model === null) {
    return <p className="text-xs text-gray-500">Grafico non disponibile per questo trade.</p>;
  }
  return (
    <div style={{ position: 'relative', width: '100%', height, overflow: 'hidden' }}>
      <div ref={containerRef} style={{ width: '100%', height }} />
      {inlineLabels.map((label) => (
        <span
          key={label.key}
          style={{
            position: 'absolute',
            // Appoggiata SOPRA la linea e allineata a destra, come nel grafico
            // attuale: sta nello spazio vuoto fra un livello e l'altro invece di
            // passare davanti alle candele.
            right: priceAxisWidth + 4 + label.lane * 26,
            // Appena sopra la linea, con un po' d'aria: lo scostamento e' fisso e
            // uguale per tutte, cosi' resta chiaro a quale livello appartengono.
            top: label.top - LABEL_OFFSET_PX,
            fontSize: 7,
            lineHeight: '9px',
            fontWeight: label.bold ? 600 : 400,
            color: label.color,
            // Il grafico sotto e' scuro ma le candele passano: un alone tiene leggibile
            // l'etichetta senza coprire il prezzo.
            textShadow: '0 0 3px #0b0e11, 0 0 3px #0b0e11',
            pointerEvents: 'none',
            whiteSpace: 'nowrap',
            zIndex: 2,
          }}
        >
          {label.text}
        </span>
      ))}
    </div>
  );
};
