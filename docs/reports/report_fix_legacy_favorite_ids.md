# Report Fix Compatibilità ID Preferiti

## 1. COSA È STATO FATTO

- Corretta la regressione che mostrava solo parte dei preferiti dopo il passaggio da release `1.0.35` a CMC.
- Mantenuti invariati i preferiti salvati nel dispositivo.
- Aggiunto un catalogo di alias tra ID storici CoinGecko e slug CMC.
- Reso l'ID storico dell'app l'identità restituita anche quando il provider attivo è CMC.
- Aggiunta paginazione completa del catalogo CMC oltre le prime 5.000 coin.
- Aggiunta riconciliazione dinamica degli ID storici non presenti nel catalogo alias statico.
- Corretta la sincronizzazione frontend/native/backend affinché invii tutti gli ID salvati, non solo quelli già risolti e visibili.
- Impedita la scomparsa visiva dei preferiti durante richieste lente: la scheda viene costruita sempre dai 14 ID persistiti e usa righe temporanee fino al caricamento dei dati.
- Esteso da 15 a 60 secondi il timeout di lettura HTTP Android e aggiunto retry ogni 5 secondi per il recupero mirato.
- Resa non bloccante la riconciliazione identità: un errore o rate limit CoinGecko non elimina più gli asset già risolti da CMC.
- Estesa a 24 ore la cache delle identità storiche CoinGecko.
- Resa resiliente la paginazione del catalogo CMC: un errore su una pagina successiva conserva gli asset già caricati.
- Aggiunta risoluzione CMC per simbolo degli asset non presenti nelle pagine map disponibili.
- Gli ID numerici CMC già risolti vengono inviati direttamente a `quotes/latest`, evitando una seconda scansione del catalogo.
- Per i preferiti storici, il registry acquisisce prima nome/simbolo dall'adapter identità e CMC risolve direttamente tramite `quotes/latest`, senza dipendere dalla lista dashboard o dal selettore 50/100/200/400/600.
- Aggiunti test su recupero mirato e lista mercato.

## 2. COME È STATO FATTO

- La release precedente persisteva ID CoinGecko come `binancecoin`, `ripple` e `avalanche-2`.
- CMC restituisce per le stesse coin gli slug `bnb`, `xrp` e `avalanche`.
- L'adapter traduce gli ID solo al confine della richiesta CMC e ripristina l'ID applicativo nella risposta normalizzata.
- Per gli ID ancora sconosciuti, il registry richiede al solo adapter CoinGecko nome e simbolo, quindi li associa al catalogo CMC con corrispondenza esatta nome+simbolo o simbolo univoco.
- CoinGecko non viene usato come fallback dei prezzi: quotazioni, market list e OHLCV continuano a provenire esclusivamente dal provider globale selezionato.
- Il frontend costruisce il payload di sincronizzazione partendo dal `Set` completo dei preferiti; gli eventuali metadati non ancora risolti non causano più la perdita dell'ID nel backend o nel worker nativo.
- Il checker backend ha confermato prezzi CMC presenti per tutti i 14 ID reali; il problema residuo era quindi nella rappresentazione frontend quando la richiesta mirata non terminava entro il timeout nativo.
- Le righe temporanee mantengono l'ID e lo stato preferito; vengono sostituite dai dati normalizzati senza modificare il `localStorage`.
- Il registry restituisce i risultati CMC parziali già disponibili anche quando il solo catalogo identità secondario fallisce; CoinGecko non viene usato come fallback dei prezzi.
- Per gli asset a bassa capitalizzazione o oltre la pagina CMC disponibile, CoinGecko fornisce soltanto nome/simbolo; prezzo, percentuale e URL icona sono sempre costruiti dalla risposta CMC.
- Nessun preferito viene cancellato, migrato o sostituito nel `localStorage`.
- L'endpoint CMC map viene interrogato a blocchi da 5.000 fino all'ultima pagina e ogni pagina resta in cache.

## 3. COSA È STATO VERIFICATO

- Suite backend: `28 passed, 1 skipped`.
- Test multi-ID: tre preferiti legacy con slug CMC divergenti vengono tutti restituiti.
- Test lista mercato: BNB da CMC viene normalizzato con ID applicativo `binancecoin`.
- Test catalogo: verificato recupero di una coin nella seconda pagina CMC (`start=5001`).
- Test riconciliazione: un ID CoinGecko storico con slug CMC differente viene associato per nome/simbolo e quotato da CMC mantenendo l'ID originale.
- Test registry: verificato che il recupero identità non provochi fallback del prezzo verso CoinGecko.
- `python -m compileall -q backend/app`: passato.
- `npx tsc -b`: passato.
- `npm run lint`: resta non verde per errori React preesistenti; nessun nuovo errore TypeScript.
- Verifica dati runtime: configurazione backend con 14 preferiti e stato prezzi CMC valorizzato per tutti e 14.
- Test resilienza: verificato che un errore del catalogo identità non trasformi una risposta CMC valida in una lista vuota.
- Test paginazione: verificato che una seconda pagina CMC fallita non cancelli i primi 5.000 asset.
- Test simbolo: verificata la risoluzione di `midnight-3` tramite `NIGHT`.
- Test ID nativo: verificato recupero diretto di prezzo, percentuale e icona tramite ID numerico CMC senza nuova chiamata map.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno Step successivo avviato.
- È stata corretta una lacuna del formato normalizzato Step 3: lo slug provider non può essere usato direttamente come identità persistente.

## 5. QUESTIONI APERTE

- Verificare sul dispositivo la lista completa dopo una nuova build APK.

## 6. STATO DELIVERABLE

**Raggiunto nel codice e nei test automatici.**

La correzione copre anche ID non censiti staticamente e conserva tutti i preferiti durante la sincronizzazione. La verifica finale richiede l'installazione della nuova APK mantenendo i dati dell'app esistenti.
