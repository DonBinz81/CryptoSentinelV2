// Banco di anteprima: monta un pezzo dell'interfaccia nel browser con dati finti,
// senza backend e senza toccare il progetto vero.
//
// Il punto delicato e' `envDir`: punta a una cartella deliberatamente vuota dentro
// questa stessa directory, cosi' Vite non legge MAI il .env reale che sta nella root
// del progetto. E' la via ammessa da AGENTS.md per lavorare in locale sull'interfaccia
// ("niente build frontend in locale" vale per la build vera, non per un ambiente
// isolato che non vede i segreti).
//
// Uso: vedi dev-preview/README.md
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: here,
  envDir: join(here, 'env-vuoto'),
  plugins: [react()],
  // Le costanti che l'app si aspetta a compilazione: qui valori finti, perche'
  // il banco non e' una build di produzione.
  define: {
    __APP_BUILD_DATE__: JSON.stringify('1970-01-01T00:00:00Z'),
    __APP_VERSION__: JSON.stringify('anteprima'),
    __APP_BUILD_NUMBER__: JSON.stringify('anteprima'),
    'import.meta.env.VITE_BACKEND_API_BASE_URL': JSON.stringify(''),
  },
  // fs.allow: '..' serve a importare i componenti da src/ restando fuori dalla root.
  server: { port: 5199, fs: { allow: ['..'] } },
});
