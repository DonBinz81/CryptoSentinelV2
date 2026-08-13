# Report fix regressione market-data frontend

## 1. COSA È STATO FATTO

- Corretta la regressione per cui la tab Preferiti poteva mostrare prezzi non aggiornati o placeholder mentre la chiamata dedicata ai preferiti era lenta.
- Ridotta la lentezza dei refresh ripetuti market-data con una cache in memoria delle identità asset già risolte dal `MarketDataRegistry`.
- Aggiunto un test di regressione backend per impedire che refresh prezzo ripetuti rieseguano la risoluzione identità CMC/CoinGecko.
- Aggiornato `docs/PROJECT_STRUCTURE.md`.

## 2. COME È STATO FATTO

- `src/hooks/useFavoriteCoinsData.ts` ora accetta un seed di coin già caricate dal mercato e aggiorna subito i preferiti corrispondenti.
- `src/App.tsx` passa alla tab Preferiti il dataset `coins` già disponibile dalla lista mercato.
- `backend/app/data/market_data/registry.py` mantiene una cache per coppia `(provider, app_id)` delle identità già risolte, evitando risoluzioni ripetute per gli stessi asset.
- `backend/tests/integration/test_market_data_providers.py` copre il caso di due refresh prezzo consecutivi sugli stessi asset.

## 3. COSA È STATO VERIFICATO

- Ispezionati i log backend disponibili: le chiamate lente erano correlate a `market_data.registry` e alla risoluzione CMC/CoinGecko degli ID, non ai loop Step 6.
- Verificato che i loop Step 6 risultano solo avviati nei log e non generano richieste market-data.
- Eseguiti test mirati market-data:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_market_data_providers.py::test_registry_caches_identity_resolution_for_repeated_price_refreshes backend/tests/integration/test_market_data_api.py::test_backend_market_data_response_shape`
  - esito: `2 passed`
- Eseguito lint backend mirato:
  - `backend\.venv\Scripts\python.exe -m ruff check backend/app/data/market_data/registry.py backend/tests/integration/test_market_data_providers.py`
  - esito: `All checks passed`
- Eseguito typecheck frontend senza build Vite:
  - `npx tsc --noEmit`
  - esito: completato senza errori

## 4. SCOSTAMENTI DAL PIANO

- Non è stata eseguita una build frontend locale perché il progetto richiede di evitare build locali quando possono caricare `.env` reale.
- Non è stato modificato il provider globale selezionato né la configurazione runtime.

## 5. QUESTIONI APERTE

- La prima risoluzione CMC dopo riavvio può ancora richiedere alcuni secondi se il processo non ha cache calda.
- Un miglioramento successivo può introdurre una cache persistente o un mapping provider-ID versionato per i token più usati, ma non è stato incluso per mantenere il fix stretto sulla regressione.

## 6. STATO DELIVERABLE

Completato e verificato con test mirati.

## 7. FOLLOW-UP 2026-06-18

### 1. COSA E STATO FATTO

- Corretta la regressione residua per cui una cache frontend da 50 elementi poteva continuare a mascherare la selezione 100/200/400/600.
- Corretta la logica Preferiti: i dati presenti nella lista mercato aggiornano subito la tab Preferiti, mentre la chiamata dedicata scarica solo gli ID non coperti dal mercato.
- La cache identita' backend viene ora popolata anche dalle liste ranked, non solo dalle chiamate esplicite con `ids`.

### 2. COME E STATO FATTO

- `useCryptoData` usa una cache separata per `currency/perPage/page` e resetta lo stato con la cache corrispondente quando cambiano i parametri.
- `useFavoriteCoinsData` calcola gli ID fuori dal seed mercato e aggiorna solo quelli, evitando refresh completi e lenti di tutti i preferiti.
- `MarketDataRegistry.get_market_list` registra le identita' app/provider dei risultati ranked.

### 3. COSA E STATO VERIFICATO

- Test mirati:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_market_data_providers.py::test_registry_caches_identity_resolution_for_repeated_price_refreshes backend/tests/integration/test_market_data_providers.py::test_registry_reuses_ranked_market_identities_for_favorite_refreshes backend/tests/integration/test_market_data_api.py::test_backend_market_data_response_shape`
  - esito: `3 passed`
- Lint backend mirato:
  - `backend\.venv\Scripts\python.exe -m ruff check backend/app/data/market_data/registry.py backend/tests/integration/test_market_data_providers.py`
  - esito: `All checks passed`
- Typecheck frontend:
  - `npx tsc --noEmit`
  - esito: nessun errore

### 4. SCOSTAMENTI DAL PIANO

- Build Vite locale non eseguita per non caricare `.env` reale.

### 5. QUESTIONI APERTE

- Il bundle installato deve essere aggiornato via CI/APK per vedere il fix sul device.

### 6. STATO DELIVERABLE

Completato e verificato con test mirati.

## 8. FOLLOW-UP 2026-06-18 - fallback cache UI

### 1. COSA E STATO FATTO

- Corretto il caso in cui, passando a un limite senza cache dedicata, la lista veniva svuotata prima della fetch e poteva mostrare il banner `Unable to load prices`.

### 2. COME E STATO FATTO

- `useCryptoData` non svuota piu' `coins` quando manca una cache per il nuovo `perPage/page/currency`.
- Se una fetch fallisce e non ci sono dati nel ref corrente, viene usata la miglior cache disponibile tra 600/400/200/100/50 o la vecchia cache legacy.
- Se ci sono dati precedenti o fallback, il banner errore viene pulito e il retry resta silenzioso.

### 3. COSA E STATO VERIFICATO

- Typecheck frontend:
  - `npx tsc --noEmit`
  - esito: nessun errore

### 4. SCOSTAMENTI DAL PIANO

- Build Vite locale non eseguita per non caricare `.env` reale.

### 5. QUESTIONI APERTE

- Il fix va distribuito in un nuovo bundle/APK per essere visibile sul device.

### 6. STATO DELIVERABLE

Completato e verificato con typecheck mirato.

## 9. FOLLOW-UP 2026-06-18 - selettore mercato oltre 50

### 1. COSA E STATO FATTO

- Stabilizzato il selettore mercato per 100/200/400/600 elementi.
- Il frontend non si affida piu' a una singola risposta `limit=100/200/400/600`.

### 2. COME E STATO FATTO

- `useCryptoData` compone le selezioni sopra 50 con pagine successive da 50 elementi.
- Per esempio, 100 usa due pagine da 50; 200 usa quattro pagine da 50.
- I risultati vengono deduplicati per `coin.id` e tagliati al limite richiesto.

### 3. COSA E STATO VERIFICATO

- Typecheck frontend:
  - `npx tsc --noEmit`
  - esito: nessun errore

### 4. SCOSTAMENTI DAL PIANO

- La strategia e' volutamente conservativa: aumenta il numero di richieste per limiti alti, ma evita che una singola risposta troncata a 50 rompa mercato e preferiti.

### 5. QUESTIONI APERTE

- Per 400/600 il caricamento puo' essere piu' lento perche' vengono richieste piu' pagine.

### 6. STATO DELIVERABLE

Completato e verificato con typecheck mirato.

## 10. FOLLOW-UP 2026-06-19 - rollback workaround frontend

### 1. COSA E STATO FATTO

- Identificata la regressione nei workaround frontend introdotti dopo `60d804d`.
- Ripristinati `useCryptoData`, `useFavoriteCoinsData` e la chiamata in `App.tsx` alla versione del commit funzionante.
- Rimosse le logiche di cache separata per limite, seed preferiti dal mercato e fetch mercato a blocchi da 50.

### 2. COME E STATO FATTO

- `useCryptoData` torna a chiamare direttamente `fetchMarkets(perPage, page, currency)`.
- `useFavoriteCoinsData` torna a fare fetch dedicato di tutti gli ID preferiti salvati.
- `App.tsx` torna a chiamare `useFavoriteCoinsData(favorites, refreshInterval, currency)` senza passare `coins` come seed.

### 3. COSA E STATO VERIFICATO

- Diff locale rispetto a `60d804d` sui tre file frontend critici:
  - `src/App.tsx`
  - `src/hooks/useCryptoData.ts`
  - `src/hooks/useFavoriteCoinsData.ts`
  - esito: nessuna differenza.
- Typecheck frontend:
  - `npx tsc --noEmit`
  - esito: nessun errore.

### 4. SCOSTAMENTI DAL PIANO

- Nessuna build Vite locale eseguita per evitare caricamento `.env` reale.

### 5. QUESTIONI APERTE

- Dopo il deploy del rollback, se il problema persiste, va verificato dai log runtime che la richiesta `limit=100/200` arrivi effettivamente al backend.

### 6. STATO DELIVERABLE

Completato e verificato con diff e typecheck mirati.
