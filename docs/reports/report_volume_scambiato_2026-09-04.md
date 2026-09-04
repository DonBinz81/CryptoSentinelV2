# Volume scambiato: caselle Vol Tot / Vol Day su app, backend e dashboard

Data: 4 settembre 2026 · Branch: `claude/volume-scambiato`
Perimetro: C (app e UI), con la parte backend di lettura necessaria a produrre il dato
Origine: travaso dalla V1 di Marco (upstream `09925eb`, `94c93c1`), analisi della chat F

> ⚠️ **Questo report è stato riscritto.** La prima versione conteneva un difetto
> bloccante e numeri sbagliati, trovati da una revisione avversariale prima del merge.
> Vedi la sezione «Il difetto che ha quasi raggiunto la produzione».

## COSA

Due caselle, `Vol Tot` e `Vol Day`, nei pannelli Spot, Perp e Global dell'app e nei
corrispondenti della dashboard web.

Il volume è il **totale scambiato**: aperture, chiusure, chiusure parziali, gambe Smart SL,
rebuy e scale-in. È la convenzione degli exchange e quella dell'upstream, così i due sistemi
restano confrontabili (decisione di David).

⚠️ Sul perp è il **nozionale**, non il capitale impegnato. Con leva 35x su un conto da 200 $
il Vol Tot reale è **370.901 $**: senza una parola che lo spieghi sembra un errore di
calcolo. Da qui la riga sotto le caselle, in Perp e in Global, sia nell'app sia nella
dashboard — non in Spot, che non ha leva e dove la spiegazione sarebbe rumore.

## COME

`sum_volume(user_id, since=...)` su `SpotTradeRepository` e `PerpTradeRepository`, che
restituisce `(totale, dal_since)` con **una sola query**: il totale con `func.sum()` e la
quota della finestra con `func.sum(case(...))` nella stessa select. L'upstream ne fa due.

`case()` e non `iif()` di SQLite: il progetto monta anche un driver Postgres, e una funzione
legata al dialetto fallirebbe il giorno del cambio.

Spot somma `amount_quote`; perp somma `size * price`. **Nessun filtro sullo `status`** — è
il punto su cui il primo tentativo ha sbagliato, vedi sotto.

`global_view` fa **due** chiamate — una per mercato — e somma, invece delle quattro
dell'upstream. Mezzanotte UTC come nelle viste per mercato.

## 🔴 Il difetto che ha quasi raggiunto la produzione

La prima versione filtrava `status == "confirmed"`, come da mandato, con questa
giustificazione nella docstring: *«oggi ogni trade nasce così, ma il default del modello è
prepared»*.

**Era falso, e mostrava circa metà del volume reale.**

Le gambe di **apertura** nascono `ExecutionStatus.PREPARED` (`agent/service.py:3514` perp,
`:3591` spot) e **nessuno le promuove mai**: l'unico `status = "confirmed"` in tutto il
backend è su un `PerpOrder` in `venues/dry_run.py:60`, tabella diversa. Solo chiusure, rebuy
e scale-in nascono `confirmed`. Il filtro non escludeva ordini non eseguiti: **scartava ogni
apertura**.

Misurato sui dati veri (`csv2-db --backup`, copia del backup, mai il DB live):

| | mostrato dal codice difettoso | reale |
|---|---:|---:|
| PERP totale | 185.530,21 | **370.901,87** |
| PERP oggi | 16.371,01 | **32.433,16** |
| SPOT totale | 5.916,31 | **11.348,91** |
| GLOBAL totale | 191.446,52 | **382.250,78** |

Una riga `prepared` **non** è un ordine mai andato a mercato: viene scritta solo dopo
`entry_execution.confirmed`, altrimenti la funzione esce con `skipped` senza scrivere nulla.
In produzione ognuna delle 252 aperture `prepared` ha la sua posizione corrispondente in
`perp_positions`, 252 su 252. `prepared` è un'etichetta rimasta indietro.

### ⚠️ Il mio riferimento «indipendente» aveva lo stesso difetto

Avevo calcolato i numeri di controllo dall'endpoint di storico, che restituisce **solo le
gambe con `pnl_usd`**, cioè solo le chiusure. Da lì l'affermazione — falsa — che «tutti gli
859 trade risultano confirmed». Le righe vere sono **1241**, di cui 349 `prepared`.

Il controllo che doveva smascherare l'errore **condivideva l'assunzione dell'errore**, e
quindi confermava. È il quarto caso in tre giorni della stessa famiglia (NOTE/107 §12.3): lo
strumento di misura che mente perché è tarato sulla stessa ipotesi del codice.

Numeri di riferimento **ricalcolati senza filtro**, sul backup `20260904T170441Z`:
PERP 370.901,87 (954 trade) · SPOT 11.348,91 (287) · GLOBAL 382.250,78.

## VERIFICATO

**Undici test** (`test_volume_scambiato.py`), eseguibili **in locale** perché toccano solo il
lato di lettura. Due gruppi: `sum_volume`, e il **cablaggio repository → viste**, che nella
prima versione era scoperto del tutto.

**Tutti visti fallire**, secondo la regola adottata (NOTE/107 §12.3):

| difetto reintrodotto | esito |
|---|---|
| filtro `status == "confirmed"` rimesso | 1 test fallisce |
| nozionale ridotto a `size` (senza prezzo) | 4 test falliscono |
| `volume_total_usd`/`volume_today_usd` invertiti in `SpotView` | 1 test fallisce |
| volume tolto dal ritorno anticipato di `global_view` | 2 test falliscono |

Gli ultimi due erano mutazioni che nella prima versione **restavano verdi**.

**Anteprima** su viewport mobile, componenti reali, tre casi: valori veri, volume davvero
zero (`$0,00`), campo assente (`$--`).

`tsc -b` pulito su app **e** dashboard. ESLint invariato rispetto alla baseline.

## SCOSTAMENTI dal mandato

**1. Tolto il filtro `status == "confirmed"`** che il mandato prescriveva — vedi sopra: non
faceva ciò che il mandato credeva.

**2. Tolti i filtri `IS NOT NULL` sull'importo.** Codice morto: `amount_quote`, `size` e
`price` sono `nullable=False`. Scoperto perché il test scritto per quel caso è fallito con
`IntegrityError`. Il test è stato riscritto per **documentare il vincolo**.

**3. Coperti DUE punti di uscita in `global_view`.** Il mandato ne indicava uno. Il secondo,
anticipato quando `portfolio is None`, avrebbe restituito zero in silenzio.

**4. Aggiunta la nota sul nozionale anche alla dashboard** (Perp e Global): mostra gli stessi
numeri dell'app, accanto a Equity ed Exposure, e senza spiegazione sono altrettanto
fraintendibili.

**5. `fmtUsdOpt` per i campi nuovi.** La CI pubblica un APK a ogni push, il backend si
deploya a mano: esiste una finestra in cui l'app nuova parla con un backend vecchio. Con
`fmtUsd` un campo assente si legge `$0,00`, indistinguibile da «non hai scambiato niente».
Ora rende `$--`. `fmtUsd` non è stato toccato: le sue chiamate esistenti si aspettano lo
zero. Di conseguenza i tipi dell'app sono **opzionali**, come già quelli della dashboard.

**6. Esportato `SpotPane`**, che non lo era, per montarlo nell'anteprima.

## 🔴 DA SAPERE — `tsc -b` non controlla la dashboard

Il mandato diceva: «senza i tipi della dashboard `tsc -b` fallisce». **Da noi non è vero.**
`tsconfig.app.json` ha `"include": ["src"]`, e la CI esegue `npm run build`, cioè quel
`tsc -b`. Oggi un errore di tipi nella dashboard **passerebbe la CI**.

Va controllata a parte: `cd dashboard && npx tsc -b` (fatto, pulito). Chiudere il buco
significa toccare il workflow: **segnalato, non risolto**, fuori dal mandato.

## NOTA DI PRESTAZIONE (non bloccante)

`sum_volume` fa una `SUM` sull'intera tabella a ogni caricamento della vista. Con le righe
attuali (954 perp + 287 spot) è irrilevante. `timestamp_utc` **non è indicizzato**: se le
righe crescessero di un ordine di grandezza servirebbe un indice, che richiederebbe una
migrazione. Segnalato, non fatto.

## DELIVERABLE

```
backend/app/persistence/repositories/trades.py   sum_volume sui due repository
backend/app/schemas/views.py                     due campi su Spot/Perp/GlobalView
backend/app/persistence/views.py                 collegamento nelle tre viste
backend/tests/unit/test_volume_scambiato.py      11 test
src/services/agentApi.ts                         tipi (opzionali) + fmtUsdOpt
src/components/AgentTab.tsx                      caselle + nota sul nozionale
dashboard/src/types.ts, dashboard/src/App.tsx    tipi, metriche e nota, Global compreso
```

Nessuna migrazione del database.

## NON FATTO

Push e deploy: **solo su richiesta esplicita di David**.
