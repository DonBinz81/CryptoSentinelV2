# Report - Trade detail Perp timeout fix

## 1. COSA È STATO FATTO

- Analizzato il problema di caricamento selettivo dei dettagli Perp, citato su AVAX e INJ short.
- Ridotto il carico generato dal preload dei dettagli nella tab mobile agente.
- Migliorato il backend del dettaglio trade per riusare la cache recente delle klines già alimentata dal signal engine.

## 2. COME È STATO FATTO

- Dai log `logs/backend.log` è emerso che diversi endpoint `trade-detail` rispondevano `200`, ma dopo circa 14-19 secondi, mentre il frontend applicava timeout più stretti.
- In `src/components/AgentTab.tsx` il preload della prima pagina scarica ora solo il dettaglio base, senza avviare subito l'enrichment grafico per tutti i trade.
- L'enrichment del grafico resta attivo quando l'utente apre un dettaglio, ma parte dopo che il dettaglio base può essere mostrato.
- In `backend/app/api/routes/views.py` i grafici live/post-close provano prima a leggere klines recenti dalla cache del feed Binance/Perp prima di chiamare di nuovo Binance/fallback CEX.

## 3. COSA È STATO VERIFICATO

- Eseguito `npm run build` con esito positivo.
- Eseguito `python -m compileall backend\app\api\routes\views.py` con esito positivo.
- Verificato che le modifiche sono limitate al caricamento dettagli trade e alla documentazione.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno: non sono state modificate strategie, risk management, execution provider o parametri operativi del bot.

## 5. QUESTIONI APERTE

- Da verificare su app reale che AVAX/INJ Perp short aprano subito il dettaglio base e che il grafico si completi quando le candele sono disponibili.
- Se un simbolo non è coperto da Binance/fallback o il CEX impiega troppo, il grafico può restare assente, ma il dettaglio non deve più restare bloccato sullo spinner.

## 6. STATO DELIVERABLE

- Deliverable completato lato codice e build.
