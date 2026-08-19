# Grafico: le sigle dei livelli restano dentro il riquadro

Data: 19 agosto 2026 · Branch: `claude/sigle-nel-riquadro` · Commit: `89d57ed`
Perimetro: C (app Android e UI)

## COSA

Zoomando il grafico della posizione, le sigle dei livelli (`TP2`, `TP1`, `SL`, `S1`, `S2`)
**uscivano dal riquadro** e finivano sparse nella pagina: TP2 e TP1 sopra la card del
grafico, SL più in basso dentro la scheda del trade. Segnalato da David con uno screenshot
il 19/08, su una posizione TRX.

## COME

### La causa: un commento sbagliato che ho scritto io

Nel codice c'era questa affermazione, in un commento accanto al controllo:

```
// priceToCoordinate torna null se il livello cade fuori dall'area
// disegnata: in quel caso la sigla non si mostra affatto.
```

**È falsa.** `series.priceToCoordinate()` restituisce comunque un numero per i livelli fuori
vista: negativo se il livello sta sopra l'area disegnata, maggiore dell'altezza se sta
sotto. Il `null` che il codice controllava non arrivava quasi mai.

Il difetto non era quindi una svista di battitura, ma una **convinzione documentata e mai
verificata**: il commento errato rendeva il controllo apparentemente corretto a chi
rileggeva, difetto incluso.

### Le due protezioni

**1. Il controllo vero.** Una sigla la cui posizione cadrebbe fuori dall'area non viene
disegnata:

```ts
const y = coordinate as number;
if (y - LABEL_OFFSET_PX < 0 || y > height) return null;
```

Non si perde informazione: il prezzo del livello resta leggibile nella **scala di destra**
finché la linea è in vista.

**2. La rete di sicurezza.** `overflow: hidden` sul riquadro esterno. Anche un caso non
previsto non può **fisicamente** uscire dal grafico: il difetto non può ripresentarsi nella
stessa forma.

### Una costante al posto di un numero ripetuto

Lo scostamento verticale della sigla sopra la sua linea era il letterale `13` scritto a
mano nel disegno. Ora è `LABEL_OFFSET_PX`, usato **sia** per disegnare **sia** per decidere
se la sigla esce in cima: erano due punti che dovevano restare d'accordo, e con due numeri
separati prima o poi non lo sarebbero stati.

## VERIFICATO

**Col gesto vero, non per deduzione.** Banco di anteprima con un caso costruito apposta:
livelli molto distanti fra loro (SL a 0,3240 e TP2 a 0,3500 su candele attorno a 0,3318),
così zoomando escono davvero dall'area. Sotto il grafico, un riquadro di controllo che
sarebbe stato invaso dalle sigle sconfinate.

- Trascinamento della scala dei prezzi **in entrambi i versi**, fino a comprimere la scala
  (visibile da 0,31 a 0,38) e poi a espanderla spingendo SL contro il bordo inferiore.
- Le sigle **restano attaccate alle rispettive linee** durante il gesto.
- Il riquadro di controllo sotto il grafico è **rimasto pulito** in ogni prova.
- Misura nel DOM prima del gesto: quattro sigle a 42, 84, 137 e 178 px dal bordo superiore,
  su 280 di altezza — tutte dentro.
- `npx tsc -b` (lo stesso della CI) pulito; ESLint senza errori sul file.

## SCOSTAMENTI

- La prova è stata fatta **con il mouse su desktop**, non con le dita su Android. Il
  comportamento del gesto è lo stesso codice, ma il pinch a due dita sul telefono non è
  stato provato in questa sessione.
- Durante la verifica ho scritto **due query DOM sbagliate** prima di quella giusta (un
  selettore che prendeva l'elemento sbagliato, un'espressione regolare troppo permissiva):
  entrambe davano risultati che sembravano sensati. È lo stesso schema del difetto che
  stavo correggendo, ed è il motivo per cui la prova finale è stata fatta **guardando le
  immagini**, non leggendo numeri.

## QUESTIONI APERTE

- Un livello fuori vista oggi **sparisce del tutto** (sigla e linea). Un'alternativa
  sarebbe appoggiare la sigla al bordo con un segno di "fuori scala", ma aggiunge rumore:
  da valutare solo se all'uso risultasse scomodo non sapere dove sia finito lo stop.

## DELIVERABLE

- `src/components/TradeCandleChartLW.tsx` — controllo sui limiti, `overflow: hidden`,
  `LABEL_OFFSET_PX`
- Branch `claude/sigle-nel-riquadro`, commit `89d57ed`, da `main` `78e581e`
