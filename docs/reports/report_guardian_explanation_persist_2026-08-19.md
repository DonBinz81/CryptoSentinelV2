# Report — Persistenza della spiegazione del Guardiano

Data: 2026-08-19 sera · Branch: `main` (diretto, piccolo intervento su lavoro appena
mergiato) · Origine: richiesta della chat C (app/UI) durante l'implementazione del banner

## 1. COSA È STATO FATTO

`guardian.state` (`/api/v1/agent/status`) espone ora **due campi in più**:

```
guardian.explanation    string | null   testo del Brain sull'ULTIMA transizione
guardian.explained_at   string | null   timestamp ISO di quando è stato generato
```

Prima, il testo del Brain (`brain.explain()` in `_notify_guardian_change`) veniva usato
solo per comporre il corpo della push e poi perso: se l'utente apriva l'app dopo che la
notifica era già scomparsa dalla tendina, il banner poteva mostrare lo stato ma non il
perché — proprio l'informazione richiesta dal requisito "stato + spiegazione" (NOTE/61).

## 2. COME È STATO FATTO

- `GuardianChange` ha ora il campo `changed_at` (il momento esatto della transizione).
- `RegimeGuardian._set_state()` **azzera esplicitamente** `explanation`/`explained_at` ad
  ogni transizione, prima ancora che il Brain risponda: un banner non può mai mostrare il
  testo dello stato precedente mentre aspetta quello nuovo.
- Nuovo metodo `record_explanation(text, at, for_change_at)`: scrive solo se
  `for_change_at` combacia ancora con la transizione corrente. Copre il caso (il Brain è
  una chiamata HTTP asincrona) in cui una transizione più recente supera quella per cui
  la spiegazione era stata richiesta: il testo vecchio viene scartato, non attaccato allo
  stato sbagliato.
- `service.py`: dopo che `brain.explain()` restituisce un testo, viene passato a
  `record_explanation()` — persistito in `RuntimeState` accanto allo stato del guardiano,
  quindi sopravvive ai restart come il resto.
- Se `brain.explain()` fallisce, `record_explanation` non viene mai chiamato: il campo
  resta `null`, mai stringa vuota (richiesto esplicitamente dalla chat C per distinguere
  "non disponibile" da "vuoto" nel banner).

## 3. COSA È STATO VERIFICATO

Suite completa su VPS: **322 passed, 2 failed** (i 2 preesistenti), 2 skipped — baseline
prima di questo intervento era 318/2, **+4 test nuovi**, tutti verdi: spiegazione
attaccata alla propria transizione, nuova transizione la azzera immediatamente (anche
prima che il Brain risponda), spiegazione di una transizione superata viene scartata,
`explain()` fallito lascia il campo `null`.

Deploy verificato per hash su 2 file (`guardian.py`, `service.py`). Confermato dal vivo
sull'endpoint `/api/v1/agent/status` in produzione: stato `yellow` con `explanation`
valorizzata dopo il redeploy.

## 4. SCOSTAMENTI DAL PIANO

Nessuno: intervento chirurgico, esattamente lo scope richiesto dalla chat C.

## 5. QUESTIONI APERTE

Nessuna nuova. Resta il timestamp `explained_at` a disposizione della chat C per il
controllo di coerenza col `changed_at` che avevano già previsto lato client (qui garantito
anche lato server dalla guardia `for_change_at`, quindi è una doppia sicurezza).

## 6. STATO DELIVERABLE

Completo, testato, deployato.
