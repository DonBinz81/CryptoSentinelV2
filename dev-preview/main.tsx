// Banco di anteprima del grafico della posizione.
// Monta SOLO il componente del grafico con dati finti: nessuna chiamata al backend,
// nessuna variabile d'ambiente, nessun contatto con la VPS.
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '../src/index.css';
import { TradeCandleChart } from '../src/components/TradeCandleChart';
import { TradeCandleChartLW } from '../src/components/TradeCandleChartLW';
import { CASI } from './fixtures';

function App() {
  return (
    <div className="min-h-screen bg-dark-900 p-4 text-gray-200">
      <h1 className="mb-1 text-lg font-bold text-white">Anteprima — grafico della posizione</h1>
      <p className="mb-4 text-xs text-gray-500">
        Confronto: sopra il grafico attuale, sotto quello nuovo. Stessi dati finti, larghezza come sul telefono.
      </p>
      <div className="space-y-4">
        {CASI.map((caso) => (
          <section key={caso.nome} className="rounded-xl bg-dark-800 px-4 py-4">
            <h2 className="text-sm font-semibold text-white">{caso.nome}</h2>
            <p className="mb-3 text-xs text-gray-500">{caso.descrizione}</p>
            <div className="space-y-4">
              <div style={{ width: '100%', maxWidth: 420 }}>
                <p className="mb-1 text-xs font-semibold text-gray-400">ATTUALE (SVG a mano)</p>
                <div className="rounded-lg bg-dark-900 p-2">
                  <TradeCandleChart
                    chart={caso.chart}
                    breakeven={caso.breakeven}
                    trailing={caso.trailing}
                    smartSlLevels={caso.smartSlLevels}
                    smartSlState={caso.smartSlState}
                  />
                </div>
              </div>
              <div style={{ width: '100%', maxWidth: 420 }}>
                <p className="mb-1 text-xs font-semibold text-accent-green">NUOVO (lightweight-charts) — zoom e trascinamento attivi</p>
                <div className="rounded-lg bg-dark-900 p-2">
                  <TradeCandleChartLW
                    chart={caso.chart}
                    breakeven={caso.breakeven}
                    trailing={caso.trailing}
                    smartSlLevels={caso.smartSlLevels}
                    smartSlState={caso.smartSlState}
                  />
                </div>
              </div>
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

// Il banco viene ricaricato a caldo a ogni modifica: la radice React va riusata,
// altrimenti React segnala che il contenitore ha gia' una radice.
const container = document.getElementById('root')! as HTMLElement & { __root?: ReturnType<typeof createRoot> };
container.__root ??= createRoot(container);
container.__root.render(
  <StrictMode>
    <App />
  </StrictMode>,
);
