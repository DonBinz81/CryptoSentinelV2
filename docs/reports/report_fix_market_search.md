# Report Fix Ricerca Market Data

## 1. COSA È STATO FATTO

- Corretta la ricerca coin con provider CMC.
- Rimossa la seconda risoluzione ridondante degli slug dopo il match nel catalogo CMC.
- Conservato l'ordine dei risultati trovato nel catalogo.
- Resa progressiva la ricerca CMC: pagine da 1.000 e stop alla prima pagina con corrispondenze.
- Resa effettiva la selezione dashboard `50/100/200/400/600` aggregando la market list CMC in blocchi da 200.
- Aggiornata la scheda informazioni frontend con ringraziamenti distinti a CoinGecko e CoinMarketCap.
- Aggiornato il README al backend multi-provider con CMC predefinito.

## 2. COME È STATO FATTO

- La ricerca frontend continua a usare esclusivamente `/api/v1/market-data/search`.
- Il backend delega al `MarketDataProvider` globale selezionato.
- `CMCProvider.search` usa direttamente gli ID numerici già ottenuti da `/v1/cryptocurrency/map` per interrogare `/v3/cryptocurrency/quotes/latest`.
- Il selettore dashboard continua a controllare solo la lista principale; preferiti e ricerca usano richieste indipendenti.
- Le richieste fino a 600 coin non dipendono più da una singola risposta CMC grande: il backend unisce blocchi contigui da 200.
- CoinGecko resta disponibile soltanto nel proprio adapter e nel selettore manuale previsto dallo Step 3.

## 3. COSA È STATO VERIFICATO

- Suite backend: `28 passed, 1 skipped`.
- Test ricerca CMC: query `ether`, ID CMC `1027`, risultato Ethereum con prezzo normalizzato.
- Verificato che la ricerca esegua una sola chiamata map e una sola chiamata quotes, senza seconda risoluzione.
- Test selettore: verificati 600 risultati con richieste CMC `(1,200)`, `(201,200)`, `(401,200)`.
- `ruff check backend/app backend/tests`: passato.
- `npx tsc -b`: passato.
- Nessuna chiamata API CoinGecko diretta presente in `src/` o Android.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno Step successivo avviato.
- CoinGecko non è stato rimosso: deve restare come adapter secondario selezionabile secondo lo Step 3.

## 5. QUESTIONI APERTE

- Verificare la ricerca sul dispositivo dopo il riavvio del backend con il nuovo commit.

## 6. STATO DELIVERABLE

**Raggiunto nel codice e nei test automatici.**

La ricerca usa il provider globale, CMC di default, e il frontend non contiene chiamate dirette a CoinGecko.
