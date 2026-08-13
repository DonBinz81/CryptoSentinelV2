import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  root: __dirname,
  envDir: path.resolve(__dirname, 'env'),
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5176,
    strictPort: true,
  },
  preview: {
    host: '0.0.0.0',
    port: 5176,
    strictPort: true,
  },
  build: {
    outDir: path.resolve(__dirname, '../dist-dashboard'),
    emptyOutDir: true,
  },
});
