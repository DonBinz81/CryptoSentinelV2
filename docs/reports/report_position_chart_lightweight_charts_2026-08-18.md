# Report - Grafico della posizione con lightweight-charts

Data: 2026-08-18

---

## COSA È STATO FATTO

Il grafico della posizione nella scheda del trade — finora un SVG disegnato a
mano dentro `AgentTab.tsx` — è stato sostituito con **lightweight-charts v5.2**
di TradingView, la stessa libreria già usata dal grafico del Mercato. Il lavoro
è sul branch `claude/grafico-lightweight-charts` (APK dev **v1.0.47**, build #47).

Tre pezzi nuovi in `src/components/`:

1. **`tradeChartModel.ts`** — il modello: decide *cosa* mostrare (livelli con
   colore/tratteggio/etichetta, marker, scala, tick degli assi) separato dal
   *come* disegnarlo. Contiene la palette `LEVEL_COLORS`, organizzata per
   significato: rosso `#f23645` lo stop, ambra le soglie Smart SL, neutri
   entry e breakeven, blu il trailing, verdi i take profit, viola la candela
   di riferimento dello stop.
2. **`TradeCandleChart.tsx`** — il grafico SVG di prima, spostato in un file
   suo e riscritto sopra il modello. Non più collegato all'app, tenuto come
   ripiego: tornare indietro è cambiare una riga di import.
3. **`TradeCandleChartLW.tsx`** — la resa nuova: zoom e pan nativi sul tempo
   (scala prezzi bloccata), crosshair, prezzi dei livelli **nella scala di
   destra** colorati come il livello, sigle minute (7px) appoggiate sopra la
   linea dentro l'area candele, distanza del trailing in percentuale accanto
   alla sigla (`TRL 1.4%`), candela di riferimento dello stop **colorata di
   viola** al posto del vecchio marker, frecce di ingresso/uscita orientate
   secondo la direzione del trade.

Decisioni prese da David durante la revisione visiva: prezzi nella scala e non
sulle linee; sigle piccole e staccate dalla linea; palette professionale sul
riferimento TradingView; candela dello stop viola senza pallino; frecce senza
testo; candele attenuate prima dell'ingresso e **dopo l'uscita** (con la sola
candela viola accesa nel contesto pre-entry).

Correzioni emerse e valide per entrambi i renderer:

- le candele si spengono **dall'uscita**, non dalla fine dello snapshot salvato
  (prima restavano accese fino a 7 candele di trade già chiuso);
- il marker d'ingresso segue la direzione (freccia in giù sopra la barra sugli
  short);
- orari in **ora locale** (la libreria etichetta in UTC di suo);
- i livelli lontani dalle candele restano in vista: l'autoscala è imposta dal
  modello (`autoscaleInfoProvider` con `margins`, senza i quali la libreria
  ignora il range richiesto).

In più: banco di anteprima `dev-preview/` (temporaneo, da rimuovere prima del
merge) per guardare il grafico nel browser senza avviare l'app né leggere il
`.env`: monta solo il componente con dati sintetici costruiti *dalle candele*.

## COME È STATO FATTO

- Branch dedicato da `main` (`a51233b`), backup datato di `AgentTab.tsx` fuori
  dal repo con SHA-256 verificata, un passo per volta con consenso esplicito.
- **Estrazione conservativa**: il componente SVG è stato prima traslocato in un
  file suo (diff meccanico: identico salvo `export`), poi il calcolo è stato
  estratto nel modello **senza cambiare il disegno**: fotografia dell'SVG reso
  nel browser (hash dell'`outerHTML`, conteggio linee/rect/cerchi, testi con
  coordinate) prima e dopo — impronte **identiche** su tutti i casi di prova.
- La resa nuova consuma lo stesso modello: nessuna logica duplicata.
- Revisione iterativa con David sull'anteprima nel browser (etichette, palette,
  marker, allineamenti), con screenshot inviati a ogni passo.
- La legenda sotto il grafico in `AgentTab` ora legge i colori da
  `LEVEL_COLORS` invece di ripeterli a mano.
- Il commit dell'altra sessione (`Eligible: USDF→SUI`) finito per errore sul
  branch è stato spostato su un branch locale dedicato
  (`chat-infra/eligible-usdf`) e rimosso da questo con rebase; backup
  `backup/grafico-prima-spostamento`.

## COSA È STATO VERIFICATO

- **Equivalenza del refactor SVG**: impronte del rendering identiche
  prima/dopo su 4 casi (long completo, short minimo, prezzi micro, livelli
  fuori scala).
- **Completezza informativa della resa nuova**: su ogni caso di prova tutti i
  livelli, marker e riferimenti presenti nell'SVG sono presenti nel nuovo
  (verifica sull'elenco delle etichette rese).
- **Caso critico "livelli fuori scala"**: SL e TP2 lontani dalle candele
  restano visibili (era il difetto più probabile del cambio libreria, trovato
  e corretto in anteprima).
- **Breakeven e trailing compaiono solo quando armati**: verificato sul
  backend (`views.py`: `_breakeven_price` torna `None` finché lo stop non è a
  pareggio; `trailing_stop` solo quando valorizzato) e riprodotto nei casi di
  prova E (pre-TP1: nessuna linea BE/TRL) ed F (oltre TP2: TRL con
  percentuale).
- `npx tsc -b` (lo stesso controllo della CI) pulito; ESLint pulito.
- **Build CI**: run 32173614927 verde su `387ca0c`, APK dev v1.0.47
  pubblicata, provenienza dal branch verificata sul corpo della release.
- URL run: https://github.com/DonBinz81/CryptoSentinelV2/actions/runs/32173614927

## SCOSTAMENTI DAL PIANO

- Il piano prevedeva un solo confronto meccanico finale; la revisione visiva
  con David ha prodotto più iterazioni (palette, etichette, marker) ciascuna
  verificata sull'anteprima.
- La **prima build CI è fallita** (`fd796ab`): sei errori di tipi che il
  controllo locale non vedeva perché `npx tsc --noEmit` sul tsconfig di
  radice non compila i file dell'app (è un contenitore di riferimenti).
  Corretto il codice e il metodo: il controllo di riferimento è `tsc -b`.
- I promessi salvataggi intermedi per ogni passo non sono stati fatti durante
  le prime fasi: il lavoro è rimasto a lungo in working tree non committato,
  contro quanto concordato. Recuperato con i commit `90cf2ab` → `387ca0c`.
- Il perimetro C della nota 50 indica `frontend/**` e `mobile/**`: quelle
  cartelle non esistono, il frontend vive in `src/`.

## QUESTIONI APERTE

- **Prova sul telefono in corso** (zoom a due dita, leggibilità sigle 7px,
  resa della candela viola): l'esito di David decide eventuali ritocchi.
- Richieste di David già discusse e **fuori da questo step**: contesto di 24h
  prima dell'apertura e fino a 24h dopo la chiusura (richiede backend: tetto
  260 candele nell'enrichment, cap 50 su `post_close_candles`, fetch per
  intervallo) e selettore timeframe 15m/1h (aggregazione lato client, da
  costruire sul grafico nuovo).
- `dev-preview/` è nel branch per comodità di revisione ma va **rimosso prima
  del merge su main** (commit marcato "temporaneo").
- Il vecchio `TradeCandleChart.tsx` resta come ripiego finché la prova sul
  telefono non conferma la resa nuova; poi andrà eliminato.
- Branch locale `chat-infra/eligible-usdf` in attesa che la sessione
  infrastruttura lo riprenda (contiene `AGENTS.md` + `eligible_tokens.yaml`
  + report USDF→SUI).

## STATO DELIVERABLE

- Branch `claude/grafico-lightweight-charts` pushato, CI verde, **APK dev
  v1.0.47** pubblicata (pre-release `dev`).
- L'app monta la resa nuova; `main` non è toccato: il merge avverrà solo dopo
  l'approvazione di David sul telefono e la rimozione di `dev-preview/`.
- Backup di `AgentTab.tsx` pre-lavoro:
  `Documents/CryptoBot/backup_frontend/AgentTab.tsx.20260818_prima_grafico_lwc`.
