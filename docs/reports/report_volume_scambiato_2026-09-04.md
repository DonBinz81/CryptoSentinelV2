# Volume scambiato: caselle Vol Tot / Vol Day su app, backend e dashboard

Data: 4 settembre 2026 · Branch: `claude/volume-scambiato`
Perimetro: C (app e UI), con la parte backend di lettura necessaria a produrre il dato
Origine: travaso dalla V1 di Marco (upstream `09925eb`, `94c93c1`), analisi della chat F

## COSA

Due caselle, `Vol Tot` e `Vol Day`, nei pannelli Spot, Perp e Global dell'app e nei
corrispondenti della dashboard web.

Il volume è il **totale scambiato**: aperture, chiusure, chiusure parziali, gambe Smart SL,
rebuy e scale-in. È la convenzione degli exchange e quella dell'upstream, così i due sistemi
restano confrontabili (decisione di David).

⚠️ Sul perp è il **nozionale**, non il capitale impegnato. Con leva 35x su un conto da 200 $
il Vol Tot reale di oggi è **185.530 $**: senza una parola che lo spieghi sembra un errore
di calcolo. Da qui la riga sotto le caselle, in Perp e in Global — non in Spot, che non ha
leva e dove la spiegazione sarebbe rumore.

## COME

`sum_volume(user_id, since=...)` su `SpotTradeRepository` e `PerpTradeRepository`, che
restituisce `(totale, dal_since)` con **una sola query**: il totale con `func.sum()` e la
quota della finestra con `func.sum(case(...))` nella stessa select. L'upstream ne fa due.

`case()` e non `iif()` di SQLite: il progetto monta anche un driver Postgres, e una funzione
legata al dialetto fallirebbe il giorno del cambio. È la stessa scelta già documentata in
questo file per `manual_reduction_by_position`.

Spot somma `amount_quote`; perp somma `size * price`. Entrambi filtrano
`status == "confirmed"`: oggi ogni trade nasce così, ma il default del modello è `prepared`
e una somma non deve raccoglierlo.

`global_view` fa **due** chiamate — una per mercato — e somma, invece delle quattro
dell'upstream. Mezzanotte UTC come nelle viste per mercato, altrimenti "oggi" vorrebbe dire
due cose diverse in due schermate.

## VERIFICATO

**Riferimento indipendente.** Prima di scrivere il codice ho calcolato il volume dai dati
veri di produzione, in Python, via API di sola lettura. Serve come termine di paragone: se
l'endpoint darà numeri diversi, uno dei due è sbagliato.

| | Vol Tot | Vol Day |
|---|---:|---:|
| Perp (nozionale) | 185.530,21 $ · 702 trade | 16.371,01 $ · 80 trade |
| Spot | 5.676,93 $ · 157 trade | 312,65 $ · 7 trade |
| Global | 191.207,13 $ | 16.683,66 $ |

Tutti gli 859 trade risultano `confirmed`: nessuno scartato.

**Nove test nuovi** (`test_volume_scambiato.py`), eseguibili **in locale** perché toccano
solo il lato di lettura e non importano `agent.service`. 17 passati insieme ai preesistenti.

**I test sono stati visti fallire**, secondo la regola adottata oggi (NOTE/107 §12.3):

| difetto reintrodotto | test che lo colgono |
|---|---|
| nozionale ridotto a `size` (senza prezzo) | 4 test falliscono |
| filtro `status == "confirmed"` rimosso | 1 test fallisce |

Ripristinato il codice, 9 passati.

**Anteprima** su viewport mobile 375×812, sui componenti reali, con i valori veri di
produzione: caselle presenti nei tre pannelli, nota sul nozionale in Perp e Global e assente
in Spot.

`tsc -b` pulito su app **e** dashboard. ESLint invariato: 5 problemi preesistenti su
`AgentTab.tsx`, 13 preesistenti su `dashboard/src/App.tsx` — verificati mettendo da parte le
modifiche e rimisurando, nessuno nuovo.

## SCOSTAMENTI dal mandato

**1. Tolti i filtri `IS NOT NULL` sull'importo.** Il mandato li chiedeva. Sono **codice
morto**: `spot_trades.amount_quote`, `perp_trades.size` e `perp_trades.price` sono tutte
`nullable=False`, quindi il filtro non può escludere nulla — e lascerebbe intendere a chi
legge che esistono righe senza importo. Scoperto perché il test scritto per quel caso è
fallito con `IntegrityError`: il database rifiuta la riga. Il test è stato riscritto per
**documentare il vincolo**, così se un giorno la colonna diventasse nullable fallirebbe lì e
ricorderebbe di rimettere la guardia. Il fallback a `Decimal("0")` resta: riguarda un caso
diverso, `SUM` su zero righe che ritorna `NULL`.

**2. Coperti DUE punti di uscita in `global_view`.** Il mandato ne indicava uno (~riga 303).
Ce n'è un secondo, anticipato, quando `portfolio is None`. Mettendo il volume solo nel primo,
in quel caso la vista avrebbe restituito zero **in silenzio**.

**3. Aggiunte le metriche anche al pannello Global della dashboard**, come da mandato —
confermo che l'upstream le mette solo in Spot e Perp e che copiarlo alla lettera avrebbe
lasciato il web senza un dato che l'app mostra.

**4. Esportato `SpotPane`** da `AgentTab.tsx`, che non lo era: serviva a montarlo
nell'anteprima. Stessa cosa già fatta per `PerpPane` e `TradeHistoryList`.

## 🔴 DA SAPERE — `tsc -b` non controlla la dashboard

Il mandato diceva: «senza i tipi della dashboard `tsc -b` fallisce». **Da noi non è vero.**

`tsconfig.app.json` ha `"include": ["src"]`: la cartella `dashboard/` non è nel build della
radice. La CI esegue `npm run build`, cioè proprio quel `tsc -b`. Quindi **oggi un errore di
tipi nella dashboard passerebbe la CI senza essere visto**.

La dashboard ha un suo `tsconfig.json` e va controllata a parte:

```bash
cd dashboard && npx tsc -b
```

Fatto per questo lavoro, pulito. Ma è un buco che vale oltre questo lavoro, e non l'ho
chiuso: aggiungere la dashboard alla CI è una modifica al workflow, fuori dal mandato.
**Segnalato, non risolto.**

## NOTA DI PRESTAZIONE (non bloccante)

`sum_volume` fa una `SUM` sull'intera tabella a ogni caricamento della vista, e la vista è
aggiornata di continuo dall'app. Con le righe attuali (702 perp + 157 spot) è irrilevante.

`timestamp_utc` **non è indicizzato**: se le righe crescessero di un ordine di grandezza
servirebbe un indice, e quello richiederebbe una migrazione. Segnalato, non fatto.

Contesto che rende la cosa meno teorica: `agent_decisions` è passata da 26 a 141 MB in
quindici giorni (NOTE/112). I trade crescono molto più lentamente, ma la stessa dinamica
esiste.

## DELIVERABLE

```
backend/app/persistence/repositories/trades.py   sum_volume sui due repository
backend/app/schemas/views.py                     due campi su Spot/Perp/GlobalView
backend/app/persistence/views.py                 collegamento nelle tre viste
backend/tests/unit/test_volume_scambiato.py      9 test nuovi
src/services/agentApi.ts                         tipi
src/components/AgentTab.tsx                      caselle + nota sul nozionale
dashboard/src/types.ts, dashboard/src/App.tsx    tipi e metriche, Global compreso
```

Nessuna migrazione del database: la funzionalità usa colonne che esistono già.

## NON FATTO

Push e deploy: **solo su richiesta esplicita di David**, come da mandato. Il lavoro è sul
branch `claude/volume-scambiato`, non pushato.
