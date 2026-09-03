# Report — Chiusura manuale totale e percentuale delle posizioni Perp (dry-run)

**Data**: 2 settembre 2026
**Chat**: A — esecuzione e live (capofila), con consultazione della chat B
**Perimetro**: solo **Perp**, solo **dry-run**. Spot fuori perimetro per decisione di David.
**Stato**: ✅ **in produzione (dry-run) dal 2 settembre, 23:47 UTC** — `main` = `2e0c37a`.
Manca solo la UI, pronta sul branch della chat C.

---

## 1. COSA È STATO FATTO

Aggiunta la possibilità di intervenire manualmente su **una singola posizione Perp
aperta**, chiudendone il 25%, 50%, 75% o 100% dall'app.

- Nuovo endpoint admin-only `POST /api/v1/agent/positions/perp/{position_id}/close`,
  con header `Idempotency-Key` e corpo `{percentage, expected_size, note}`.
- La percentuale si applica **sempre alla size residua** al momento della conferma,
  mai a quella originale.
- La chiusura parziale è un **ridimensionamento**: la posizione resta aperta e tutte le
  automazioni proseguono sulla quantità rimasta.
- Motivi canonici distinti: `manual_partial_close` e `manual_full_close`. **Non** viene
  usato `manual_risk`, che appartiene al diverso comando «chiudi tutto e metti in pausa».
- Una riduzione manuale **non imposta `tp1_reached`**, non sveglia il Guardiano di regime,
  non tocca il kill switch, non mette in pausa l'agente e non modifica i livelli di
  stop/TP/trailing/profit lock.
- Ratchet e Smart SL vengono **rinormalizzati** sulla quota rimasta, così continuano a
  lavorare sul residuo reale.
- Introdotta la **serializzazione per posizione**: tutti i percorsi che chiudono o mutano
  una posizione perp passano ora sotto un unico lock.

### File aggiunti

| file | contenuto |
|---|---|
| `backend/app/agent/manual_close.py` | logica pura: preset ammessi, quantità sul residuo, regola del residuo non negoziabile, rinormalizzazione degli stati |
| `backend/app/agent/perp_position_lock.py` | registro dei lock per `position_id`, con `assert_held` e `discard` |
| `backend/app/persistence/models/manual_close.py` | tabella `manual_close_requests`: ledger di idempotenza |
| `backend/tests/unit/test_manual_close_math.py` | 47 test della logica pura (eseguibili in locale) |
| `backend/tests/unit/test_perp_position_lock.py` | 8 test del lock (eseguibili in locale) |
| `backend/tests/unit/test_manual_close_perp.py` | 33 test a livello motore (VPS) |

### File modificati

| file | modifica |
|---|---|
| `backend/app/agent/service.py` | `manual_close_perp_position()`; parametri `set_tp1_reached` e `renormalize_states` su `_close_perp_position`; `_iter_locked_perp`; `manual` in `_close_purpose`; `manual_close:` nelle note del trade perp; lock su fast tick e `close_all_and_pause` |
| `backend/app/api/routes/agent.py` | endpoint, schema di richiesta, mappa esiti → codici HTTP |
| `backend/app/persistence/models/__init__.py` | registrazione del modello nuovo |
| `backend/app/persistence/views.py` | `_close_reason` riconosce il prefisso `manual_close:` |

---

## 2. COME È STATO FATTO

### La separazione fra «parziale» e «TP1 raggiunto»

`_close_perp_position` impostava `pos.tp1_reached = True` per **ogni** chiusura parziale.
Corretto per un vero TP1, sbagliato per una riduzione umana: su quel flag si armano il
breakeven in modalità `tp1` (quella live) e il trailing post-TP1, e il motore userebbe il
TP2 come prossimo obiettivo saltando il TP1 mai raggiunto dal prezzo. È stato aggiunto il
parametro `set_tp1_reached` (default `True`, così ogni percorso esistente è invariato) e
il solo percorso manuale lo passa a `False`.

### Le due rinormalizzazioni

Entrambe **moltiplicative sullo stato corrente**, mai ricalcolate dall'originale: due
riduzioni del 50% portano la base a 0,25×, non a 0,5×.

- **Ratchet**: `base_size × (1 − q)`, con `closed_frac` e `last_step` conservati. Senza,
  il primo scalino successivo chiederebbe una quantità calcolata su una base che non
  esiste più; il clamp `min(1, want_size / pos.size)` la ridurrebbe al residuo intero,
  svuotando la posizione uno scalino in anticipo — e l'errore sarebbe invisibile, perché
  il risultato *sembra* plausibile.
- **Smart SL**: `original_size × (1 − q)`, base sia di `split_size` (vendite L1/L2) sia di
  `total_rebuy_size` (rebuy above-entry). Rinormalizzati anche
  `pre_sell_opening_fee`/`pre_sell_slippage`/`pre_sell_funding`, perché i rami di rebuy li
  riassegnano alla posizione **in valore assoluto**: senza correzione un rebuy futuro
  reintrodurrebbe i costi di una posizione più grande. Il rebuy è oggi disarmato
  (`perp_smart_sl_max_reentries = 0`), ma lo stato non deve restare incoerente per il
  giorno in cui verrà riacceso.

Restano intatti, con test che lo dimostra: stati dei livelli (`idle`/`sold`/`rebought`),
prezzi di vendita e di rebuy, contatori dei rientri, `realized_loss`, `original_entry`,
`original_tp1`/`tp2`, `protection_suspended`. Nessun livello viene armato o disarmato.

### Il coordinatore e il lock

Il fast tick (ratchet, Smart SL, uscite TP/SL) e l'endpoint HTTP girano nello stesso event
loop ma con **sessioni di database distinte**: ogni `await` è un punto in cui l'uno può
inserirsi nell'altro, leggere la stessa riga e calcolare `size − chiusa` da un valore già
vecchio. L'ultimo commit vince: due trade di chiusura scritti, una sola riduzione di size.

Soluzione: un `asyncio.Lock` per `position_id`, acquisito dal chiamante **più esterno** —
il fast tick attorno all'intera gestione di una posizione, l'endpoint attorno a
leggi-verifica-esegui-persisti, `close_all_and_pause` per posizione. Gli helper interni
(`_close_perp_position`, il ramo Smart SL) non lo acquisiscono mai: `asyncio.Lock` non è
rientrante e un annidamento bloccherebbe il loop invece di proteggerlo.
`assert_held()` logga a livello `error` se un percorso aggiunto in futuro dimentica il
contratto — non solleva, perché rifiutare una chiusura sarebbe peggio che eseguirla non
serializzata.

Per non reindentare 283 righe del loop perp è stato introdotto `_iter_locked_perp`, un
generatore asincrono che possiede il lock attorno a ogni iterazione, usato dentro
`contextlib.aclosing` perché un `break` o un'eccezione chiudano il generatore in modo
deterministico invece di lasciare il rilascio alla garbage collection.

### Idempotenza e doppio invio: due protezioni distinte

- La **chiave di idempotenza** (tabella `manual_close_requests`) copre il **replay**:
  timeout HTTP e ritentativo, client che si riconnette. La stessa chiave con lo stesso
  payload restituisce l'esito originale; con un payload diverso viene rifiutata.
- **`expected_size`** copre il **doppio tap**, che manderebbe una chiave *nuova* e che
  quindi l'idempotenza non può intercettare: la size che l'utente vedeva non corrisponde
  più e la richiesta viene respinta.

### Riconoscibilità nel database

Segnalazione della chat B, e ha scoperto un difetto reale. Il formato esistente
`auto_close:<reason>_partial` avrebbe prodotto `auto_close:manual_partial_close_partial`,
e il lettore in `views.py` rimuove `_partial` da **tutte** le occorrenze: la stringa
sarebbe collassata in `manual_close`, un motivo inesistente, rendendo indistinguibili
parziali e totali e inutile qualunque query su `manual_partial_close`.

Le chiusure manuali usano ora il prefisso `manual_close:` e conservano il motivo integro:
`notes` resta una colonna interrogabile (`LIKE 'manual_close:%'`), come serve al confronto
shadow-vs-reale previsto per metà settembre. Il percorso **spot** dello stesso costrutto
non è stato toccato.

---

## 3. COSA È STATO VERIFICATO

### In locale (`backend\.venv\Scripts\python.exe`)

**55 test verdi in 0,36 s** sui due moduli puri, più `pyflakes` pulito su tutti i file
toccati e la verifica che la tabella nuova venga creata da `Base.metadata`.

### Sulla VPS (copia isolata in `/tmp`, interprete di produzione)

```
moduli nuovi          88 passed
suite completa       495 passed, 2 failed, 2 skipped   (120 s)
golden test           3 passed  (long, short, simmetria)
ratchet/guardiano/venue  61 passed
```

I 2 falliti sono **i due preesistenti documentati**: `test_support_ticket_thread_and_admin_status_flow`
(FK malformata, NOTE/41) e `test_meta_controller_reduce` (nessuna API key nell'ambiente di
test). **Zero regressioni.**

Il **golden test invariato** è la verifica che conta: nessuno dei cinque valori economici
congelati si è mosso, quindi è stata toccata l'esecuzione e non la strategia.

### Casi coperti dai test

Quattro preset su long e short; percentuale sul residuo (50% dopo 50% lascia un quarto);
`tp1_reached` non impostato dalla riduzione manuale; TP1 vero ancora funzionante prima e
dopo una riduzione; rinormalizzazione del Ratchet con stadio conservato; **due riduzioni
consecutive seguite da uno scalino, che chiude la frazione attesa e non l'intero residuo**;
rinormalizzazione dello Smart SL con stati e prezzi intatti; Smart SL invariato in assenza
di interventi manuali; Guardiano mai chiamato; `breach_state` intatto; costi pro-rata;
livelli di protezione immutati; snapshot del grafico prodotto anche dalla chiusura totale;
i quattro rifiuti (stale, già chiusa, inesistente, venue assente); i tre casi di
idempotenza (replay, stessa chiave con payload diverso, chiave nuova su size vecchia).

### Condizioni rispettate durante i test VPS

Percorso temporaneo isolato, pacchetto `backend configs pytest.ini`, servizio **mai
fermato** (verificato `active` a fine corsa), **database di produzione mai aperto** (i test
creano SQLite propri in `tmp_path`), nessun uso di `configs/instance.yaml`, nessuna lettura
di `.env`. Temporanei rimossi.

---

## 4. SCOSTAMENTI DAL PIANO

1. **Test locali solo parziali, per impossibilità dell'ambiente.** `AGENTS.md` prescrive i
   test locali con `backend\.venv\Scripts\python.exe`. Il venv esisteva ma era vuoto; le
   dipendenze sono state installate solo dove esiste una wheel Windows ARM64. Il blocco è
   `ckzg` (dipendenza di `eth-account`, richiesta da `web3`), che non ne ha alcuna: la
   catena `agent/service.py → execution/perp_registry → wallet_selection → web3` rende
   VPS-only ogni test che tocchi il motore. Comando ed errore esatti sono nella nota 107.
   **Contromisura adottata**: la logica dove si annidano gli errori di calcolo è stata
   isolata in un modulo puro, senza dipendenze da `web3`, ed è testata in locale. Non sono
   stati compilati pacchetti nativi né modificati i pin del progetto.
2. **Toccato `backend/app/persistence/views.py`** (una riga più il commento), che appartiene
   al perimetro D. Senza, il motivo di chiusura manuale verrebbe letto in modo errato e la
   funzionalità sarebbe incoerente. Segnalato a David invece di essere fatto in silenzio.
3. **`executed_qty`/`executed_price` della venue non sono ancora l'autorità economica** per
   i percorsi *esistenti*. In dry-run coincidono con i valori richiesti; cambiare il calcolo
   delle frazioni ora avrebbe rischiato di muovere i numeri del golden test per effetto
   della quantizzazione, senza alcun beneficio finché la venue è simulata. Il percorso
   manuale è già scritto per accoglierli. Resta lavoro dell'execution layer live (NOTE/68).

---

## 5. QUESTIONI APERTE

1. **Soglie in dollari assoluti dopo una riduzione** (segnalata dalla chat B).
   `perp_breakeven_min_profit_usd` (0,15 $) e analoghe sono in USD: su un residuo del 25%
   diventano proporzionalmente quattro volte più esigenti, quindi il breakeven può non
   armarsi su posizioni molto ridotte. **Non è un difetto introdotto qui** e non è stato
   modificato nulla: è annotato perché fra qualche settimana sembrerà un guasto e qualcuno
   cercherà un bug che non esiste.
2. **Sottoconteggio deliberato del Guardiano** (accettato dalla chat B). Se una posizione
   viene chiusa a mano poco prima che lo stop scatti da solo, quel quasi-stop non viene
   contato dalla macchina VERDE/GIALLO/ROSSO. È la conseguenza voluta di non contare una
   decisione umana come segnale di mercato.
3. **Il lock protegge un solo processo.** Non copre più worker o più host, e non rende
   atomici database e venue: in dry-run la venue scrive nella stessa transazione, quindi un
   rollback annulla tutto, ma con una venue reale la chiamata di rete sta fuori dalla
   transazione. Il caso «venue confermata, database fallito» **resta fuori perimetro** e
   richiede reconciliation contro la venue (NOTE/68). Dichiarato nel codice.
4. **`perp_orders` non ha campi di telemetria**: verrà modellata su ciò che restituisce una
   venue reale, come già deciso nella nota 43.
5. **Nessuna quantizzazione per simbolo.** Oggi si usa il quanto unico `0.000001` del
   motore; `stepSize`, `minQty` e `minNotional` per simbolo appartengono all'execution
   layer live.
6. **UI non ancora realizzata**: il contratto è congelato e consegnato alla chat C.

---

## 6. STATO DELIVERABLE

| elemento | stato |
|---|---|
| Endpoint admin-only, quattro preset sulla size residua | ✅ implementato |
| Chiusura parziale come ridimensionamento, `tp1_reached` non impostato | ✅ implementato e testato |
| Ratchet e Smart SL rinormalizzati sul residuo | ✅ implementato e testato |
| Guardiano, shadow e breach non contaminati | ✅ verificato |
| Serializzazione di tutti i percorsi di chiusura Perp | ✅ implementato |
| Idempotenza e protezione dal doppio invio | ✅ implementata e testata |
| Motivi manuali interrogabili nel database | ✅ implementato |
| Suite backend senza regressioni, golden test invariato | ✅ verificato sulla VPS |
| Spot invariato | ✅ nessun file spot modificato |
| Nessun percorso live attivato | ✅ solo venue dry-run |
| UI (chat C) | ✅ implementata (`claude/manual-close-ui`, `918caac`, CI verde) — ⏳ merge e APK da fare |
| Commit, push | ✅ `main` = `2e0c37a`, 4 commit |
| **Deploy in produzione** | ✅ **2/09 23:47 UTC**, 7 file verificati per hash, 0 errori |

**Il deliverable backend è completo, verificato e in produzione in dry-run.** Resta il
merge della UI e la pubblicazione dell'APK perché la funzione sia usabile dall'app.


---

## 7. REVISIONE PRE-PUSH — un difetto introdotto da questo stesso lavoro

Richiesta di David prima di autorizzare il push. Ha prodotto una correzione reale.

**Il difetto.** Il coordinatore aggiornava il prezzo **dentro** il lock della posizione. Il
price feed ha un timeout di **10 secondi per chiamata** e quel percorso ne fa due (prezzi e
funding), più l'eventuale ripiego su un altro exchange. Con il feed lento il lock sarebbe
rimasto preso per decine di secondi e — poiché il fast tick acquisisce i lock **in
sequenza** — la gestione di ogni posizione in coda dietro quella si sarebbe fermata. Un lock
introdotto per proteggere l'integrità che finisce per sospendere la sorveglianza, in un
sistema il cui difetto più costoso è già che lo stop viene valutato solo ogni ~5 secondi
(NOTE/59, NOTE/64).

**Perché i test non l'avevano visto.** Sostituiscono `_refresh_position_prices` con una
no-op, altrimenti farebbero chiamate di rete vere. Era esattamente quella sostituzione a
nascondere il problema: la dipendenza da osservare era stata neutralizzata. Il test nuovo la
sostituisce invece con una **sonda che riporta se il lock è tenuto**, e la sua validità è
stata dimostrata sul campo — reintrodotto il difetto sulla VPS, il test **fallisce**;
ripristinata la correzione, **passa**.

**La correzione.** Il refresh avviene ora prima di acquisire il lock, come già fa
`close_all_and_pause`; scrive e committa per conto proprio, quindi la rilettura dentro il
lock vede comunque il valore fresco. Nessun cambiamento di comportamento visibile. Commit
`f871ae0`.

**Un sospetto verificato e risultato infondato.** Si era temuto che il fast tick rilasciasse
il lock *prima* di committare, lasciando una finestra per il lost update che il lock doveva
impedire. Verificato prima di segnalarlo: è falso, perché i repository committano al proprio
interno (`PerpTradeRepository.save()` chiama `session.commit()`), quindi lo stato è
persistito dentro il lock.

**Lezione trasferibile**: quando un test sostituisce una dipendenza per renderla veloce, la
domanda da porsi è *cosa smette di essere osservabile*. Qui la sostituzione nascondeva
precisamente il difetto che quel codice poteva avere.

## 8. DEPLOY — 2 settembre, 23:47 UTC

Eseguito dalla chat A su autorizzazione di David.

| passo | esito |
|---|---|
| Push | `main` = `2e0c37a` su origin, più il branch `claude/manual-close-perp` |
| Controllo file sensibili | nessun `.env`, `secrets/`, `instance.yaml`, chiave o service account |
| Backup pre-deploy | `/opt/cryptosentinelv2/backups/predeploy_manualclose_20260902_234652` |
| Estrazione | `git cat-file blob`, mai `git show` (il `core.autocrlf` restituirebbe CRLF) |
| Copia in produzione | 7 file backend, **verificati per hash uno a uno** |
| Prova di import prima del riavvio | app importabile, 2 rotte `/close` registrate |
| Riavvio | 23:47:20 UTC — servizio `active`, `health/live` 200 |
| Tabella `manual_close_requests` | creata al primo avvio |
| Errori post-riavvio | **0** (nessun traceback, nessun `no such table/column`, nessun rollback) |
| Pulizia | temporanei rimossi da `/tmp` |

Due accorgimenti aggiunti alla procedura, entrambi nati da incidenti passati:

1. **Prova di import con l'interprete di produzione prima del riavvio.** Con 4 posizioni
   aperte, scoprire un errore di import dopo il restart significherebbe un crash loop con le
   posizioni non sorvegliate — è già successo il 18/08 durante il ripristino del database.
   Costa dieci secondi.
2. **Lavoro git in un worktree separato** (`git worktree add` in directory temporanea, poi
   rimosso). La working copy è condivisa fra le chat e poche ore prima un checkout di
   un'altra sessione aveva cambiato il branch sotto i piedi a questa. Il worktree elimina
   l'interferenza: stessa repo, directory diversa.

Le posizioni aperte al momento del deploy erano **4**, lette con `csv2-db` (che interroga una
copia): il riavvio le ha lasciate non sorvegliate per circa venti secondi. È il costo noto di
ogni deploy, dichiarato in anticipo e accettato.
