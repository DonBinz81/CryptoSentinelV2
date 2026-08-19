# Report — Breach monitor (persistenza+bypass) in shadow mode

Data: 2026-08-19 sera · Branch: `claude/breach-monitor` · Riferimento: `NOTE/64`

## 1. COSA È STATO FATTO

Retrospettiva su tocchi reali di SL e livelli Smart SL (18-19/08, 1.252 episodi sui
tick) per validare l'ipotesi della nota 59 (persistenza 5 s / bypass 0,15%), poi
distribuzione in produzione di un tracker a episodi in **shadow mode**: logga cosa la
regola avrebbe fatto, senza cambiare alcun comportamento del trading.

## 2. COME È STATO FATTO

- **Retrospettiva** (script temporanei, sola lettura, cancellati a fine lavoro): copia
  del DB (mai il file di produzione) + klines 1m + aggTrades attorno ai tocchi reali.
  Segmentazione degli episodi sui tick: un episodio finisce solo al rientro reale, non
  su un buco fra trade.
- **`backend/app/agent/breach.py`**: `evaluate_breach()`, funzione pura — stato
  episodio + prezzo campionato → nuovo stato + eventi. Nessun I/O.
- **Integrazione**: `AgentService._evaluate_breach_levels()`, chiamata nel fast tick per
  ogni posizione perp aperta (livello SL dinamico + L1/L2 Smart SL se attivi e non
  ancora venduti). Stato su `perp_positions.breach_state` (nuova colonna, migrazione
  idempotente).
- **Config**: `perp_breach_mode` (`off|shadow|enforce_sl|enforce_all`, default
  `shadow`) + 4 soglie, tutte app-configurabili e nei YAML.

## 3. COSA È STATO VERIFICATO

- 10 test nuovi su `breach.py`: ciclo di vita dell'episodio, non-scatto sui flicker
  brevi, scatto a 5 s esatti, scatto singolo per episodio, bypass immediato su
  profondità, simmetria long/short, sopravvivenza a un buco di campionamento.
- Suite completa su VPS: **326 passed, 3 failed** (2 preesistenti documentati + 1 flaky
  dipendente da dati di mercato reali — **confermato con controprova**: fallisce
  identico anche su `main` non modificato), 2 skipped. Nessuna regressione attribuibile
  a questo lavoro.
- Retrospettiva: hard stop 89 episodi (regola scatta su 10/89, filtra 79, nessuno stop
  vero mancato sui 4 casi della notte rossa); Smart SL 20 coppie posizione-livello
  (persistenza 900 s conferma il netto migliore della griglia).

## 4. SCOSTAMENTI DAL PIANO

Il confronto col low/high della candela 1m per misurare la cecità residua del
campionamento a 5 s (`breach_missed_by_sampling`, previsto nel resume) **non è stato
implementato**: avrebbe richiesto chiamate Binance aggiuntive nel loop caldo per ogni
posizione aperta — rischio e complessità a sé, decisi di rimandare esplicitamente
piuttosto che bundlarlo. La domanda che doveva rispondere è già coperta offline dallo
step A. Motivazione completa in NOTE/64.

## 5. QUESTIONI APERTE

- **Controllo dello shadow**: oggi nessun meccanismo automatico legge i log o avvisa
  David. Proposta e opzioni in NOTE/64 (manuale a richiesta vs task programmato) —
  decisione di David, non presa qui.
- Soglie Smart SL (900 s / 0,30% bypass) provvisorie: il bypass non è mai stato testato
  su un episodio abbastanza profondo nel campione.
- Step C (lettura shadow, soglie definitive, `enforce_sl`) e step D (`enforce_all` al
  posto della conferma a candele dello Smart SL, valutare patch upstream a Marco)
  restano da autorizzare separatamente.

## 6. STATO DELIVERABLE

Codice completo e testato su branch `claude/breach-monitor`. **Non ancora mergiato su
main né deployato**: in attesa di push/merge esplicito, come da prassi del progetto.
