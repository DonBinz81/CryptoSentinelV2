# Report Osservabilità Market Data

## 1. COSA È STATO FATTO

- Aggiunto logging strutturato persistente in `logs/backend.log`.
- Aggiunta rotazione giornaliera con retention configurabile.
- Aggiunto `X-Request-ID` end-to-end tra app e backend.
- Aggiunti log dettagliati per route, registry, risoluzione identità, cache e chiamate provider.
- Aggiunta diagnostica locale frontend degli ultimi 100 eventi market-data.
- Aggiunto un gate CI che impedisce di pubblicare APK senza URL backend e token Vite obbligatori.
- Resi visibili nell'app gli errori di configurazione market-data precedenti alla rete.
- Deduplicate le chiamate provider identiche già in corso per evitare code sul rate limiter.
- La ricerca CMC riutilizza il catalogo paginato da 5.000 già usato per la risoluzione dei preferiti.
- Le risposte Android obsolete non possono più sovrascrivere selettore, lista o ricerca correnti.
- I preferiti sono caricati sempre come insieme completo e non dipendono più dalla dimensione `50/100/200/400/600` del mercato.
- La tab Preferiti dispone dello stesso ordinamento Rank, 24h, 7g, Volume e Prezzo dei Mercati, con stato e direzione completamente indipendenti.
- La risoluzione CMC usa catalogo, slug, nome e simbolo univoco prima di interrogare singoli simboli; un simbolo invalido non annulla più l'intero gruppo prezzi/alert.
- I logger dei moduli sono inizializzati in modo lazy, così provider e checker notifiche usano la configurazione strutturata applicata all'avvio.

## 2. COME È STATO FATTO

- Il middleware genera o conserva il request ID e lo associa al contesto `structlog`.
- Il client invia lo stesso ID nell'header e registra status, durata ed errore senza token.
- I provider registrano endpoint, conteggi, paginazione, cache, crediti e tempi; non registrano header o valori sensibili.
- I nomi dei parametri provider sono filtrati da una whitelist; chiavi e testo completo delle eccezioni esterne non vengono serializzati.
- Il registry registra quantità richieste/restituite e gli ID non risolti per preferiti e prezzi.
- Ricerca e market list espongono conteggi distinti, permettendo di verificare selettore `50/100/200/400/600`.
- Una funzione pura condivisa ordina entrambe le liste, mentre ciascuna tab conserva autonomamente criterio, verso e periodo delle card.
- La build Android verifica la presenza delle variabili senza stamparne i valori.

## 3. COSA È STATO VERIFICATO

- Suite backend: `31 passed, 1 skipped`.
- Test anti-leak: i riepiloghi log contengono conteggi ma non valori di parametri non autorizzati.
- `ruff check backend/app backend/tests`: passato.
- `npx tsc -b`: passato.
- Verifica TypeScript dell'ordinamento indipendente Mercati/Preferiti: passata.
- `npm run lint`: non verde per errori React Hooks preesistenti e non collegati a questa modifica; nessuna segnalazione riguarda il nuovo ordinamento.
- Nessun token, header Authorization o chiave provider viene registrato.
- I log reali hanno mostrato richieste alert funzionanti ma nessuna richiesta market-data: la causa era `VITE_API_READ_TOKEN` mancante nell'APK, quindi il client si fermava prima della rete.
- Dopo la configurazione del token, i log hanno evidenziato richieste concorrenti accumulate per `40-163` secondi: cache stampede, ricerca con pagine separate da 1.000 e risposte native non annullabili.
- Test concorrente: dieci richieste provider identiche producono una sola chiamata HTTP.
- I log hanno mostrato `400 Bad Request` sui batch CMC contenenti `FIGR_HELOC`; questo errore bloccava sia il popolamento preferiti sia il price checker degli alert.
- Dopo la correzione, le richieste quote usano ID numerici e rispondono `200`; il checker registra conteggio prezzi ricevuti e ID eventualmente mancanti.
- Il checker notifiche registra esplicitamente prezzi richiesti, prezzi restituiti, ID mancanti e assenza di dispositivi registrati.
- Verifica runtime del 14 giugno 2026: CMC ha risolto `27/27` asset e restituito `27/27` prezzi senza ID mancanti.
- Nella stessa verifica il checker ha generato un alert preferito reale per `audiera` con movimento `-2,06%`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno Step successivo avviato.
- La diagnostica è stata introdotta come task correttivo trasversale allo Step 3.

## 5. QUESTIONI APERTE

- Installare e verificare sul dispositivo la nuova APK contenente il caricamento preferiti indipendente dal selettore mercato.

## 6. STATO DELIVERABLE

**Raggiunto.**

Il sistema produce evidenze persistenti e correlate e impedisce nuove release Android prive della configurazione market-data necessaria.
