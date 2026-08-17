# Report - Blocchi richiudibili nel setup agente (Step B)

Data: 2026-08-17
Branch: `feature/setup-spot-perp`

---

## COSA È STATO FATTO

Resi richiudibili i due blocchi piu' lunghi e di uso raro della scheda Perp, che
era diventata la piu' pesante da scorrere:

- **Parametri Smart Stop Loss** (20 campi)
- **Soglie del filtro shock BTC** (4 campi)

Partono chiusi. Gli interruttori che li attivano restano invece sempre visibili:
si nasconde la configurazione di dettaglio, non il comando.

## COME È STATO FATTO

Nuovo componente `Collapsible` (stato locale, ~20 righe): intestazione cliccabile
con il titolo, un contatore dei parametri contenuti e una freccia che ruota. Il
contenuto vive dentro i condizionali gia' esistenti, quindi il blocco compare solo
se la funzione e' accesa e, in quel caso, resta comunque ripiegato.

Scelta deliberata: **non** e' stata resa richiudibile ogni sezione. Rischio e
Strategia si toccano spesso e restano aperte — la modalita' ibrida concordata con
l'utente.

## COSA È STATO VERIFICATO

| verifica | esito |
|---|---|
| `npx tsc --noEmit` | pulito |
| Controlli renderizzati | **85**, `diff` vuoto sulla baseline pre-refactor |
| Campi `settings.*` | **83**, invariati |
| Campi visibili nella scheda Perp | da **49 a 30** con le tendine chiuse |
| Apertura tendina Smart SL | i campi salgono a **45**, i parametri compaiono |
| Punti interrogativi | presenti anche dentro le tendine (45 su 45 campi visibili) |

Verifiche eseguite sull'app in esecuzione, oltre che sul codice.

## SCOSTAMENTI DAL PIANO

- Nessuno rispetto a quanto concordato per lo Step B.
- **`npm run build` non eseguito** (regola AGENTS.md: `.env` reale nella root).
  Usato `tsc --noEmit`. **La build resta da verificare in CI.**

## QUESTIONI APERTE

- Le tendine partono sempre chiuse: non ricordano lo stato fra un'apertura e
  l'altra della scheda. Valutabile se dara' fastidio all'uso.
- Nessuna verifica su dispositivo reale: richiede una build APK da CI.
- Restano fuori dal setup 4 parametri reali non esposti dall'app
  (`spot_structural_stop_lookback_candles`, `perp_structural_stop_lookback_candles`,
  `spot_partial_take_profit_pct`, `spot_trailing_distance_pct`).

## STATO DELIVERABLE

**Completato sul branch `feature/setup-spot-perp`**, non integrato in `main`.
Reversibile con `git checkout main`.
