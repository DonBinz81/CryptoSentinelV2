// Configurazione SOLO per l'anteprima locale del grafico.
// envDir punta a una cartella VUOTA dedicata: nessun .env del progetto viene letto.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: here,
  envDir: join(here, 'env-vuoto'),
  plugins: [react()],
  server: { port: 5199, fs: { allow: ['..'] } },
});
