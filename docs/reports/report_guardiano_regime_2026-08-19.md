# Report — Guardiano di regime + Protezione capitale (Capital Preservation Mode)

Data: 2026-08-19 · Branch: `claude/guardiano-regime` · Riferimenti: `NOTE/60`, `NOTE/61`

## 1. COSA È STATO FATTO

Costruito il **Guardiano di regime**: una macchina a stati VERDE/GIALLO/ROSSO che reagisce
agli **stop-loss pieni** del bot perp su finestra mobile (default 6h), decisa dopo che
l'analisi del drawdown del 19/08 ha dimostrato che nessuna variabile di mercato misurata
distingueva le entry perdenti dalle vincenti al momento dell'apertura (NOTE/60 §6, NOTE/61 §2).

- **GIALLO** (1 stop in finestra): nuove aperture perp a size ridotta (default ×0,5).
- **ROSSO** (2 stop): nuove aperture perp bloccate (`guardian_red_capital_preservation`);
  le posizioni aperte restano gestite in **Protezione capitale**: TP1 chiude il 100%,
  vendite Smart SL L1/L2 immediate (conferma 0 candele), scalini ratchet anticipati
  (50/80/100% a 0,30/0,50/0,70 del tratto), trailing classico spento.
- **Rientro graduale**: dopo N ore senza nuovi stop (default 6) ROSSO→GIALLO, poi GIALLO→VERDE.
- **Notifica** una-per-transizione (FCM, severità critical) con spiegazione del **Brain**
  (Claude) su contesto reale — stop della finestra, PnL, regime BTC — e fallback su testo
  composto dal codice; uso API registrato in `ApiUsageRepository`.
- **Stato esposto** su `/api/v1/agent/status` (campo `guardian`) per il futuro banner app.
- Tutti i parametri (guardian e profilo difensivo) configurabili dall'app e con default
  nei YAML (`configs/strategy_perp.yaml`).

## 2. COME È STATO FATTO

- `backend/app/agent/guardian.py` (nuovo): stato in memoria, persistito in `RuntimeState`
  (chiave `perp_guardian_state`) a ogni variazione → sopravvive ai restart. Escalation
  sincrona su `record_stop()` (hook in `_close_perp_position`, solo `reason=stop_loss`
  e chiusura non parziale); de-escalation e rete di sicurezza in `evaluate()` chiamata
  dallo `slow_tick` (300 s). La rete di sicurezza escalation considera solo stop più
  recenti dell'ultimo cambio di stato: senza questo vincolo, con finestra > rientro la
  de-escalation verrebbe ribaltata al tick successivo (coperto da test dedicato).
- **Protezione capitale come resolver, non come scrittura**: `_CapitalPreservationView`
  (service.py) intercetta in lettura 4 chiavi (`perp_tp1_close_pct`,
  `perp_smart_sl_confirmation_candles`, `perp_profit_lock_steps`, `perp_trailing_enabled`)
  e restituisce i `perp_defense_*`; ogni altro attributo passa invariato. I settings
  salvati dell'utente non vengono mai modificati → nessun ripristino, nessun rischio di
  sovrascrittura. Attivata nei tre punti di lettura della gestione: `_check_sl_tp`
  (binding `ms`), `_close_perp_position` (frazione TP1), `_process_smart_sl` (riceve `ms`
  dal chiamante).
- GIALLO: fattore applicato in `_handle_signal` dopo il Risk Manager (così Brain ed
  esecuzione vedono la size reale); se la size scalata scende sotto `min_trade_size_usd`
  il trade è rifiutato con `guardian_yellow_below_min_size`.
- ROSSO: gate in `evaluate_perp` dopo i filtri di mercato, con log `perp_entry_rejected`.
- `ClaudeMetaController.explain()`: chiamata breve (max 300 token), best-effort, non
  solleva mai; `AgentNotifier.notify_guardian_state()`: un push per transizione, rispetta
  la preferenza `risk_alerts`.

## 3. COSA È STATO VERIFICATO

- Suite completa sulla VPS (interprete di produzione, copia isolata in `/tmp`):
  **316 passed, 2 failed, 2 skipped** — i 2 rossi sono i preesistenti documentati
  (`test_meta_controller_reduce`, `test_support_ticket_thread_and_admin_status_flow`).
  Baseline precedente: 299 passed / 2 failed → +17 test nuovi, tutti verdi.
- **Golden test del ciclo economico** (`test_position_lifecycle_golden`): passa —
  comportamento economico invariato con Guardiano in VERDE.
- Test nuovi (`backend/tests/unit/test_guardian.py`, 17): transizioni, finestra mobile,
  stop fuori finestra, de-escalation a gradini, anti-rimbalzo con finestra > rientro,
  ri-escalation su stop nuovo dopo il rientro, toggle disabilitazione (pulisce anche un
  ROSSO stantio), view di Protezione capitale (sostituzione, passthrough, nessuna
  mutazione), validazioni schema (red ≥ yellow, scalini difensivi crescenti).
- Nota metodologica: il primo run della suite mostrava 66 falsi rossi perché il tar di
  test non includeva `pytest.ini` (asyncio_mode=auto); reimpacchettato, rientrati.

## 4. SCOSTAMENTI DAL PIANO

- **Trigger PnL opzionale** (`perp_guardian_pnl_red_pct`, previsto "0=off" nel resume):
  NON spedito — sarebbe stata configurazione esposta senza implementazione. Si aggiunge
  quando verrà implementato il calcolo del PnL su finestra mobile.
- **`perp_defense_trailing_pct`**: rimosso per lo stesso principio — il trailing classico
  perp usa `trailing_mode` + floor ATR, non una percentuale; sarebbe stato un parametro
  morto. Resta `perp_defense_trailing_enabled`.
- Nessun altro scostamento: perimetro file come da resume (agent/** + notifier + schema
  + route + YAML).

## 5. QUESTIONI APERTE

- **UI (perimetro C)**: banner di stato con spiegazione e comandi rapidi (mockup
  consegnato a David, requisiti in NOTE/61 §6-bis); il backend espone già tutto il
  necessario in `/agent/status`.
- Le **soglie di default sono dichiaratamente provvisorie** (replay su un solo episodio
  rosso, NOTE/61 §7): da rivalutare col campione delle giornate etichettate (NOTE/53).
- Se David cambia gli scalini difensivi mentre una posizione è oltre il TP1 in ROSSO,
  il `closed_frac` cumulativo può superare la quota dello scalino corrente: il ratchet
  semplicemente non chiude nulla finché il progresso non lo raggiunge (monotono, sicuro).
- Il **cap di rischio sul margine fisso** (NOTE/60 §8 punto 1) resta da fare come
  intervento separato, già motivato ma non ancora autorizzato come resume.
- Throttle della notifica drawdown (approvato a parte): prossimo intervento, piccolo.

## 6. STATO DELIVERABLE

- Codice: **completo e testato** su branch `claude/guardiano-regime`.
- Deploy in produzione: eseguito il 2026-08-19 col protocollo standard (backup,
  `git cat-file blob`, verifica hash, restart) — esito e verifiche nel presente report
  aggiornato post-deploy e in NOTE/61.
- Documentazione: `docs/PROJECT_STRUCTURE.md` aggiornato (voce `agent/guardian.py`),
  NOTE/60-61 in archivio.
