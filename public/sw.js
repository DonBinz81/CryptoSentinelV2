// SW auto-distruttivo: prende il controllo immediatamente, cancella tutte le cache
// e lascia che le risorse vengano servite direttamente dall'APK (Capacitor)
self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
