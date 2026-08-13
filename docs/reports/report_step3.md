# Report Step 3 - Astrazione Dati Multi-Provider

## 1. COSA È STATO FATTO

- Creata l'interfaccia astratta `MarketDataProvider` per prezzi, OHLCV, ricerca e market list.
- Creati modelli interni normalizzati per asset, identità provider, quote e barre OHLCV.
- Implementato `CMCProvider` come provider primario e predefinito.
- Integrato il codice CoinGecko esistente in `CoinGeckoProvider` senza eliminarlo o riscriverlo da zero.
- Creato `MarketDataRegistry` come selettore globale CMC/CoinGecko, senza fallback automatico.
- Aggiunti rate limiter asincrono, cache TTL, single-flight delle richieste concorrenti e monitoraggio crediti CMC.
- Aggiunti gli endpoint backend normalizzati:
  - `GET /api/v1/market-data/provider`
  - `PUT /api/v1/market-data/provider`
  - `GET /api/v1/market-data/markets`
  - `GET /api/v1/market-data/prices`
  - `GET /api/v1/market-data/search`
  - `GET /api/v1/market-data/ohlcv`
- Reso admin-only il cambio provider; il read token non può soddisfare controlli admin.
- Sostituito l'accesso diretto a CoinGecko nel checker notifiche con il registry multi-provider.
- Sostituite le chiamate provider dirette del frontend con `src/services/marketData.ts`.
- Aggiunta la configurazione ufficiale CMC MCP e il relativo stato non sensibile.
- Aggiunte chiavi i18n EN/IT per il dominio market data.
- Segmentate le richieste CMC OHLCV in finestre contigue di massimo 30 giorni.
- Mantenuti stabili gli ID applicativi storici CoinGecko e aggiunta la risoluzione verso gli ID nativi CMC.
- Aggiunti alias per asset legacy come `binancecoin/bnb`, `ripple/xrp` e `avalanche-2/avalanche`.
- Paginato il catalogo CMC `/v1/cryptocurrency/map` a blocchi da 5.000 fino a esaurimento.
- Corretta la ricerca CMC riutilizzando il catalogo completo e le quote normalizzate.
- Impedito che un simbolo CMC invalido blocchi l'intero batch di prezzi o il checker alert.
- Resi i preferiti indipendenti dal selettore Mercati `50/100/200/400/600`.
- Conservati gli ultimi dati validi dei preferiti durante errori temporanei o risposte obsolete.
- Aggiunto ai Preferiti l'ordinamento Rank, 24h, 7g, Volume e Prezzo con stato indipendente da Mercati.
- Aggiunto logging strutturato persistente con request ID, rotazione, diagnostica provider, cache, identità e checker.
- Aggiunto un gate CI che blocca APK privi delle variabili Vite obbligatorie senza stamparne i valori.
- Aggiunti nei ringraziamenti sia CoinGecko sia CoinMarketCap.
- Non sono stati implementati fallback automatico, selettore per funzione o terzo provider, esplicitamente rinviati a V2.

## 2. COME È STATO FATTO

- Tutti i consumer dipendono da `MarketDataProvider`; i provider concreti vengono istanziati soltanto nel registry.
- Il provider predefinito arriva da `Settings` tramite `market_data.provider: cmc`.
- Il selettore sviluppatore cambia provider globalmente per il processo corrente; al riavvio torna il valore configurato.
- Gli ID usati dall'app restano slug stabili, mentre `provider_id` conserva l'identificativo nativo.
- La risoluzione CMC usa prima alias, slug, ID numerici, nome esatto e simbolo univoco.
- I simboli non risolti vengono interrogati singolarmente, così un errore non annulla gli asset validi.
- CMC usa map, listings latest, quotes latest v3 e OHLCV historical v2.
- CoinGecko mantiene simple price, markets, search e OHLC dietro lo stesso contratto.
- Cache e single-flight sono applicati prima della chiamata esterna; richieste concorrenti identiche condividono una sola operazione.
- Una cache hit non incrementa richieste o crediti locali.
- Il limite CMC applicativo resta conservativo a 120 richieste/minuto per rispettare il limite documentato di `quotes/latest` v3.
- Le richieste OHLCV usano sempre `time_start` e `time_end`, finestre massime di 30 giorni e deduplicazione dei punti di confine.
- Il frontend invia al backend tutti gli ID preferiti, separatamente dalla market list visibile.
- Le risposte native obsolete non possono sovrascrivere lista, ricerca o selettore correnti.
- Mercati e Preferiti usano la stessa funzione pura di ordinamento, ma mantengono criterio, direzione e periodo in stati separati.
- Il checker registra provider, conteggio richiesto/restituito, ID mancanti e assenza di dispositivi.
- I log non includono token, header Authorization, chiavi provider o valori sensibili.

Documentazione ufficiale CMC verificata durante l'implementazione:

- https://coinmarketcap.com/api/documentation/pro-api-reference/pricing
- https://coinmarketcap.com/api/documentation/pro-api-reference/cryptocurrency
- https://coinmarketcap.com/api/documentation/pro-api-reference/agent-hub/cmc-mcp

## 3. COSA È STATO VERIFICATO

- Suite backend completa attuale: `31 passed, 1 skipped`.
- Lo skip riguarda la chiamata CMC reale quando `CMC_API_KEY` non è esportata nel processo di test.
- Smoke reale CMC eseguito separatamente nell'ambiente utente: `1 passed, 9 deselected in 3.71s`.
- Smoke reale CoinGecko passato con risposta valida nel formato normalizzato.
- Selettore CMC/CoinGecko verificato: le richieste vengono inoltrate al provider attivo.
- Normalizzazione verificata sui campi comuni dei due provider.
- Rate limiter verificato oltre soglia.
- Cache crediti verificata: una richiesta identica non consuma un secondo credito.
- Soglie budget `ok`, `warning`, `critical` ed `exhausted` verificate.
- Endpoint backend verificati per symbol, price, volume e OHLCV.
- Segmentazione OHLCV verificata su 75 giorni: tre finestre contigue, ciascuna non superiore a 30 giorni.
- Verificata l'assenza di chiamate dirette a `api.coingecko.com` fuori dall'adapter/configurazione.
- Verificata la compatibilità degli ID preferiti salvati prima dello Step 3.
- Verificato che il catalogo CMC venga letto oltre la prima pagina.
- Verificato che un simbolo invalido come `FIGR_HELOC` non blocchi gli asset validi.
- Verificato che dieci richieste provider concorrenti identiche producano una sola chiamata HTTP.
- Verifica runtime del 14 giugno 2026: CMC ha risolto `27/27` asset e restituito `27/27` prezzi senza ID mancanti.
- Nella stessa verifica il checker ha generato un alert preferito reale per `audiera` con movimento `-2,06%`.
- Verificato che preferiti e ricerca non dipendano più dalla dimensione della lista Mercati.
- Verificato con TypeScript l'ordinamento indipendente di Mercati e Preferiti.
- `ruff check backend/app backend/tests`: passato.
- `compileall backend/app backend/tests`: passato durante il gate Step 3.
- `npx tsc -b`: passato.
- JSON locale EN/IT: parsing passato.
- `git diff --check`: passato; restano solo avvisi CRLF della working copy Windows.
- `npm run lint`: non verde per errori React Hooks preesistenti in `App.tsx`, hook legacy e `SplashOverlay.tsx`; nessuna segnalazione riguarda l'ordinamento aggiunto.
- Il build Vite locale non è stato usato come gate perché può caricare configurazione locale; build APK e distribuzione sono affidate alla CI.

## 4. SCOSTAMENTI DAL PIANO

- Il piano indicava una traduzione IT → EN con inglese predefinito. Sono state aggiunte le chiavi EN/IT del dominio market data, ma la UI legacy contiene ancora numerosi testi italiani hardcoded.
- La granularità storica CMC a 5 minuti riguarda quote storiche, non OHLCV completo con volume; non vengono sintetizzati dati mancanti.
- CoinGecko è pienamente valido per monitoring, ricerca e alert, ma il suo endpoint OHLC non fornisce il volume necessario al Volume Profile 5m.
- Il cambio provider runtime non è persistito: al riavvio viene ripristinato il provider definito in `Settings`.
- È stata aggiunta osservabilità più estesa del previsto per diagnosticare problemi reali di preferiti, ricerca, rate limiting e checker.
- Sono state eseguite correzioni di retrocompatibilità non esplicitate nel piano per preservare i preferiti creati nelle release precedenti.

## 5. QUESTIONI APERTE

- Completare la conversione dei testi frontend legacy al sistema i18n prima dello Step 8, con inglese default e italiano conservato. Deve essere una sostituzione di stringhe senza riscrivere la logica dei componenti.
- Implementare nello Step 6 il feed specializzato Binance klines per il Volume Profile 5m:
  - Futures: `GET /fapi/v1/klines`
  - Spot: `GET /api/v3/klines`
- Il feed Binance del Volume Profile deve restare nel signal engine e non passare attraverso il `MarketDataProvider` generico.
- Decidere in uno step successivo se persistere il selettore runtime, mantenendo `Settings` come unico punto di caricamento.
- Risolvere il debito lint React con correzioni puntuali prima di rendere `npm run lint` un gate CI.
- Verificare che il secret GitHub Actions `VITE_API_READ_TOKEN` sia configurato prima delle prossime build APK.
- Eseguire una verifica finale su APK dell'ordinamento indipendente Preferiti/Mercati appena la relativa build è disponibile.

## 6. STATO DELIVERABLE

**Raggiunto.**

La parte funzionale e architetturale dello Step 3 è completata: astrazione multi-provider, adapter CMC/CoinGecko, selettore globale, checker notifiche, frontend normalizzato, MCP, rate limiting, cache crediti, compatibilità preferiti, ricerca e suite di integrazione sono implementati e verificati.

La revisione successiva ha accettato i punti residui come vincoli differiti che non bloccano lo Step 4: i18n frontend prima dello Step 8, feed Binance klines specializzato nello Step 6, debito lint come task separato e configurazione del secret CI `VITE_API_READ_TOKEN`.

Il limite OHLCV/Volume Profile è quindi un confine architetturale documentato e assegnato allo Step 6, non un'implementazione mancante dello Step 3.
