# Report — Smart SL: conferma su candele chiuse, non su cronometro (NOTE/93)

Data: 2026-08-24 · Branch: `claude/smart-sl-closed-candle-confirmation` · Richiesta esplicita di David

## 1. COSA È STATO FATTO

David ha segnalato che gli ultimi due Smart SL (BNB, FET, 23/08 ~21:24 UTC)
sembravano scattare tardi rispetto al grafico. L'indagine (nota 93) ha
verificato che il prezzo di vendita era reale, ma il livello era stato
raggiunto ~14 minuti prima: la conferma richiesta (`perp_smart_sl_confirmation_candles`,
tradotta in un cronometro di 900 secondi) si azzerava completamente ogni
volta che il prezzo rientrava sotto il livello anche per un solo tick — il
rumore normale vicino a una soglia lo azzerava in continuazione. David ha
confermato la diagnosi e chiesto esplicitamente il fix: "vai a 3 candele
chiuse".

Il difetto era identico in **tre punti**, non uno solo: vendita L1/L2,
rebuy in modalità `delta` (mai attiva in produzione, stessa configurazione
YAML), e rebuy `above_entry` (quella davvero in uso, ed è il meccanismo che
la posizione FET aperta sta aspettando per recuperare). Corretti tutti e tre,
non solo quello segnalato — lasciarne due sul tavolo avrebbe riprodotto lo
stesso problema al primo rebuy.

## 2. COME È STATO FATTO

- `backend/app/agent/service.py`: due metodi nuovi su `AgentService`.
  - `_smart_sl_closed_candles(asset, n)`: scarica le ultime candele 5m
    dell'asset e filtra quelle REALMENTE chiuse (esclude quella in corso,
    stesso criterio già usato in `shadow_stop_runner.py`); cache 90 secondi
    per asset (stessa TTL di `_trend_shock_cache`/`_market_reversal_cache`)
    per non richiedere Binance a ogni fast tick mentre il prezzo oscilla
    vicino a un livello.
  - `_smart_sl_confirmed(pos, level_price, ms, direction_down)`: richiede che
    le ultime N candele chiuse (N = `perp_smart_sl_confirmation_candles`)
    abbiano TUTTE il close oltre il livello, nella direzione indicata.
    Fail-closed: dati insufficienti o fetch fallito → mai confermato, mai una
    vendita/rientro alla cieca.
- Sostituiti i tre blocchi `confirm_since`/`rebuy_confirm_since`/
  `rebuy_above_confirm_since` (cronometro con reset a ogni tick di rientro)
  con una chiamata a `_smart_sl_confirmed`. Rimossi i campi di stato ormai
  morti dall'inizializzazione e da ogni punto di scrittura (nessun
  riferimento residuo nel codice, verificato con grep). Rientrato di 4 spazi
  il corpo del blocco `above_entry` dopo la semplificazione (era valido ma
  con un salto di 8 spazi, non idiomatico).

## 3. COSA È STATO VERIFICATO

- 8 test nuovi (`test_smart_sl_confirmation_candles.py`), con un feed di
  candele iniettabile: conferma quando le ultime N candele chiuse sono tutte
  oltre il livello; NON conferma se anche una sola delle ultime N è rientrata
  (il pattern esatto osservato nei log reali di BNB/FET); un rientro vecchio
  non impedisce la conferma una volta che le ultime N sono pulite (differenza
  comportamentale chiave rispetto al cronometro precedente); direzione
  corretta per rientro long vs vendita short; fail-closed su dati
  insufficienti e su fetch che solleva eccezione; la candela ancora in corso
  viene esclusa; chiamate ripetute entro il TTL riusano la cache (verificato
  contando le chiamate al feed).
- Suite completa su VPS: **391 passed, 2 failed, 2 skipped** — gli stessi 2
  pre-esistenti (ticket-flow support, meta-controller reduce) verificati
  identici su `main` pulito più volte in questa sessione: non regressioni.
  Nessun test esistente sullo Smart SL (`test_perp_smart_sl_detail_preserves_original_entry`,
  `test_perp_smart_sl_rebuy_tp_adjustment_uses_actual_tp1_close_pct`) è stato
  toccato dalla modifica.
- **Verifica dal vivo in produzione**: chiamata diretta a
  `_smart_sl_confirmed` contro la posizione BNB reale ancora aperta — candele
  chiuse recuperate correttamente da Binance (703.40, 703.63, 703.97, tutte
  oltre il livello L1 703.22), risultato `confermato: True`. Non solo test
  isolati: la funzione funziona contro dati reali nel processo vero.

## 4. SCOSTAMENTI DAL PIANO

Nessuno rispetto a quanto chiesto da David. Ho ampliato lo scope da "la
vendita che hai segnalato" a "tutti e tre i punti con lo stesso difetto" —
comunicato esplicitamente prima di procedere, non deciso in silenzio.

## 5. QUESTIONI APERTE

- La posizione FET (ancora aperta) ha `smart_sl_state` con i vecchi campi
  `confirm_since`/`rebuy_confirm_since` nel JSON salvato ieri: sono ora
  ignorati dal codice (rimossa solo la LETTURA, mai aggiunta una lettura
  senza fallback su dati vecchi — nessun rischio di crash, a differenza
  dell'incidente shadow-stop di ieri). Nessuna azione necessaria.
- Non è stata testata la modalità rebuy `delta` con un caso end-to-end
  completo (solo la funzione di conferma condivisa): quella modalità non è
  mai stata attiva in produzione in questo progetto.
- Con la correzione attiva, la posizione BNB reale risultava GIÀ confermata
  al momento della verifica (le condizioni per la vendita L1 erano
  soddisfatte): il prossimo ciclo del bot probabilmente esegue quella vendita
  a breve. Comportamento atteso, non un effetto collaterale della modifica.

## 6. STATO DELIVERABLE

Completo. Deploy su VPS con backup freddo del DB di produzione prima di ogni
modifica (nessun cambio di schema: `smart_sl_state` resta una colonna TEXT,
solo il contenuto JSON cambia forma). Hash del file deployato confrontato e
coincidente con il commit. Nessun errore nei log dopo il riavvio, le due
posizioni reali (BNB, FET) intatte. Merge in main e push eseguiti.
