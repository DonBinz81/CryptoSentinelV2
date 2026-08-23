# Report — Shadow mode: regola stop-stretto + reclaim confermato (NOTE/91)

Data: 2026-08-23 · Branch: `claude/shadow-stop-david-rule` · Richiesta esplicita di David

## 1. COSA È STATO FATTO

Implementata una simulazione live, in shadow mode, della regola d'ingresso
proposta da David dopo la notte di sweep del 22-23/08: stop stretto (0,1%
sotto il minimo/massimo della candela che ha generato il segnale) invece dello
stop strutturale; se colpito, si attende una candela 5m INTERA oltre l'entry
originale (conferma), poi si arma un rientro virtuale esattamente sull'entry;
stessi TP1/TP2, fino a 1 rientro, orizzonte 24h.

La regola è stata validata su 198 trade storici reali (141 V1 di Marco fuori
campione + 57 V2) PRIMA di scrivere questo codice: +11,3 punti percentuali sul
totale a costi maker, bootstrap con segno concorde su entrambi i campioni
(dettaglio nota 91 parti 2-3). Non è ancora una conclusione definitiva — per
questo va in shadow, non in produzione: il bot continua a operare esattamente
come prima, e in parallelo logga cosa avrebbe fatto la regola su ogni
posizione reale, senza mai toccare un ordine.

## 2. COME È STATO FATTO

- `backend/app/agent/shadow_stop.py`: motore puro (`advance()`, `new_run_state()`),
  una macchina a stati che avanza di una candela 5m chiusa per chiamata.
  Fasi: `awaiting_signal_candle → in → waiting_confirm → waiting_reclaim → in
  (rientro) → done`. Esiti: `tp1`, `final_stop`, `missed_train` (TP1 raggiunto
  senza ritracciamento all'entry), `horizon`, `invalid_geometry` (guardia per
  il caso in cui l'allineamento a 5m in un sistema live prenda la candela
  sbagliata). Mai muta lo state ricevuto — stesso motivo di purezza di
  `breach.py` (NOTE/73: una mutazione in-place lì aveva perso silenziosamente
  lo stato di un intero episodio).
- `backend/app/agent/shadow_stop_runner.py`: lato I/O. `create_shadow_stop_run()`
  crea la riga all'apertura (fire-and-forget, sessione propria, non solleva
  mai eccezioni — stesso contratto di `capture_entry_telemetry`).
  `advance_active_runs()` interroga i run non ancora conclusi, scarica le
  candele mancanti (`price_feed.fetch`, market="futures"), le passa una a una
  al motore puro, persiste stato ed eventi in JSON. Non solleva mai eccezioni:
  un fetch fallito lascia il run intatto al giro successivo.
- `backend/app/persistence/models/shadow_stop.py`: tabella nuova
  `shadow_stop_runs` (una riga per posizione; `create_all` la crea, nessun
  ALTER necessario). Stato ed eventi in JSON per essere autosufficiente e
  ispezionabile senza altre tabelle; `outcome`/`pnl_virtual_pct` denormalizzati
  per letture rapide.
- Aggancio in apertura: `agent/service.py`, `_handle_signal`, subito dopo il
  blocco della telemetria d'ingresso — stesso punto, stesso pattern
  fire-and-forget con `asyncio.create_task`.
- Aggancio periodico: `slow_tick`, subito dopo lo snapshot di telemetria
  posizioni aperte. **Continua a far avanzare un run anche dopo che la
  posizione reale è chiusa** — è il punto centrale: il confronto che serve è
  fra l'esito reale e quello simulato sugli stessi prezzi, non solo mentre la
  posizione vera è aperta.
- Parametri: solo YAML (`configs/strategy_perp.yaml` + `core/config.py`),
  nessuna esposizione app — `perp_shadow_stop_enabled` (true),
  `perp_shadow_stop_buffer_pct` (0,1), `perp_shadow_stop_max_reentries` (1):
  la configurazione migliore trovata nella validazione.

## 3. COSA È STATO VERIFICATO

- 13 test sul motore puro (`test_shadow_stop.py`): candela del segnale fissa
  lo stop senza valutarlo; geometria invalida quando il minimo della candela
  di segnale finisce sopra l'entry (guardia per un disallineamento
  candela-vera-entry in produzione); stop senza rientri disponibili → esito
  finale; il percorso completo segnalato da David (sweep → conferma → rientro
  → TP1); treno perso (TP1 raggiunto senza ritracciare); doppio stop che
  esaurisce i rientri nella stessa candela del rientro; orizzonte 24h che
  marca a mercato una posizione ancora aperta; **immutabilità dello stato**
  (stesso contratto anti-regressione di `breach.py`); lato short speculare.
- 5 test sull'I/O (`test_shadow_stop_runner.py`): creazione del run con lo
  stato iniziale atteso; avanzamento corretto su più tick successivi (una
  candela non ancora chiusa non viene processata in anticipo); un run concluso
  esce dalla query e non viene più ri-processato (verificato contando le
  chiamate al feed candele); un fetch che solleva un'eccezione non tocca il
  run e non si propaga.
- Anti-tautologia: entrambi i moduli sono nuovi — su `main` i test falliscono
  con `ImportError` prima ancora di eseguire un assert. Non serve una prova
  aggiuntiva del tipo "il vecchio codice fallisce": il vecchio codice non ha
  questo percorso.
- Suite completa su VPS: **377 passed, 2 failed, 2 skipped**. I 2 falliti
  (`test_support_api` ticket-flow, `test_meta_controller_reduce`) falliscono
  identici su `main` pulito (verificato con `git archive main` nella stessa
  sessione VPS): pre-esistenti, non regressioni di questo lavoro.

## 4. SCOSTAMENTI DAL PIANO

Nessuno rispetto al resume approvato da David. Un dettaglio tecnico emerso in
fase di test e non previsto nel resume: SQLite restituisce datetime *naive*
anche per colonne dichiarate `timezone=True` — bug latente scoperto dai test,
non dal codice di produzione. Corretto applicando lo stesso pattern già
presente altrove nel progetto (`_ensure_utc`, `service.py:105`) al modulo I/O.

## 5. QUESTIONI APERTE

- Il confronto vero/simulato richiede che passi del tempo: la prima lettura
  utile è fra 2-3 settimane, quando ci sarà un campione di run conclusi.
- Nessun endpoint API espone ancora i run per la lettura da app o script di
  analisi — oggi si leggono via query diretta (SELECT sulla tabella) o via
  backup. Se David vuole un modo più comodo di consultarli prima della
  scadenza delle 2-3 settimane, va aggiunto (piccola estensione, fuori scope
  di questo resume).
- La regola resta non validata su costi reali di esecuzione (slippage Aster):
  la simulazione shadow logga solo il PnL di prezzo, come da nota 91 §5.

## 6. STATO DELIVERABLE

Completo. Deploy su VPS con backup freddo del DB (tabella nuova), servizio
riavviato, hash verificati. Nessun reset o azione manuale necessaria: il
sistema comincia ad aprire run automaticamente dalla prossima posizione perp
reale. Merge in main e push eseguiti.
