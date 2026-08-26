# Report — Smart SL: L1 mai dentro il range della candela di riferimento (NOTE/97)

Data: 2026-08-26 · Branch: `claude/smart-sl-ref-gap` · Richiesta esplicita di David, resume approvato

## 1. COSA È STATO FATTO

David ha notato (screenshot PENGU) che il livello Smart SL L1 può cadere
DENTRO il range già battuto dalla candela di riferimento dello stop — un
livello di vendita piazzato dove un normale retest del wick lo raccoglie.
Lo studio preliminare (nota 97) ha quantificato: geometria presente nel 21%
delle posizioni storiche (19/91), una vendita reale sprecata così (NEAR,
−1,39$). Implementato il vincolo geometrico deciso da David: L1 deve stare
ad almeno un margine percentuale oltre il minimo/massimo della candela di
riferimento; tutto il resto (conferma a candele chiuse, S2, split, buffer,
rebuy disarmato) invariato.

## 2. COME È STATO FATTO

- `backend/app/agent/service.py` (`_process_smart_sl`): dopo il calcolo dei
  livelli a frazione, per il solo L1: long
  `L1_eff = min(L1, ref × (1 − gap))`, short speculare. `ref` è
  `pos.stop_reference_price` (già persistito per il grafico). Clamp: se
  L1_eff finisce a/oltre L2, flag `l1_skipped` e il loop dei livelli salta
  L1 per quella posizione — la sua quota resta in posizione, gestita da L2 e
  stop; mai livelli fuori ordine. Se la posizione non ha reference (stop in
  modalità ATR) la regola non si applica: fallback esplicito al
  comportamento attuale, mai un blocco per dati assenti.
- Parametro nuovo, solo YAML: `smart_sl_min_gap_from_ref_pct` (default
  **0,15**) → `perp_smart_sl_min_gap_from_ref_pct` in Settings. Il default
  è l'ordine dello sfondamento mediano osservato (0,227%) e lo stesso
  valore del bypass del breach monitor. Scelto il margine in percentuale e
  NON in tick (la richiesta originale era "15 tick"): i tick valgono da
  0,022% (BNB) a 0,81% (NEAR) del prezzo — un fattore 40× fra pair — e il
  bot non ha i tick size in tabella. David ha approvato la proposta in %.
- I livelli sono ricalcolati a ogni tick: la regola vale immediatamente
  anche per le posizioni aperte al momento del deploy.

## 3. COSA È STATO VERIFICATO

- 4 test end-to-end (`test_smart_sl_ref_gap.py`), DB reale + venue dry-run +
  feed candele iniettato, costruiti sulla geometria REALE del PENGU
  segnalato (entry 0,00946, ref 0,00933, ISL 0,0092274):
  1. a prezzo dentro il range battuto (dove il vecchio codice vendeva) L1
     non vende più;
  2. oltre il bordo+gap L1 vende normalmente;
  3. geometria degenerata (via override del gap): L1 saltato, L2 scatta
     regolarmente — il clamp non danneggia il resto della scala;
  4. posizione senza reference price: comportamento identico al vecchio.
- **Anti-tautologia eseguita davvero**: i 4 test lanciati contro il codice
  di produzione pre-modifica — i 2 che verificano il comportamento nuovo
  falliscono, i 2 di non-regressione passano. Esattamente il profilo
  atteso.
- Suite completa su VPS: **407 passed, 2 failed, 2 skipped** — gli stessi 2
  pre-esistenti di tutta la settimana, non regressioni.

## 4. SCOSTAMENTI DAL PIANO

Nessuno rispetto al resume approvato.

## 5. QUESTIONI APERTE

- Il margine 0,15% è tarato sullo sfondamento mediano storico, non
  ottimizzato con una griglia su klines (il danno storico era −1,39$: non
  c'era abbastanza segnale per un'ottimizzazione onesta). Se in futuro le
  vendite L1 su retest ricompaiono nei dati, si ritara dal YAML senza
  toccare codice.
- La regola vale solo per L1, come da decisione: S2 non è mai risultato
  dentro il range (0/91) e non è stato toccato.

## 6. STATO DELIVERABLE

Completo. Deploy su VPS (service.py, config.py, strategy_perp.yaml) con
backup freddo del DB e dei file precedenti, hash verificati, servizio
riavviato senza errori. Merge in main e push eseguiti.
