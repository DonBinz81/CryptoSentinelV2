# Report - Dettaglio trade rapido e cache grafico

## 1. COSA È STATO FATTO

- Separato il caricamento del dettaglio trade dal caricamento arricchito del grafico.
- Aggiunta cache frontend che conserva il dettaglio con grafico completo durante la sessione.
- Impedite nuove chiamate backend per lo stesso trade quando in cache esiste gia' il grafico con le candele.
- Aggiunti timeout espliciti al client API per evitare spinner prolungati.

## 2. COME È STATO FATTO

- L'endpoint `trade-detail` ora carica il grafico live/post-close solo con `enrich_chart=true`.
- L'app apre il dettaglio con richiesta base fail-fast e poi prova l'arricchimento in background.
- Se il dettaglio cached contiene `chart.candles`, la richiesta successiva dello stesso trade usa solo la cache.
- I refresh automatici non ricaricano il dettaglio se la cache contiene gia' un grafico completo.

## 3. COSA È STATO VERIFICATO

- `npm exec tsc -- -b --pretty false`
- `backend\.venv\Scripts\python.exe -c "import backend.app.api.routes.views as views; print(views.TRADE_DETAIL_CHART_TIMEOUT_SECONDS)"`

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Resta utile una verifica manuale su dispositivo reale con rete lenta.

## 6. STATO DELIVERABLE

- Implementato, in attesa dei controlli finali.
