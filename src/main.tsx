import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';

// Rimuove il service worker (non necessario in Capacitor — causa stale cache dopo aggiornamenti APK)
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    regs.forEach((r) => r.unregister());
  });
}
if ('caches' in window) {
  caches.keys().then((keys) => keys.forEach((k) => caches.delete(k)));
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
