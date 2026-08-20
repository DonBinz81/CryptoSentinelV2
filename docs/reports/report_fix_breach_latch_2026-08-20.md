# Report — Fix del latch del breach-monitor (NOTE/73)

Data: 2026-08-20 sera · Branch: `claude/fix-breach-latch` · Origine: bug trovato dalla
chat C su un caso reale (BCH, 24 `breach_rule_fired` per un solo episodio).

## 1. COSA È STATO FATTO

Chiuso il difetto per cui il breach-monitor (NOTE/64, shadow mode) risparava
`rule_fired` a ogni tick per tutta la durata dell'episodio invece di una volta sola,
inquinando lo shadow dataset da cui dipende la promozione della regola anti-spike.

## 2. COME È STATO FATTO

Due difese complementari sulla stessa causa (`evaluate_breach` mutava lo stato in
place e restituiva lo stesso riferimento; `service.py` confrontava per identità
`is not`, vedeva "nessun cambiamento" e non ripersisteva mai il latch `fired`):

- `backend/app/agent/breach.py`: mai più mutato l'input — lo stato che avanza è una
  copia (`dict(state)`), come il docstring "This module is pure" già prometteva.
- `backend/app/agent/service.py`: confronto per **valore** (`!=`) al posto
  dell'identità — regge anche a una futura regressione di purezza, e in più evita
  scritture inutili quando lo stato non cambia davvero.

## 3. COSA È STATO VERIFICATO

- Il test tautologico segnalato dalla chat C è stato riscritto (giro JSON reale fra i
  passi) e sono stati aggiunti: replay del caso BCH (21 campioni round-trip → 1 solo
  fired), test di purezza dell'input, e un test **a livello di service** sul percorso
  vero (`pos.breach_state` ORM, fired su un campione successivo al primo).
- **Controprova anti-tautologia eseguita**: i test nuovi contro il codice VECCHIO di
  produzione falliscono esattamente sui due che inchiodano il bug (purezza e percorso
  di persistenza); contro il nuovo passano 13/13. Nota: la sola versione round-trip
  suggerita inizialmente NON avrebbe colto il bug (il latch sopravvive nel valore
  restituito; si perdeva nella persistenza condizionale) — per questo esiste il test
  a livello di service.
- Suite completa su VPS: **345 passed, 2 failed** (i 2 preesistenti documentati).

## 4. SCOSTAMENTI DAL PIANO

Nessuno. Diagnosi e fix suggerito della chat C confermati; aggiunta la difesa doppia.

## 5. QUESTIONI APERTE

Gli episodi loggati PRIMA di questo fix vanno filtrati nelle analisi dello shadow
dataset: per episodio va contato un solo `rule_fired` (dedup su position_id+level+
start). I 1.252 episodi della retrospettiva (NOTE/64) non sono toccati.

## 6. STATO DELIVERABLE

Completo, testato con controprova, deployato (hash verificati).
