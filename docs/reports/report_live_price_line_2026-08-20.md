# Grafico: il prezzo attuale su una posizione live non è più una freccia

Data: 20 agosto 2026 · Branch: `claude/live-price-line` · Commit: `bb49baf`
Perimetro: C (app Android e UI)

## COSA

David, guardando il grafico di una posizione TRX aperta: *"non voglio la freccia
verde per il prezzo attuale, voglio una riga tratteggiata bianca leggera che riporti
il prezzo a dx"*.

## COME

Il marker era una freccia (`arrowDown`, colorata verde o rossa secondo
`exitGood = exit >= entry`) piazzata sull'ultima candela, sia per le posizioni **live**
sia per i trade **chiusi**. Per il live questo è fuorviante: il prezzo "adesso" non è
un evento con un verso giusto o sbagliato — cambia a ogni tick — quindi non dovrebbe
avere un colore che suggerisce un giudizio.

Distinzione per `chart.live` (lo stesso flag già usato dalla legenda esistente per
"Ora" vs "Uscita"/"Exit", non uno nuovo):

- **live** → nessuna freccia; `series.createPriceLine()` con lo stesso meccanismo già
  usato per SL/TP1/TP2/S1/S2, prezzo su `model.exitPrice` (che per una posizione
  aperta è il prezzo corrente), `axisLabelVisible: true` per il prezzo sulla scala di
  destra
- **chiuso** → la freccia colorata resta: lì l'uscita è un evento preciso, a un prezzo
  e un istante precisi, non un riferimento che scorre

Nuovo colore `LEVEL_COLORS.now = '#9ca3af'` (grigio chiaro), deliberatamente leggero
per non competere con SL/TP che sono i livelli operativi, e distinto dal bianco pieno
della linea E (`#d1d4dc`, tratto continuo) per non confondersi con l'ingresso.

Legenda in `AgentTab.tsx` aggiornata in coerenza: "- - Ora" tratteggiata e neutra sul
live, freccia colorata "Uscita"/"Exit" solo sui trade chiusi.

## VERIFICATO

- `npx tsc -b` pulito.
- ESLint sui tre file toccati: 5 avvisi, verificati preesistenti su `main` con
  `git stash` prima di committare — un avviso nuovo (`react-hooks/exhaustive-deps`
  su `chart.live` mancante nelle dipendenze dell'effetto) è stato **trovato e corretto**
  durante lo sviluppo, non prima del commit.
- Banco di anteprima con due grafici affiancati (uno `live: true`, uno `live: false`)
  costruiti sugli stessi dati, per isolare la sola differenza che conta.
- Montaggio senza errori: verificato in una scheda **nuova e in primo piano** (una
  prima verifica in scheda di background aveva dato falsi negativi — canvas a
  dimensione 0, nessuna sigla disegnata — per via del layout azzerato di una scheda
  non visibile, non per un difetto del codice; corretto portando la scheda in primo
  piano prima di ripetere la verifica).
- Le sigle dei livelli (SL, E, TP1, TP2) si disegnano correttamente su **entrambi** i
  grafici, a conferma che `model.levels` e la pipeline `placeInlineLabels` restano
  intatte.

## SCOSTAMENTI — ⚠️ nessuna conferma visiva diretta

Ho tentato di leggere i pixel disegnati sul `<canvas>` per distinguere in modo
automatico la riga grigia dalla vecchia freccia colorata (dato che SL usa
coincidentalmente lo stesso rosso `#f23645` della vecchia freccia negativa, rendendo
ambigua qualunque ricerca per colore). Il tentativo non ha dato risultati affidabili
(canvas multipli sovrapposti nella libreria, difficili da isolare con certezza da
codice esterno) e **ho scelto di fermarmi** invece di riportare una conferma visiva
che non avevo davvero.

**Quello che è verificato**: il codice compila, non lancia eccezioni a runtime, la
logica condizionale è stata letta riga per riga ed è corretta, e usa lo stesso flag
`chart.live` già in produzione per la legenda. **Quello che NON è verificato in questa
sessione**: l'aspetto visivo reale della riga tratteggiata sul telefono. Da controllare
alla prima apertura dell'app dopo il deploy.

## DELIVERABLE

- `src/components/tradeChartModel.ts` — nuovo colore `LEVEL_COLORS.now`
- `src/components/TradeCandleChartLW.tsx` — marker condizionale, nuova `createPriceLine`
  per il live, dipendenza `chart.live` aggiunta all'effetto
- `src/components/AgentTab.tsx` — legenda aggiornata
- Branch `claude/live-price-line`, commit `bb49baf`, da `main` `d617084`
