import { useState, useRef, type FC } from 'react';
import type { Coin, AlertDirection, PriceAlertTriggerOptions } from '../types';
import { hapticMedium, hapticLight } from '../utils/haptics';

interface Props {
  coin: Coin;
  onConfirm: (
    direction: AlertDirection,
    threshold: number,
    percentChange?: number,
    note?: string,
    triggerOptions?: PriceAlertTriggerOptions,
  ) => void;
  onConfirmRange: (minPrice: number, maxPrice: number, note?: string) => void;
  onClose: () => void;
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString('it-IT', { maximumFractionDigits: 0 });
  if (price >= 1) return price.toFixed(2);
  return price.toFixed(6);
}

function parsePrice(input: string): number {
  let s = input.trim();
  const dotCount = (s.match(/\./g) || []).length;
  const commaCount = (s.match(/,/g) || []).length;

  if (dotCount > 1) {
    // "1.234.567" → dots as thousands (Italian)
    s = s.replace(/\./g, '');
    if (commaCount === 1) s = s.replace(',', '.');
  } else if (commaCount > 1) {
    // "1,234,567" → commas as thousands
    s = s.replace(/,/g, '');
  } else if (dotCount === 1 && commaCount === 1) {
    // both present: last separator is decimal
    s = s.lastIndexOf(',') > s.lastIndexOf('.')
      ? s.replace(/\./g, '').replace(',', '.')
      : s.replace(/,/g, '');
  } else if (commaCount === 1) {
    const parts = s.split(',');
    // comma as thousands if followed by exactly 3 digits: "63,600"
    s = parts[1].length === 3 ? s.replace(',', '') : s.replace(',', '.');
  }
  // single dot or no separator: standard parseFloat

  return parseFloat(s);
}

type Mode = 'price' | 'percent' | 'range';

const AlertModal: FC<Props> = ({ coin, onConfirm, onConfirmRange, onClose }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const touchStartY = useRef(0);
  const [mode, setMode] = useState<Mode>('price');
  const [direction, setDirection] = useState<AlertDirection>('above');
  const [priceValue, setPriceValue] = useState(() => {
    const p = coin.current_price;
    if (p >= 1) return p.toFixed(2);
    return p.toFixed(6);
  });
  const [pctValue, setPctValue] = useState('5');
  const [rangeMin, setRangeMin] = useState(() => {
    const p = coin.current_price * 0.95;
    return p >= 1 ? p.toFixed(2) : p.toFixed(6);
  });
  const [rangeMax, setRangeMax] = useState(() => {
    const p = coin.current_price * 1.05;
    return p >= 1 ? p.toFixed(2) : p.toFixed(6);
  });
  const [crossingOnly, setCrossingOnly] = useState(false);
  const [keepActiveAfterTrigger, setKeepActiveAfterTrigger] = useState(false);
  const [rearmPct, setRearmPct] = useState('0.5');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const pctNum = parseFloat(pctValue.replace(',', '.'));
  const calcThreshold = !isNaN(pctNum)
    ? direction === 'above'
      ? coin.current_price * (1 + pctNum / 100)
      : coin.current_price * (1 - pctNum / 100)
    : null;

  const handleSubmit = () => {
    const trimmedNote = note.trim() || undefined;
    if (mode === 'range') {
      const min = parsePrice(rangeMin);
      const max = parsePrice(rangeMax);
      if (isNaN(min) || min <= 0) { setError('Inserisci un prezzo minimo valido'); return; }
      if (isNaN(max) || max <= 0) { setError('Inserisci un prezzo massimo valido'); return; }
      if (min >= max) { setError('Il prezzo minimo deve essere inferiore al massimo'); return; }
      onConfirmRange(min, max, trimmedNote);
      onClose();
      return;
    }
    const rearmNum = parseFloat(rearmPct.replace(',', '.'));
    if (crossingOnly && keepActiveAfterTrigger && (isNaN(rearmNum) || rearmNum < 0)) {
      setError('Riarmo non valido');
      return;
    }
    const triggerOptions: PriceAlertTriggerOptions = {
      crossingOnly,
      keepActiveAfterTrigger: crossingOnly && keepActiveAfterTrigger,
      rearmPercent: crossingOnly && keepActiveAfterTrigger ? rearmNum : 0,
    };
    if (mode === 'price') {
      const num = parsePrice(priceValue);
      if (isNaN(num) || num <= 0) {
        setError('Inserisci un prezzo valido maggiore di zero');
        return;
      }
      onConfirm(direction, num, undefined, trimmedNote, triggerOptions);
    } else {
      if (isNaN(pctNum) || pctNum <= 0) {
        setError('Inserisci una percentuale valida maggiore di zero');
        return;
      }
      if (calcThreshold === null || calcThreshold <= 0) {
        setError('Percentuale non valida');
        return;
      }
      onConfirm(direction, calcThreshold, pctNum, trimmedNote, triggerOptions);
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex flex-col justify-end" onClick={onClose}>
      <div
        className="bg-dark-800 rounded-t-3xl border-t border-dark-600 h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
        onTouchStart={e => { touchStartY.current = e.touches[0].clientY; }}
        onTouchEnd={e => {
          const deltaY = e.changedTouches[0].clientY - touchStartY.current;
          if (deltaY > 80 && (scrollRef.current?.scrollTop ?? 0) <= 0) onClose();
        }}
      >
        {/* Handle */}
        <div className="flex justify-center pt-3 pb-1 flex-shrink-0">
          <div className="w-9 h-1 bg-dark-600 rounded-full" />
        </div>

        {/* Scrollable body */}
        <div ref={scrollRef} className="overflow-y-auto flex-1 px-5 pb-8">

          {/* Intestazione */}
          <div className="flex items-center gap-3 py-4">
            <img src={coin.image} alt={coin.name} className="w-10 h-10 rounded-full flex-shrink-0" />
            <div>
              <h2 className="text-white font-bold text-lg leading-tight">Imposta Allarme</h2>
              <p className="text-gray-400 text-sm">
                {coin.name} · Ora: <span className="text-white">${formatPrice(coin.current_price)}</span>
              </p>
            </div>
          </div>

          {/* Toggle modalità */}
          <div className="flex gap-1 bg-dark-700 rounded-xl p-1 mb-4">
            <button
              onClick={() => { setMode('price'); setError(''); }}
              className={`flex-1 py-2 rounded-lg text-xs font-medium transition-colors ${
                mode === 'price' ? 'bg-dark-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              $ Fisso
            </button>
            <button
              onClick={() => { setMode('percent'); setError(''); }}
              className={`flex-1 py-2 rounded-lg text-xs font-medium transition-colors ${
                mode === 'percent' ? 'bg-dark-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              % Variaz.
            </button>
            <button
              onClick={() => { setMode('range'); setError(''); }}
              className={`flex-1 py-2 rounded-lg text-xs font-medium transition-colors ${
                mode === 'range' ? 'bg-dark-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              ↔ Range
            </button>
          </div>

          {/* Direzione — nascosta in modalità range */}
          {mode !== 'range' && (
            <div className="flex gap-2 mb-4">
              <button
                onClick={() => { hapticLight(); setDirection('above'); }}
                className={`flex-1 py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                  direction === 'above' ? 'bg-accent-green text-white' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
                }`}
              >
                ▲ Sopra
              </button>
              <button
                onClick={() => { hapticLight(); setDirection('below'); }}
                className={`flex-1 py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                  direction === 'below' ? 'bg-accent-red text-white' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
                }`}
              >
                ▼ Sotto
              </button>
            </div>
          )}

          {/* Input prezzo fisso */}
          {mode === 'price' && (
            <div className="mb-4">
              <label className="text-gray-400 text-xs mb-1.5 block">Prezzo soglia (USD)</label>
              <div className="flex items-center bg-dark-700 rounded-xl px-3 border border-dark-600 focus-within:border-accent-blue">
                <span className="text-gray-500 mr-1">$</span>
                <input
                  type="text"
                  inputMode="decimal"
                  value={priceValue}
                  onChange={(e) => {
                    const val = e.target.value;
                    setPriceValue(val);
                    setError('');
                    const num = parsePrice(val);
                    if (!isNaN(num) && num > 0) {
                      setDirection(num >= coin.current_price ? 'above' : 'below');
                    }
                  }}
                  onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
                  className="flex-1 bg-transparent text-white py-3 outline-none text-sm"
                  placeholder="0.00"
                  autoFocus
                />
              </div>
            </div>
          )}

          {/* Input percentuale */}
          {mode === 'percent' && (
            <div className="mb-4">
              <label className="text-gray-400 text-xs mb-1.5 block">Variazione dal prezzo attuale</label>
              <div className="flex items-center bg-dark-700 rounded-xl px-3 border border-dark-600 focus-within:border-accent-blue">
                <input
                  type="number"
                  value={pctValue}
                  onChange={(e) => { setPctValue(e.target.value); setError(''); }}
                  onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
                  className="flex-1 bg-transparent text-white py-3 outline-none text-sm"
                  placeholder="5"
                  step="0.1"
                  min="0.1"
                  autoFocus
                />
                <span className="text-gray-500 ml-1">%</span>
              </div>
              {calcThreshold !== null && !isNaN(pctNum) && pctNum > 0 && (
                <p className="text-xs text-gray-500 mt-1.5">
                  Soglia calcolata:{' '}
                  <span className={direction === 'above' ? 'text-accent-green font-medium' : 'text-accent-red font-medium'}>
                    ${formatPrice(calcThreshold)}
                  </span>
                </p>
              )}
            </div>
          )}

          {mode !== 'range' && (
            <div className="mb-4 space-y-2.5">
              <button
                type="button"
                onClick={() => {
                  hapticLight();
                  setCrossingOnly((value) => {
                    const next = !value;
                    if (!next) setKeepActiveAfterTrigger(false);
                    return next;
                  });
                }}
                className={`w-full flex items-center justify-between gap-3 rounded-xl px-3 py-2.5 border transition-colors ${
                  crossingOnly
                    ? 'bg-accent-blue/10 border-accent-blue/40'
                    : 'bg-dark-700 border-dark-600'
                }`}
              >
                <span className="text-left min-w-0">
                  <span className="block text-sm font-semibold text-white">Solo attraversamento</span>
                  <span className="block text-xs text-gray-500 truncate">Scatta quando passa la soglia</span>
                </span>
                <span className={`w-10 h-5 rounded-full p-0.5 flex-shrink-0 transition-colors ${crossingOnly ? 'bg-accent-blue' : 'bg-dark-600'}`}>
                  <span className={`block w-4 h-4 rounded-full bg-white transition-transform ${crossingOnly ? 'translate-x-5' : ''}`} />
                </span>
              </button>

              {crossingOnly && (
                <div className="bg-dark-700 border border-dark-600 rounded-xl p-3 space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setKeepActiveAfterTrigger(false)}
                      className={`py-2 rounded-lg text-xs font-semibold transition-colors ${
                        !keepActiveAfterTrigger ? 'bg-accent-blue text-white' : 'bg-dark-600 text-gray-400'
                      }`}
                    >
                      1 volta
                    </button>
                    <button
                      type="button"
                      onClick={() => setKeepActiveAfterTrigger(true)}
                      className={`py-2 rounded-lg text-xs font-semibold transition-colors ${
                        keepActiveAfterTrigger ? 'bg-accent-blue text-white' : 'bg-dark-600 text-gray-400'
                      }`}
                    >
                      Continua
                    </button>
                  </div>
                  {keepActiveAfterTrigger && (
                    <div>
                      <label className="text-gray-400 text-xs mb-1.5 block">Riarmo (%)</label>
                      <div className="flex items-center bg-dark-600 rounded-lg px-3 border border-dark-500 focus-within:border-accent-blue">
                        <input
                          type="number"
                          value={rearmPct}
                          onChange={(e) => { setRearmPct(e.target.value); setError(''); }}
                          className="flex-1 bg-transparent text-white py-2 outline-none text-sm"
                          placeholder="0.5"
                          step="0.1"
                          min="0"
                        />
                        <span className="text-gray-500 ml-1">%</span>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Input range price */}
          {mode === 'range' && (
            <div className="mb-4 space-y-3">
              <div>
                <label className="text-gray-400 text-xs mb-1.5 block">Prezzo minimo (USD)</label>
                <div className="flex items-center bg-dark-700 rounded-xl px-3 border border-dark-600 focus-within:border-accent-blue">
                  <span className="text-gray-500 mr-1">$</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={rangeMin}
                    onChange={(e) => { setRangeMin(e.target.value); setError(''); }}
                    onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
                    className="flex-1 bg-transparent text-white py-3 outline-none text-sm"
                    placeholder="0.00"
                    autoFocus
                  />
                </div>
              </div>
              <div>
                <label className="text-gray-400 text-xs mb-1.5 block">Prezzo massimo (USD)</label>
                <div className="flex items-center bg-dark-700 rounded-xl px-3 border border-dark-600 focus-within:border-accent-blue">
                  <span className="text-gray-500 mr-1">$</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={rangeMax}
                    onChange={(e) => { setRangeMax(e.target.value); setError(''); }}
                    onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
                    className="flex-1 bg-transparent text-white py-3 outline-none text-sm"
                    placeholder="0.00"
                  />
                </div>
              </div>
            </div>
          )}

          {error && <p className="text-accent-red text-xs mb-3">{error}</p>}

          {/* Nota opzionale */}
          <div className="mb-4">
            <label className="text-gray-400 text-xs mb-1.5 block">Nota (opzionale)</label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Es: Livello chiave di supporto, target TP…"
              rows={2}
              className="w-full bg-dark-700 border border-dark-600 rounded-xl px-3 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-accent-blue transition-colors resize-none"
            />
          </div>

          {/* Anteprima */}
          <div className="bg-dark-700 rounded-xl px-4 py-3 mb-5">
            <p className="text-gray-500 text-xs">
              {mode === 'range' ? (
                <>
                  Notifica quando <span className="text-white">{coin.name}</span> entra o esce dal range{' '}
                  <span className="text-accent-blue">${rangeMin || '…'} – ${rangeMax || '…'}</span>
                </>
              ) : (
                <>
                  {crossingOnly ? 'Attraversa' : `Notifica quando ${coin.name} andra`}{' '}
                  {!crossingOnly && (
                    <>
                      <span className={direction === 'above' ? 'text-accent-green' : 'text-accent-red'}>
                        {direction === 'above' ? 'sopra' : 'sotto'}
                      </span>{' '}
                    </>
                  )}
                  {mode === 'percent'
                    ? calcThreshold !== null && pctNum > 0
                      ? `$${formatPrice(calcThreshold)} (${direction === 'above' ? '+' : '-'}${pctValue}%)`
                      : '…'
                    : `$${priceValue || '…'}`}
                </>
              )}
            </p>
          </div>

          <div className="flex gap-3">
            <button onClick={() => { hapticLight(); onClose(); }} className="flex-1 py-3 rounded-xl bg-dark-700 text-gray-300 text-sm font-medium transition-colors">
              Annulla
            </button>
            <button onClick={() => { hapticMedium(); handleSubmit(); }} className="flex-1 py-3 rounded-xl bg-accent-blue text-white text-sm font-semibold transition-opacity hover:opacity-90">
              Crea Allarme
            </button>
          </div>

        </div>
      </div>
    </div>
  );
};

export default AlertModal;
