# Report - ExecutionResult, DryRunPerpVenue e router minimo

## COSA È STATO FATTO

- **`ExecutionResult`**: risultato comune e autorevole di un'esecuzione
  (`confirmed`, `venue`, `executed_qty`, `executed_price`, `fee`, `venue_order_id`,
  `venue_execution_id`, `tx_hash`, `status`, `reason`). Nessun campo di telemetria futura.
- **`DryRunPerpVenue`**: prima implementazione reale del contratto. Scrive davvero in
  `perp_orders` (`created` → `confirmed` nello stesso istante) e restituisce
  `ExecutionResult`. Non calcola nulla di economico.
- **`PerpVenueRouter`**: due momenti distinti — `resolve_entry_venue(market, symbol)`
  all'apertura, `resolve_position_venue(position)` per una posizione esistente, che
  **legge** la venue e non la sceglie mai di nuovo. Nessun fallback nascosto.
- **Tutto il perp transita dal contratto**: apertura, chiusure (TP1, TP2, stop, breakeven,
  ratchet, profit lock) e i tre percorsi Smart SL.

## COME È STATO FATTO

- Nuovo pacchetto `backend/app/execution/venues/` (`base.py`, `dry_run.py`) e
  `backend/app/execution/venue_router.py`. Il vecchio `perp_base.py` non è stato toccato:
  il contratto venue è nuovo e affianca i provider esistenti.
- Innesto in `service.py` in **cinque punti**, senza refactor del file:
  - `_simulate_trade`: risolve la venue d'ingresso e la scrive su trade e posizione
    (`venue=entry_venue.name` al posto della costante `"dry_run"`);
  - `_close_perp_position`: **un solo punto copre tutte le uscite perp**;
  - `_process_smart_sl`: vendita di livello, rebuy per livello, rebuy globale.
- `_close_purpose()` traduce il motivo di chiusura nello scopo persistito sull'ordine
  (`tp1`, `tp2`, `stop_loss`, `ratchet`, `close`).
- Se la venue non è disponibile o non conferma, l'operazione **non avviene**: nessuna
  mutazione della posizione, log esplicito, PnL zero.

## COSA È STATO VERIFICATO

- **Golden test invariato**, valore per valore:
  | tranche | PnL | quantità |
  |---|---|---|
  | TP1 | **50,00** | 5 |
  | ratchet 1 | **18,75** | 1,25 |
  | ratchet 2 | **21,25** | 1,25 |
  | ratchet 3 | **29,25** | 1,5 |
  | uscita finale (profit lock) | **15,00** | 1 |

  identici prima e dopo il refactor, in LONG e in SHORT.
- **Catena completa osservata nei log**: ogni chiusura è preceduta dal suo ordine con lo
  scopo corretto (`purpose=tp1 qty=5` → chiusura `take_profit_1`; `purpose=ratchet
  qty=1.25` → `ratchet_step`; e così via).
- **Suite completa**: **253 passed, 2 failed, 2 skipped** (le 2 failure sono le
  preesistenti: `test_meta_controller_reduce`, `test_support_ticket_thread_and_admin_status_flow`).
  Baseline precedente: 246 passed / 2 failed. I 7 in più sono i test nuovi del venue layer.
- **7 test nuovi**: ordine confermato scritto davvero, tutti gli scopi tracciati, router che
  risolve il dry-run, router che **rifiuta** l'apertura live senza venue, router che legge
  la venue dalla posizione, router che rifiuta posizione senza venue o con venue ignota,
  valori conservativi di `ExecutionResult`.

## SCOSTAMENTI DAL PIANO

- **Due errori miei, individuati dai test e corretti**:
  1. `ms.execution_mode` invece di `self._ms.execution_mode` in `_simulate_trade`
     (variabile inesistente in quello scope): faceva fallire l'apertura.
  2. Il golden test creava una posizione **senza `venue`**, quindi il router la rifiutava
     correttamente e non chiudeva nulla. Corretto il test, non il router.
- **11 posizioni nei test esistenti erano prive di `venue`**: allineate alla realtà
  (in produzione tutte le 11 posizioni reali hanno `venue = "dry_run"`, verificato).
  Modifiche di solo setup, nessuna asserzione toccata.
- La costante `"dry_run"` scritta su trade e posizione è stata sostituita con
  `entry_venue.name`: non era richiesto, ma senza di esso l'arrivo di una venue reale
  avrebbe richiesto di tornare a modificare quegli stessi punti.

## QUESTIONI APERTE

- ⚠️ **Rischio operativo da valutare**: una posizione perp con `venue` NULL non sarebbe
  più chiudibile dal bot (il router rifiuta, per progetto). Oggi non ce ne sono — 11/11
  valorizzate — ma una rete di sicurezza (backfill `venue='dry_run'` sulle posizioni aperte
  che ne fossero prive) costerebbe nulla. **Non implementata**: fuori dal perimetro
  autorizzato, va decisa.
- `ExecutionResult.fee` resta `None` nel dry-run: le fee continuano a essere calcolate in
  `_close_perp_position` come prima, per non alterare l'economia. Quando la venue reale
  restituirà la commissione, il campo diventerà la fonte autorevole.
- Lo **spot non è stato toccato**: continua a usare i provider esistenti. La stessa
  astrazione andrà estesa quando si affronterà lo spot.
- Nessun deploy: le modifiche sono committate ma non in produzione.

## STATO DELIVERABLE

- Blocco completo e verificato: strategia ed esecuzione sono separate, il comportamento
  economico è invariato.
- Prossimo passo (da autorizzare): adapter PancakeSwap Perp V2, previa verifica di
  prodotto, network, primitive di protezione e costi per operazione.
