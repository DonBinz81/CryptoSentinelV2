# Report - Fix caricamento dettagli trade mobile

## 1. COSA È STATO FATTO

- Corretto il caricamento dei dettagli trade quando il grafico OHLCV live/post-close e' lento o non disponibile.
- Aggiunta cache in memoria lato app per riaprire rapidamente dettagli gia' caricati.
- Aggiunto preload leggero dei dettagli piu' probabili nel pannello Spot/Perp attivo.
- Aggiunto un pulsante di annullamento durante il caricamento del dettaglio.

## 2. COME È STATO FATTO

- Il backend mantiene il dettaglio trade come risposta principale e rende il grafico best-effort con timeout bounded.
- Le chiamate Binance/fallback CEX usate solo per arricchire il grafico non possono piu' bloccare a lungo l'endpoint `trade-detail`.
- Il frontend memorizza i dettagli in una cache TTL limitata e precarica solo posizioni aperte e pochi trade recenti del pannello attivo.
- Quando un dettaglio e' in cache viene mostrato subito e aggiornato in background.

## 3. COSA È STATO VERIFICATO

- `npm exec tsc -- -b --pretty false`
- `backend\.venv\Scripts\python.exe -c "import backend.app.api.routes.views as views; print(views.TRADE_DETAIL_CHART_TIMEOUT_SECONDS)"`

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Resta utile una verifica manuale su dispositivo/emulatore con rete lenta per confermare l'esperienza reale.

## 6. STATO DELIVERABLE

- Implementato, in attesa dei controlli finali.
