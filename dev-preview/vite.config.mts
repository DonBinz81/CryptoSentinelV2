// Configurazione SOLO per l'anteprima locale del grafico.
// envDir punta a una cartella VUOTA fuori dal repo: nessun .env del progetto viene letto.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: here,
  envDir: 'C:/Users/RoBot/AppData/Local/Temp/claude/C--Users-RoBot-Documents-CryptoBot/9007259b-3397-4236-bb15-0e23901e1fe0/scratchpad/env_vuoto',
  plugins: [react()],
  server: { port: 5199, fs: { allow: ['..'] } },
});
