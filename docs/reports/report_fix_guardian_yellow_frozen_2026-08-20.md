# Report — Fix: il GIALLO del Guardiano mutava una dataclass frozen

Data: 2026-08-20 notte · Branch: `claude/fix-guardian-yellow-frozen`

## 1. COSA È STATO FATTO
Corretto un bug latente del Guardiano (NOTE/61): in stato GIALLO, la riduzione di size
delle entry perp approvate assegnava ai campi di `RiskDecision`, che è `frozen=True`
**dal commit di fork**: ogni approvazione in GIALLO avrebbe sollevato
`FrozenInstanceError` — intercettata dal try/except per-asset dello scanner — con
l'effetto reale di **bloccare** le entry invece di dimezzarle. Mai scattato in
produzione: nell'unica finestra GIALLA (19/08 11:25-17:25) nessuna entry perp è
arrivata all'approvazione.

## 2. COME È STATO FATTO
Logica estratta in `_apply_guardian_yellow()` (pura, module-level): ricostruisce la
decisione con `dataclasses.replace` invece di mutarla; sotto la size minima restituisce
il rifiuto `guardian_yellow_below_min_size` come prima.

## 3. COSA È STATO VERIFICATO
2 test nuovi sulla funzione con la VERA classe frozen (dimezzamento + campi originali
intatti; rifiuto sotto minimo). Il difetto originario è provato da lettura del codice e
dalla dimostrazione diretta (`FrozenInstanceError` su assegnazione a dataclass frozen);
i test nuovi contro il codice vecchio falliscono per assenza della funzione (prova che
il ramo non era coperto, non riproduzione del crash — dichiarato). Suite completa su
VPS: **351 passed, 2 failed** (i 2 preesistenti). Deploy per hash, merge su main.

## 4. SCOSTAMENTI DAL PIANO
Nessuno — fix nato da una rilettura del file su main durante il merge del cap.

## 5. QUESTIONI APERTE
Lezione registrata: il ramo GIALLO non aveva un test perché richiedeva stato guardiano
+ approvazione risk insieme; l'estrazione in funzione pura chiude quel buco per sempre.

## 6. STATO DELIVERABLE
Completo, testato, deployato, mergiato.
