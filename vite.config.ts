import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync, existsSync } from 'fs'
import { load as loadYaml } from 'js-yaml'

const pkg = JSON.parse(readFileSync('./package.json', 'utf-8')) as { version: string }

// Legge backend_api_base_url da instance.yaml se presente, altrimenti usa la variabile d'ambiente.
// In sviluppo locale il valore è in configs/instance.yaml (gitignored).
// In CI il valore arriva dal secret VITE_BACKEND_API_BASE_URL.
function readBackendUrl(): string {
  const yamlPath = './configs/instance.yaml'
  if (existsSync(yamlPath)) {
    const doc = loadYaml(readFileSync(yamlPath, 'utf-8')) as Record<string, unknown>
    const url = (doc?.frontend as Record<string, unknown>)?.backend_api_base_url as string | undefined
    if (url) return url
  }
  return process.env.VITE_BACKEND_API_BASE_URL ?? ''
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_BUILD_DATE__: JSON.stringify(new Date().toISOString()),
    __APP_VERSION__: JSON.stringify(pkg.version),
    __APP_BUILD_NUMBER__: JSON.stringify(process.env.BUILD_NUMBER ?? 'dev'),
    'import.meta.env.VITE_BACKEND_API_BASE_URL': JSON.stringify(readBackendUrl()),
  },
})
