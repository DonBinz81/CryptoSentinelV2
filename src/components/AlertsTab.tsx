import { useState, useRef, useEffect, type FC } from 'react';
import type { PriceAlert, Coin, AlertDirection, AlertHistoryEntry, RangeAlert, PriceAlertTriggerOptions } from '../types';
import { hapticMedium, hapticLight } from '../utils/haptics';

// Slider personalizzato con pointer events — aggiornamento DOM diretto durante drag
// per evitare il jank causato dai re-render React ad ogni frame
const computeThumbColor = (v: number): string => {
  const dev = v - 50;
  if (Math.abs(dev) < 0.4) return '#6b7280';
  return dev > 0 ? '#22c55e' : '#ef4444';
};

interface SmoothSliderProps {
  value: number;       // 0–100
  onChange: (v: number) => void;
  markerAt?: number;   // 0–100, linea prezzo corrente
}

const SmoothSlider: FC<SmoothSliderProps> = ({ value, onChange, markerAt }) => {
  const trackRef = useRef<HTMLDivElement>(null);
  const thumbRef = useRef<HTMLDivElement>(null);
  const fillRef  = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const rafId    = useRef<number | null>(null);
  const lastVal  = useRef(value);

  const applyDOM = (v: number) => {
    const c = computeThumbColor(v);
    if (thumbRef.current) { thumbRef.current.style.left = `${v}%`; thumbRef.current.style.background = c; }
    if (fillRef.current)  { fillRef.current.style.width = `${v}%`; fillRef.current.style.background = c; }
  };

  // Sincronizza React → DOM quando non si sta trascinando
  useEffect(() => { if (!dragging.current) applyDOM(value); }, [value]); // eslint-disable-line react-hooks/exhaustive-deps

  const pxToVal = (clientX: number): number => {
    const rect = trackRef.current!.getBoundingClientRect();
    return Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
  };

  const scheduleUpdate = (v: number) => {
    lastVal.current = v;
    if (rafId.current !== null) return;
    rafId.current = requestAnimationFrame(() => { rafId.current = null; onChange(lastVal.current); });
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragging.current = true;
    trackRef.current!.setPointerCapture(e.pointerId);
    const v = pxToVal(e.clientX);
    applyDOM(v);
    scheduleUpdate(v);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    const v = pxToVal(e.clientX);
    applyDOM(v);
    scheduleUpdate(v);
  };

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    dragging.current = false;
    if (rafId.current !== null) { cancelAnimationFrame(rafId.current); rafId.current = null; }
    const v = pxToVal(e.clientX);
    applyDOM(v);
    onChange(v);
  };

  const initColor = computeThumbColor(value);
  return (
    <div
      ref={trackRef}
      className="relative h-8 flex items-center cursor-pointer touch-none select-none"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div className="absolute left-0 right-0 h-1.5 bg-dark-600 rounded-full overflow-hidden">
        <div ref={fillRef} className="h-full rounded-full" style={{ width: `${value}%`, background: initColor }} />
      </div>
      {markerAt !== undefined && (
        <div
          className="absolute top-1 bottom-1 w-0.5 bg-accent-blue/70 rounded-full pointer-events-none"
          style={{ left: `${markerAt}%`, transform: 'translateX(-50%)' }}
        />
      )}
      <div
        ref={thumbRef}
        className="absolute w-5 h-5 rounded-full shadow-lg pointer-events-none border-2 border-dark-900"
        style={{ left: `${value}%`, transform: 'translateX(-50%)', background: initColor }}
      />
    </div>
  );
};

interface Props {
  alerts: PriceAlert[];
  onRemove: (id: string) => void;
  onReset: (id: string) => void;
  coins: Coin[];
  onEdit: (
    id: string,
    threshold: number,
    direction: AlertDirection,
    percentChange?: number,
    note?: string,
    triggerOptions?: PriceAlertTriggerOptions,
  ) => void;
  history: AlertHistoryEntry[];
  onClearHistory: () => void;
  sliderRange: number;
  rangeAlerts: RangeAlert[];
  onRemoveRange: (id: string) => void;
  onEditRange: (id: string, minPrice: number, maxPrice: number, note?: string) => void;
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString('it-IT', { maximumFractionDigits: 0 });
  if (price >= 1) return price.toFixed(2);
  return price.toFixed(6);
}

function parseNum(s: string): number {
  let clean = s.trim().replace(/[^\d.,-]/g, '');
  const lastDot = clean.lastIndexOf('.');
  const lastComma = clean.lastIndexOf(',');
  if (lastDot !== -1 && lastComma !== -1) {
    clean = lastComma > lastDot
      ? clean.replace(/\./g, '').replace(',', '.')
      : clean.replace(/,/g, '');
  } else if (lastComma !== -1) {
    const after = clean.slice(lastComma + 1);
    clean = after.length === 3 ? clean.replace(',', '') : clean.replace(',', '.');
  }
  return parseFloat(clean);
}

const AlertsTab: FC<Props> = ({ alerts, onRemove, onReset, coins, onEdit, history, onClearHistory, sliderRange, rangeAlerts, onRemoveRange, onEditRange }) => {
  const [showHistory, setShowHistory] = useState(false);
  const [showRangeAlerts, setShowRangeAlerts] = useState(true);

  const active = alerts.filter((a) => !a.triggered);
  const triggered = alerts.filter((a) => a.triggered);

  if (alerts.length === 0 && history.length === 0 && rangeAlerts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center px-8">
        <div className="text-5xl mb-4">🔔</div>
        <h3 className="text-white font-semibold text-lg mb-2">Nessun allarme</h3>
        <p className="text-gray-500 text-sm">
          Premi il 🔔 accanto a una criptovaluta per impostare un allarme di prezzo.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {triggered.length > 0 && (
        <div>
          <h3 className="text-accent-yellow text-xs font-semibold uppercase tracking-wide px-1 mb-2">
            ✅ Scattati ({triggered.length})
          </h3>
          {triggered.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              onRemove={onRemove}
              onReset={onReset}
              onEdit={onEdit}
              coin={coins.find((c) => c.id === alert.coinId)}
              sliderRange={sliderRange}
            />
          ))}
        </div>
      )}

      {active.length > 0 && (
        <div>
          <h3 className="text-gray-400 text-xs font-semibold uppercase tracking-wide px-1 mb-2">
            Attivi ({active.length})
          </h3>
          {active.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              onRemove={onRemove}
              onReset={onReset}
              onEdit={onEdit}
              coin={coins.find((c) => c.id === alert.coinId)}
              sliderRange={sliderRange}
            />
          ))}
        </div>
      )}

      {rangeAlerts.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setShowRangeAlerts((v) => !v)}
            className="flex items-center justify-between w-full px-1 mb-2 group"
          >
            <h3 className="text-accent-blue text-xs font-semibold uppercase tracking-wide group-hover:text-blue-300 transition-colors">
              ↔ Alert Range Price ({rangeAlerts.length})
            </h3>
            <span className="text-gray-600 text-xs">{showRangeAlerts ? '▲' : '▼'}</span>
          </button>

          {showRangeAlerts && (
            <div className="space-y-2">
              {rangeAlerts.map((alert) => (
                <RangeAlertRow
                  key={alert.id}
                  alert={alert}
                  onRemove={onRemoveRange}
                  onEdit={onEditRange}
                  coin={coins.find((c) => c.id === alert.coinId)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {history.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setShowHistory((v) => !v)}
            className="flex items-center justify-between w-full px-1 mb-2 group"
          >
            <h3 className="text-gray-500 text-xs font-semibold uppercase tracking-wide group-hover:text-gray-300 transition-colors">
              📋 Storico ({history.length})
            </h3>
            <span className="text-gray-600 text-xs">{showHistory ? '▲' : '▼'}</span>
          </button>

          {showHistory && (
            <>
              <div className="space-y-1.5">
                {history.map((entry) => (
                  <HistoryRow key={entry.id} entry={entry} />
                ))}
              </div>
              <button
                onClick={onClearHistory}
                className="mt-3 w-full py-2 text-xs text-accent-red/70 hover:text-accent-red bg-accent-red/5 hover:bg-accent-red/10 rounded-xl transition-colors"
              >
                Cancella storico
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
};

interface AlertRowProps {
  alert: PriceAlert;
  onRemove: (id: string) => void;
  onReset: (id: string) => void;
  onEdit: (
    id: string,
    threshold: number,
    direction: AlertDirection,
    percentChange?: number,
    note?: string,
    triggerOptions?: PriceAlertTriggerOptions,
  ) => void;
  coin?: Coin;
  sliderRange: number;
}

const AlertRow: FC<AlertRowProps> = ({ alert, onRemove, onReset, onEdit, coin, sliderRange }) => {
  const [editing, setEditing] = useState(false);
  const [sliderValue, setSliderValue] = useState(50);
  const [draftThreshold, setDraftThreshold] = useState(alert.threshold);
  const [draftDirection, setDraftDirection] = useState<AlertDirection>(alert.direction);
  const [editField, setEditField] = useState<'price' | 'percent' | null>(null);
  const [priceInput, setPriceInput] = useState('');
  const [pctInput, setPctInput] = useState('');
  const [draftNote, setDraftNote] = useState(alert.note ?? '');
  const [draftCrossingOnly, setDraftCrossingOnly] = useState(alert.crossingOnly === true);
  const [draftKeepActive, setDraftKeepActive] = useState(alert.keepActiveAfterTrigger === true);
  const [draftRearmPct, setDraftRearmPct] = useState(String(alert.rearmPercent ?? 0));

  const isAbove = alert.direction === 'above';
  const pivotPrice = coin?.current_price ?? alert.threshold;
  const sliderMin = pivotPrice * (1 - sliderRange / 100);
  const sliderMax = pivotPrice * (1 + sliderRange / 100);

  const thresholdToSlider = (t: number) =>
    Math.max(0, Math.min(100, ((t - sliderMin) / (sliderMax - sliderMin)) * 100));

  const applyNewThreshold = (t: number) => {
    setDraftThreshold(t);
    setSliderValue(thresholdToSlider(t));
    if (coin) setDraftDirection(t >= coin.current_price ? 'above' : 'below');
  };

  const handleOpenEdit = () => {
    setSliderValue(thresholdToSlider(alert.threshold));
    setDraftThreshold(alert.threshold);
    setDraftDirection(alert.direction);
    setDraftNote(alert.note ?? '');
    setDraftCrossingOnly(alert.crossingOnly === true);
    setDraftKeepActive(alert.keepActiveAfterTrigger === true);
    setDraftRearmPct(String(alert.rearmPercent ?? 0));
    setEditField(null);
    setEditing(true);
  };

  const handleSliderChange = (val: number) => {
    setEditField(null);
    setSliderValue(val);
    const newThreshold = sliderMin + (val / 100) * (sliderMax - sliderMin);
    setDraftThreshold(newThreshold);
    if (coin) setDraftDirection(newThreshold >= coin.current_price ? 'above' : 'below');
  };

  const handleSave = () => {
    const newPct = coin
      ? Math.abs((draftThreshold - coin.current_price) / coin.current_price * 100)
      : undefined;
    const rearmPercent = Math.max(0, Number.parseFloat(draftRearmPct.replace(',', '.')) || 0);
    onEdit(alert.id, draftThreshold, draftDirection, newPct, draftNote.trim() || undefined, {
      crossingOnly: draftCrossingOnly,
      keepActiveAfterTrigger: draftCrossingOnly && draftKeepActive,
      rearmPercent: draftCrossingOnly && draftKeepActive ? rearmPercent : 0,
    });
    setEditing(false);
  };

  const openPriceField = () => {
    const raw = draftThreshold >= 1000
      ? String(Math.round(draftThreshold))
      : draftThreshold >= 1 ? draftThreshold.toFixed(2) : draftThreshold.toFixed(6);
    setPriceInput(raw);
    setEditField('price');
  };

  const openPctField = (pct: number) => {
    setPctInput(Math.abs(pct).toFixed(2));
    setEditField('percent');
  };

  const currentPricePercent = coin ? 50 : null;
  const pct = coin ? ((draftThreshold - coin.current_price) / coin.current_price) * 100 : null;

  return (
    <div className={`rounded-xl mb-2 border overflow-hidden transition-all ${
      alert.triggered ? 'bg-dark-700 border-accent-yellow/30' : 'bg-dark-800 border-dark-600'
    }`}>
      <div
        className="flex items-center gap-3 p-3 cursor-pointer select-none"
        onClick={() => !editing && handleOpenEdit()}
      >
        <img src={alert.coinImage} alt={alert.coinName} className="w-8 h-8 rounded-full flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1 flex-wrap">
            <span className="text-white text-sm font-semibold">{alert.coinName}</span>
            {alert.triggered && (
              <span className="text-xs bg-accent-yellow/20 text-accent-yellow px-1.5 py-0.5 rounded-full">Scattato</span>
            )}
            {alert.crossingOnly && !alert.triggered && (
              <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                alert.waitingForRearm ? 'bg-accent-yellow/15 text-accent-yellow' : 'bg-accent-blue/15 text-accent-blue'
              }`}>
                {alert.waitingForRearm ? 'Riarmo' : 'Cross'}
              </span>
            )}
            {alert.lastCrossDirection && (
              <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                alert.lastCrossDirection === 'up' ? 'bg-accent-green/10 text-accent-green' : 'bg-accent-red/10 text-accent-red'
              }`}>
                {alert.lastCrossDirection === 'up' ? 'Up' : 'Down'}
              </span>
            )}
            {alert.triggered && alert.triggeredAt && (
              <span className="text-xs text-gray-500">
                {new Date(alert.triggeredAt).toLocaleString('it-IT', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>
          <div className={`text-xs mt-0.5 flex items-center gap-1.5 ${isAbove ? 'text-accent-green' : 'text-accent-red'}`}>
            {isAbove ? '▲ Sopra' : '▼ Sotto'} ${formatPrice(alert.threshold)}
            {alert.crossingOnly && (
              <span className="px-1.5 py-0.5 rounded-full text-xs font-semibold bg-accent-blue/10 text-accent-blue">
                Cross
              </span>
            )}
            {alert.percentChange != null && (
              <span className={`px-1.5 py-0.5 rounded-full text-xs font-semibold ${isAbove ? 'bg-accent-green/10' : 'bg-accent-red/10'}`}>
                {isAbove ? '+' : '-'}{alert.percentChange.toFixed(1)}%
              </span>
            )}
            {alert.crossingOnly && alert.keepActiveAfterTrigger && (
              <span className="px-1.5 py-0.5 rounded-full text-xs font-semibold bg-dark-600 text-gray-300">
                {Math.max(0, alert.rearmPercent ?? 0)}%
              </span>
            )}
          </div>
          {alert.note && (
            <div className="text-xs text-gray-500 mt-0.5 truncate max-w-[200px]">
              📝 {alert.note}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
          {alert.triggered && (
            <button
              onClick={() => { hapticLight(); onReset(alert.id); }}
              className="text-xs px-2 py-1 rounded-lg bg-dark-600 text-gray-300 hover:bg-dark-500 transition-colors"
              aria-label="Riattiva allarme"
            >↺</button>
          )}
          <button
            onClick={() => { hapticMedium(); onRemove(alert.id); }}
            className="p-1.5 rounded-lg bg-dark-700 hover:bg-dark-600 transition-colors flex items-center justify-center"
            style={{ color: '#8B95A7' }}
            aria-label="Elimina allarme"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      {editing && (
        <div className="px-3 pb-3 border-t border-dark-600">
          <div className="flex items-center justify-between pt-2.5 pb-2">
            <div className="flex items-center gap-2 flex-wrap">

              {editField === 'price' ? (
                <div className={`flex items-center gap-0.5 rounded-lg px-2 py-1 border border-accent-blue bg-dark-700`}>
                  <span className={`text-sm font-bold ${draftDirection === 'above' ? 'text-accent-green' : 'text-accent-red'}`}>
                    {draftDirection === 'above' ? '▲' : '▼'}&nbsp;$
                  </span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={priceInput}
                    onChange={e => {
                      setPriceInput(e.target.value);
                      const num = parseNum(e.target.value);
                      if (!isNaN(num) && num > 0) applyNewThreshold(num);
                    }}
                    onBlur={() => setEditField(null)}
                    onKeyDown={e => (e.key === 'Enter' || e.key === 'Escape') && setEditField(null)}
                    autoFocus
                    className="bg-transparent text-white w-24 text-sm font-bold tabular-nums outline-none"
                  />
                </div>
              ) : (
                <button
                  onClick={openPriceField}
                  className={`flex items-center gap-1 text-sm font-bold tabular-nums hover:opacity-70 transition-opacity ${
                    draftDirection === 'above' ? 'text-accent-green' : 'text-accent-red'
                  }`}
                >
                  {draftDirection === 'above' ? '▲' : '▼'}&nbsp;${formatPrice(draftThreshold)}
                </button>
              )}

              {coin && pct !== null && (
                editField === 'percent' ? (
                  <div className="flex items-center rounded-lg px-2 py-1 border border-accent-blue bg-dark-700">
                    <input
                      type="text"
                      inputMode="decimal"
                      value={pctInput}
                      onChange={e => {
                        setPctInput(e.target.value);
                        const num = parseFloat(e.target.value.replace(',', '.'));
                        if (!isNaN(num) && num > 0) {
                          const newT = draftDirection === 'above'
                            ? coin.current_price * (1 + num / 100)
                            : coin.current_price * (1 - num / 100);
                          applyNewThreshold(newT);
                        }
                      }}
                      onBlur={() => setEditField(null)}
                      onKeyDown={e => (e.key === 'Enter' || e.key === 'Escape') && setEditField(null)}
                      autoFocus
                      className="bg-transparent text-white w-14 text-xs font-semibold tabular-nums outline-none text-right"
                    />
                    <span className={`text-xs ml-0.5 ${pct >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>%</span>
                  </div>
                ) : (
                  <button
                    onClick={() => openPctField(pct)}
                    className={`flex items-center gap-0.5 text-xs font-semibold tabular-nums px-1.5 py-0.5 rounded-full hover:opacity-70 transition-opacity ${
                      pct >= 0 ? 'text-accent-green bg-accent-green/10' : 'text-accent-red bg-accent-red/10'
                    }`}
                  >
                    {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                    </button>
                )
              )}
            </div>

            {coin && (
              <span className="text-xs text-gray-500 flex-shrink-0">
                Ora: <span className="text-gray-300 font-medium">${formatPrice(coin.current_price)}</span>
              </span>
            )}
          </div>

          <SmoothSlider
            value={sliderValue}
            onChange={handleSliderChange}
            markerAt={currentPricePercent ?? undefined}
          />

          <div className="flex justify-between text-xs text-gray-600 mb-3 mt-0.5">
            <span>${formatPrice(sliderMin)}</span>
            <span className="text-gray-700">−{sliderRange}% · +{sliderRange}%</span>
            <span>${formatPrice(sliderMax)}</span>
          </div>

          <div className="mb-3 space-y-2">
            <button
              type="button"
              onClick={() => {
                setDraftCrossingOnly((value) => {
                  const next = !value;
                  if (!next) setDraftKeepActive(false);
                  return next;
                });
              }}
              className={`w-full flex items-center justify-between gap-3 rounded-lg px-3 py-2 border transition-colors ${
                draftCrossingOnly ? 'bg-accent-blue/10 border-accent-blue/40' : 'bg-dark-700 border-dark-600'
              }`}
            >
              <span className="text-xs font-semibold text-white">Solo crossing</span>
              <span className={`w-9 h-5 rounded-full p-0.5 flex-shrink-0 transition-colors ${draftCrossingOnly ? 'bg-accent-blue' : 'bg-dark-600'}`}>
                <span className={`block w-4 h-4 rounded-full bg-white transition-transform ${draftCrossingOnly ? 'translate-x-4' : ''}`} />
              </span>
            </button>
            {draftCrossingOnly && (
              <div className="grid grid-cols-[1fr_1fr_80px] gap-2">
                <button
                  type="button"
                  onClick={() => setDraftKeepActive(false)}
                  className={`py-2 rounded-lg text-xs font-semibold ${!draftKeepActive ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400'}`}
                >
                  1 volta
                </button>
                <button
                  type="button"
                  onClick={() => setDraftKeepActive(true)}
                  className={`py-2 rounded-lg text-xs font-semibold ${draftKeepActive ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400'}`}
                >
                  Continua
                </button>
                <div className="flex items-center bg-dark-700 rounded-lg px-2 border border-dark-600">
                  <input
                    type="number"
                    value={draftRearmPct}
                    onChange={(e) => setDraftRearmPct(e.target.value)}
                    disabled={!draftKeepActive}
                    className="w-full bg-transparent text-white py-2 outline-none text-xs text-right disabled:text-gray-600"
                    min="0"
                    step="0.1"
                  />
                  <span className="text-gray-500 text-xs ml-0.5">%</span>
                </div>
              </div>
            )}
          </div>

          <div className="mb-3">
            <label className="text-xs text-gray-500 mb-1 block">Nota</label>
            <textarea
              value={draftNote}
              onChange={(e) => setDraftNote(e.target.value)}
              placeholder="Aggiungi una nota…"
              rows={2}
              className="w-full bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 outline-none focus:border-accent-blue transition-colors resize-none"
            />
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setEditing(false)}
              className="flex-1 py-2 bg-dark-700 text-gray-400 text-sm rounded-lg hover:bg-dark-600 transition-colors"
            >Annulla</button>
            <button
              onClick={handleSave}
              className="flex-1 py-2 bg-accent-blue text-white text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity"
            >Salva</button>
          </div>
        </div>
      )}
    </div>
  );
};

interface RangeAlertRowProps {
  alert: RangeAlert;
  onRemove: (id: string) => void;
  onEdit: (id: string, minPrice: number, maxPrice: number, note?: string) => void;
  coin?: Coin;
}

const RangeAlertRow: FC<RangeAlertRowProps> = ({ alert, onRemove, onEdit, coin }) => {
  const [editing, setEditing] = useState(false);
  const [draftMin, setDraftMin] = useState(String(alert.minPrice >= 1 ? alert.minPrice.toFixed(2) : alert.minPrice.toFixed(6)));
  const [draftMax, setDraftMax] = useState(String(alert.maxPrice >= 1 ? alert.maxPrice.toFixed(2) : alert.maxPrice.toFixed(6)));
  const [draftNote, setDraftNote] = useState(alert.note ?? '');
  const [editError, setEditError] = useState('');

  const currentPrice = coin?.current_price;
  const isInside = alert.isInsideRange === true;
  const isUnknown = alert.isInsideRange === null;

  const priceBarPct = currentPrice != null
    ? Math.max(2, Math.min(98, ((currentPrice - alert.minPrice) / (alert.maxPrice - alert.minPrice)) * 100))
    : null;

  const handleOpenEdit = () => {
    setDraftMin(alert.minPrice >= 1 ? alert.minPrice.toFixed(2) : alert.minPrice.toFixed(6));
    setDraftMax(alert.maxPrice >= 1 ? alert.maxPrice.toFixed(2) : alert.maxPrice.toFixed(6));
    setDraftNote(alert.note ?? '');
    setEditError('');
    setEditing(true);
  };

  const handleSave = () => {
    const min = parseNum(draftMin);
    const max = parseNum(draftMax);
    if (isNaN(min) || min <= 0) { setEditError('Prezzo minimo non valido'); return; }
    if (isNaN(max) || max <= 0) { setEditError('Prezzo massimo non valido'); return; }
    if (min >= max) { setEditError('Il minimo deve essere inferiore al massimo'); return; }
    onEdit(alert.id, min, max, draftNote.trim() || undefined);
    setEditing(false);
  };

  return (
    <div className="rounded-xl mb-2 border overflow-hidden bg-dark-800 border-dark-600">
      <div
        className="flex items-center gap-3 p-3 cursor-pointer select-none"
        onClick={() => !editing && handleOpenEdit()}
      >
        <img src={alert.coinImage} alt={alert.coinName} className="w-8 h-8 rounded-full flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-white text-sm font-semibold">{alert.coinName}</span>
            {!isUnknown && (
              <span className={`text-xs px-1.5 py-0.5 rounded-full font-semibold ${
                isInside ? 'bg-accent-green/15 text-accent-green' : 'bg-gray-700 text-gray-400'
              }`}>
                {isInside ? '↔ Nel range' : '↗ Fuori range'}
              </span>
            )}
          </div>
          <div className="text-xs text-accent-blue mt-0.5">
            ${formatPrice(alert.minPrice)} – ${formatPrice(alert.maxPrice)}
          </div>
          {currentPrice != null && priceBarPct != null && (
            <div className="mt-1.5 relative h-1.5 bg-dark-600 rounded-full overflow-visible">
              <div className="absolute inset-0 bg-accent-blue/20 rounded-full" />
              <div
                className={`absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full border border-dark-900 ${isInside ? 'bg-accent-green' : 'bg-gray-400'}`}
                style={{ left: `${priceBarPct}%`, transform: 'translate(-50%, -50%)' }}
              />
            </div>
          )}
          {currentPrice != null && (
            <div className="text-xs text-gray-500 mt-1">
              Ora: <span className={`font-medium ${isInside ? 'text-accent-green' : 'text-gray-300'}`}>${formatPrice(currentPrice)}</span>
            </div>
          )}
          {alert.note && (
            <div className="text-xs text-gray-500 mt-0.5 truncate max-w-[200px]">📝 {alert.note}</div>
          )}
        </div>
        <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => { hapticMedium(); onRemove(alert.id); }}
            className="p-1.5 rounded-lg bg-dark-700 hover:bg-dark-600 transition-colors flex items-center justify-center"
            style={{ color: '#8B95A7' }}
            aria-label="Elimina"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      {editing && (
        <div className="px-3 pb-3 border-t border-dark-600">
          <div className="flex items-center justify-between pt-2.5 pb-2">
            <span className="text-xs text-gray-500">Modifica range</span>
            {coin && (
              <span className="text-xs text-gray-500">
                Ora: <span className="text-gray-300 font-medium">${formatPrice(coin.current_price)}</span>
              </span>
            )}
          </div>
          <div className="space-y-2 mb-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Prezzo minimo</label>
              <div className="flex items-center bg-dark-700 rounded-lg px-3 border border-dark-600 focus-within:border-accent-blue">
                <span className="text-gray-500 mr-1 text-sm">$</span>
                <input
                  type="text"
                  inputMode="decimal"
                  value={draftMin}
                  onChange={(e) => { setDraftMin(e.target.value); setEditError(''); }}
                  autoFocus
                  className="flex-1 bg-transparent text-white py-2 outline-none text-sm"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Prezzo massimo</label>
              <div className="flex items-center bg-dark-700 rounded-lg px-3 border border-dark-600 focus-within:border-accent-blue">
                <span className="text-gray-500 mr-1 text-sm">$</span>
                <input
                  type="text"
                  inputMode="decimal"
                  value={draftMax}
                  onChange={(e) => { setDraftMax(e.target.value); setEditError(''); }}
                  className="flex-1 bg-transparent text-white py-2 outline-none text-sm"
                />
              </div>
            </div>
          </div>
          {editError && <p className="text-accent-red text-xs mb-2">{editError}</p>}
          <div className="mb-3">
            <label className="text-xs text-gray-500 mb-1 block">Nota</label>
            <textarea
              value={draftNote}
              onChange={(e) => setDraftNote(e.target.value)}
              placeholder="Aggiungi una nota…"
              rows={2}
              className="w-full bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 outline-none focus:border-accent-blue transition-colors resize-none"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setEditing(false)}
              className="flex-1 py-2 bg-dark-700 text-gray-400 text-sm rounded-lg hover:bg-dark-600 transition-colors"
            >Annulla</button>
            <button
              onClick={handleSave}
              className="flex-1 py-2 bg-accent-blue text-white text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity"
            >Salva</button>
          </div>
        </div>
      )}
    </div>
  );
};

const HistoryRow: FC<{ entry: AlertHistoryEntry }> = ({ entry }) => {
  const isAbove = entry.direction === 'above';
  const label = entry.crossDirection === 'up' ? 'Cross up' : entry.crossDirection === 'down' ? 'Cross down' : isAbove ? 'Sopra' : 'Sotto';
  const priceDiff = ((entry.triggeredPrice - entry.threshold) / entry.threshold) * 100;
  const date = new Date(entry.triggeredAt);
  const dateStr = date.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' });
  const timeStr = date.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="flex items-center gap-2.5 bg-dark-800/60 rounded-xl px-3 py-2.5 border border-dark-700">
      <img src={entry.coinImage} alt={entry.coinName} className="w-7 h-7 rounded-full flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-white text-xs font-semibold">{entry.coinName}</span>
          <span className={`text-xs font-bold ${isAbove ? 'text-accent-green' : 'text-accent-red'}`}>
            {label} ${formatPrice(entry.triggeredPrice)}
          </span>
        </div>
        <div className="text-xs text-gray-500 mt-0.5">
          Soglia ${formatPrice(entry.threshold)} ·{' '}
          <span className={priceDiff >= 0 ? 'text-accent-green/70' : 'text-accent-red/70'}>
            {priceDiff >= 0 ? '+' : ''}{priceDiff.toFixed(1)}%
          </span>
        </div>
      </div>
      <div className="text-right flex-shrink-0">
        <div className="text-xs text-gray-500">{dateStr}</div>
        <div className="text-xs text-gray-600">{timeStr}</div>
      </div>
    </div>
  );
};

export default AlertsTab;
