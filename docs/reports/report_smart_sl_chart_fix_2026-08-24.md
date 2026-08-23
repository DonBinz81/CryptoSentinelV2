# Report — Smart SL: grafico congelato + timeout realistico (NOTE/93 parte 2)

Data: 2026-08-24 · Branch: `claude/smart-sl-chart-fix` · Richiesta esplicita di David ("si procedi")

## 1. COSA È STATO FATTO

Seconda metà della segnalazione originale di David sugli ultimi due Smart SL:
il grafico "posizione (live)" in app non mostrava mai il tocco del livello
S1, nonostante lo storico riportasse correttamente la vendita a quel prezzo.
L'indagine (nota 93 parte 2) aveva trovato due cause concorrenti: (1) nessuno
scatto congelato del grafico esiste per le vendite Smart SL — la funzione
apposita non viene mai chiamata da quel percorso; (2) il grafico "live" di
riserva ha un timeout di 1,5 secondi per l'intera chiamata di rete, verificato
fallire quasi sempre sotto il carico reale del server, in silenzio (nessun
log). Entrambe corrette.

## 2. COME È STATO FATTO

- `backend/app/agent/service.py`: aggiunta la chiamata a
  `_snapshot_closed_trade()` subito dopo il salvataggio del trade di chiusura
  nel blocco di vendita Smart SL (L1/L2) — stesso trattamento delle chiusure
  normali (stop/TP/breakeven), che già la chiamavano. Non toccati i percorsi
  di rebuy (L1/L2 delta, above_entry): sono aperture, non chiusure, e il
  meccanismo di snapshot è per costruzione legato a un `close_trade_id`.
- `backend/app/api/routes/views.py`:
  - `TRADE_DETAIL_FEED_TIMEOUT_SECONDS`: 1,5s → **5s** (budget per singola
    chiamata di rete).
  - `TRADE_DETAIL_CHART_TIMEOUT_SECONDS`: 4s → **12s** (budget esterno
    complessivo, che deve coprire più tentativi in sequenza: con/senza
    `start_time`, più l'eventuale catena di fallback CEX).
  - `_build_live_chart()`: aggiunto un logger (`api.views`, mai esistito in
    questo file) e due punti di log — `live_chart_no_candles` quando il feed
    non restituisce candele, `live_chart_build_failed` (con eccezione e tipo)
    nel blocco `except` finale che prima ritornava `None` senza lasciare
    traccia.

## 3. COSA È STATO VERIFICATO

- 2 test nuovi end-to-end (`test_smart_sl_chart_snapshot.py`, DB reale +
  venue dry-run, nessuna rete): una vendita L1 confermata crea esattamente
  uno snapshot legato al `close_trade_id` giusto; se la conferma non arriva
  (candele insufficienti, fail-closed della nota 93 parte 1) non scatta né
  la vendita né lo snapshot — comportamento coerente, non un effetto
  collaterale separato.
- 5 test nuovi sul grafico live (`test_live_chart_timeout_and_logging.py`):
  i due timeout rispettano i nuovi minimi attesi; un fetch che solleva
  eccezione o restituisce zero candele produce esattamente il log atteso
  (`live_chart_build_failed` / `live_chart_no_candles`); una chiamata
  riuscita non produce alcun warning (nessun log spurio sul percorso felice).
- Suite completa su VPS: **398 passed, 2 failed, 2 skipped** — gli stessi 2
  pre-esistenti (ticket-flow support, meta-controller reduce) verificati
  identici su `main` pulito più volte in questa sessione: non regressioni.

## 4. SCOSTAMENTI DAL PIANO

Nessuno. Un errore mio nella prima stesura del test end-to-end: avevo
costruito uno stop-loss SOTTO l'entry per una posizione short (dovrebbe
stare sopra — è quello che protegge da un prezzo che sale), che faceva
uscire `_process_smart_sl` all'istante per la guardia `sl_in_loss` senza
eseguire nulla. Trovato dal test stesso (0 trade prodotti invece di 1),
corretto prima di consegnare.

## 5. QUESTIONI APERTE

- I nuovi timeout (5s / 12s) sono una stima ragionata, non misurata sul
  carico di picco del server: se anche questi risultassero insufficienti in
  futuro, ora almeno il fallimento lascia un log invece di sparire — la
  prossima volta si misura, non si ipotizza di nuovo.
- Le vendite Smart SL passate (comprese BNB e FET di ieri, se già chiuse
  completamente da allora) non hanno uno snapshot retroattivo: la correzione
  vale da ora in avanti, non recupera lo storico.

## 6. STATO DELIVERABLE

Completo. Deploy su VPS con backup freddo del DB di produzione prima di ogni
modifica (nessun cambio di schema: `TradeChartSnapshot` è una tabella già
esistente, si aggiungono solo righe). Hash dei file deployati confrontati e
coincidenti col commit. Nessun errore nei log dopo il riavvio. Merge in main
e push eseguiti.
