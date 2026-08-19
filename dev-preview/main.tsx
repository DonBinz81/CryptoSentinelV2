// Punto di ingresso del banco di anteprima. QUESTO FILE SI SOSTITUISCE:
// monta qui il componente che vuoi guardare, con dati finti.
//
// Esempio (pannello Setup):
//   import { SetupPane } from '../src/components/AgentTab';
//   import { defaultSettings } from '../src/components/agentDefaults';
//   ...poi passa `settings={defaultSettings}` e callback vuote.
//
// Regole del banco: nessuna chiamata al backend, nessun dato reale, e a lavoro
// finito si ripristina questo file com'era (vedi README.md).
import { createRoot } from 'react-dom/client';
import '../src/index.css';

const Istruzioni = () => (
  <div className="min-h-screen bg-dark-900 p-6 text-white">
    <h1 className="text-lg font-bold">Banco di anteprima</h1>
    <p className="mt-2 max-w-xl text-sm text-gray-400">
      Il banco funziona. Ora apri <code className="text-accent-blue">dev-preview/main.tsx</code> e
      sostituisci questo componente con quello che vuoi guardare, passandogli dati finti.
    </p>
    <div className="mt-4 max-w-xl rounded-lg border border-dark-600 bg-dark-800 p-4 text-xs leading-6 text-gray-300">
      <p className="font-semibold text-white">Promemoria</p>
      <p>· nessuna chiamata al backend: i dati si scrivono a mano</p>
      <p>· il <code>.env</code> reale non viene letto (envDir → cartella vuota)</p>
      <p>· a lavoro finito, riporta questo file com'era</p>
    </div>
  </div>
);

createRoot(document.getElementById('root')!).render(<Istruzioni />);
