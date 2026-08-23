# Report — Shadow-stop: seconda variante ottimizzata in parallelo (NOTE/92)

Data: 2026-08-24 · Branch: `claude/shadow-stop-optimized-variant` · Richiesta esplicita di David

## 1. COSA È STATO FATTO

Estesa la simulazione shadow del 23/08 (NOTE/91) con una **seconda variante
della regola**, trovata da una ricerca sistematica sui punti di rientro dopo
uno stop (nota 92): David ha chiesto di calcolare, dai dati, quali sarebbero
stati i migliori rientri per arrivare a TP1 dopo uno stop. La ricerca ha
trovato una config — 3 candele di conferma invece di 1, rientro allo 0,2%
sotto l'entry invece che esattamente sull'entry — che batte la regola già
deployata su entrambi i campioni storici (V1 in-sample, V2 fuori campione),
con un intervallo di confidenza bootstrap su V2 che non contiene lo zero
(P(>0)=99%).

Le due varianti ("baseline" = la regola originale invariata, "optimized" =
quella nuova) girano ora **in parallelo sulla stessa posizione reale**, non
in sostituzione l'una dell'altra: ogni apertura perp crea due run shadow
indipendenti sugli stessi prezzi veri, così il confronto fra le due — atteso
fra 2-3 settimane — non dipende da periodi diversi di mercato.

## 2. COME È STATO FATTO

- `backend/app/agent/shadow_stop.py`: `ShadowStopConfig` esteso con
  `confirm_candles` (default 1) e `reentry_offset_pct` (default 0,0) — ai
  default riproducono ESATTAMENTE il comportamento originale, verificato con
  un test di regressione esplicito. La fase `waiting_confirm` ora conta
  candele consecutive oltre l'entry (`confirm_count`, azzerato ogni volta che
  una candela rientra prima di completare la conferma) invece di bastare una
  sola; la fase `waiting_reclaim` arma il rientro su un livello scostato
  dall'entry (`entry*(1∓offset/100)`) invece che sull'entry esatta.
- `backend/app/persistence/models/shadow_stop.py`: aggiunta la colonna
  `variant` (String(24)); il vincolo di unicità è passato da `position_id`
  da solo a `UniqueConstraint(position_id, variant)`, per permettere due
  righe per la stessa posizione.
- `backend/app/agent/shadow_stop_runner.py`: `create_shadow_stop_run` accetta
  un parametro `variant` (default `"baseline"`, retrocompatibile).
- `backend/app/agent/service.py`: all'apertura si crea sempre il run
  `"baseline"`; se `perp_shadow_stop_optimized_enabled` (default true) si crea
  anche il run `"optimized"` con `confirm_candles`/`reentry_offset_pct` letti
  da YAML. `advance_active_runs` non richiede modifiche: interroga tutti i run
  non conclusi indipendentemente dalla variante.
- Parametri nuovi, solo YAML: `perp_shadow_stop_optimized_enabled` (true),
  `perp_shadow_stop_optimized_confirm_candles` (3),
  `perp_shadow_stop_optimized_reentry_offset_pct` (0,2).

## 3. COSA È STATO VERIFICATO

- 4 test nuovi sul motore puro (`test_shadow_stop.py`): il contatore di
  conferma si azzera se una candela rientra prima di completare la sequenza;
  il rientro con offset richiede un prezzo più conveniente e non scatta se il
  ritracciamento non arriva così in basso; **test di regressione esplicito**
  che verifica come i default (confirm=1, offset=0,0) riproducano esattamente
  il comportamento di ieri.
- 1 test nuovo sull'I/O (`test_shadow_stop_runner.py`): due varianti create
  sulla STESSA posizione coesistono senza collidere sul vincolo di unicità,
  e avanzano in modo indipendente — nel caso di test, la baseline arriva a
  TP1 mentre la optimized resta ancora in attesa perché le servono più
  candele di conferma di quelle già passate.
- Suite completa su VPS: **381 passed, 2 failed, 2 skipped**. I 2 falliti
  sono gli stessi due pre-esistenti (ticket-flow support, meta-controller
  reduce) già verificati identici su `main` pulito il 23/08: non
  regressioni.

## 4. SCOSTAMENTI DAL PIANO

Una precisazione emersa scrivendo i test: il "2/3" che avevo ipotizzato a
voce per il conteggio delle candele di conferma nel caso di test non teneva
conto che una candela con il minimo sotto l'entry AZZERA il contatore, non lo
lascia fermo — corretto nel commento del test, comportamento del codice
sempre stato quello inteso.

**Bug trovato e corretto prima che avesse effetto**: la tabella
`shadow_stop_runs` NON era vuota come nel deploy del 23/08 — al momento del
deploy risultavano **2 posizioni perp reali già aperte**, con run shadow
`baseline` già in corso nelle fasi `waiting_confirm`/`waiting_reclaim`. Il
loro `state_json`, scritto dalla versione precedente di `new_run_state()`,
non conteneva le chiavi nuove (`confirm_candles`, `reentry_offset_pct`,
`confirm_count`). La lettura diretta con `st["..."]` in quelle due fasi
avrebbe sollevato `KeyError` al primo tick successivo al deploy — catturato
da `advance_active_runs` (che non propaga mai un'eccezione), quindi senza
crashare il bot, ma **quei due run sarebbero rimasti bloccati per sempre**,
persi in modo silenzioso: esattamente il tipo di errore che la regola di
rigore vieta di lasciar passare. Trovato ispezionando `state_json` delle
righe reali PRIMA del tick successivo (mancavano ~4 minuti), corretto
sostituendo le letture dirette con `st.get(..., default)` (stesso pattern
difensivo già usato nel progetto per i settings), coperto da 2 test di
regressione dedicati che riproducono esattamente la forma dei due
`state_json` reali, e ridistribuito con un secondo deploy mirato (solo
`shadow_stop.py`) prima che il tick scattasse. Verificato nei log: nessun
`shadow_stop_advance_failed` prima della correzione.

Anche la sezione "6. Stato deliverable" del piano andava corretta: avevo
scritto a David che la tabella sarebbe stata vuota, sulla base del deploy
del giorno prima — non ho ricontrollato lo stato attuale prima di scrivere
il resume. Lezione: verificare lo stato live subito prima del deploy, non
fidarsi dello stato dell'ultima verifica.

## 5. QUESTIONI APERTE

- Stesse della nota 91: la prima lettura utile del confronto richiede un
  campione di run conclusi, quindi 2-3 settimane.
- Ora ogni posizione produce DUE righe nella tabella invece di una: se in
  futuro serve un endpoint di lettura, dovrà aggregare per `position_id` e
  confrontare `variant` fra loro, non solo elencare le righe.
- Non è stata testata una terza variante intermedia (es. solo l'offset senza
  le 3 candele, o viceversa) — la grid search ne aveva prodotte 24, ho
  scelto di deployare solo l'estremo migliore trovato, non l'intera griglia:
  se David vuole isolare quale delle due modifiche pesa di più, serve una
  terza variante.

## 6. STATO DELIVERABLE

Completo. Deploy su VPS con backup freddo del vero DB di produzione
(`backend/local.db`), servizio fermato prima di ogni modifica. La tabella
`shadow_stop_runs` conteneva 2 righe reali (posizioni aperte, vedi §4):
migrazione applicata in `database.py` (ADD COLUMN `variant` con default
`'baseline'`, sostituzione dell'indice unico da `position_id` a
`(position_id, variant)`), idempotente e automatica a ogni avvio — non un
intervento manuale una tantum. Verificato dopo il riavvio: schema corretto,
le 2 righe preesistenti backfillate a `variant='baseline'` con `outcome`
ancora NULL (run in corso, intatti). File deployati, hash confrontati e
coincidenti. Il bug di §4 è stato corretto con un secondo deploy mirato
prima che causasse danno. Merge in main e push eseguiti (commit `2f216d5`
incluso).
