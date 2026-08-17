# Report - Setup agente diviso per mercato (Step A)

Data: 2026-08-17
Branch: `feature/setup-spot-perp` (main non toccato)

---

## COSA È STATO FATTO

Riorganizzato il pannello Setup dell'app in **quattro sotto-schede** — Generale,
Spot, Perp, Sistema — separando i parametri per mercato. Prima erano 514 righe in
un'unica colonna, con una sezione "Filtri mercato" che mescolava controlli spot e
perp.

Nessuna modifica al backend, alle API, al database o ai valori dei parametri.

## COME È STATO FATTO

**Ripartizione** (83 campi totali: 9 globali, 19 spot, 55 perp):

| scheda | sezioni |
|---|---|
| Generale | General, Filtri globali, Risk globale, Grafico trade |
| Spot | Spot — risk, Spot — strategia, Spot — protezioni |
| Perp | Perp — risk, Perp — strategia, Perp — protezioni |
| Sistema | Admin session, Kill switch, Chiusura di emergenza, Liquidita', Onboarding |

**Il blocco misto "Filtri mercato" e' stato spezzato** in "Spot — protezioni"
(breakeven + modalita', stop loss, trailing, time stop) e "Perp — protezioni"
(breakeven + modalita' + min $, stop loss, time stop, filtro shock BTC, Smart SL),
mentre il filtro inversione mercato e' rimasto in "Filtri globali".

**Correzione rispetto al piano iniziale**: il piano prevedeva di lasciare "Filtri
mercato" intatto in Generale e spezzarlo in uno step successivo. Verificando si e'
scoperto che l'interruttore del time stop (riga 1582) e le sue ore (riga 1706)
erano gia' in sezioni diverse: lasciando il blocco in Generale, il toggle sarebbe
finito in una scheda e il parametro in un'altra, **peggiorando** la situazione. Lo
spacchettamento e' stato quindi anticipato a questo step.

**Implementazione**: `type SetupTab` + `SETUP_TABS`, stato locale `setupTab`,
barra a 4 pulsanti con lo stesso schema gia' usato da `CoinsPane`. I gruppi di
sezioni sono avvolti in condizionali; le sezioni non sono state riscritte, solo
spostate (il blocco "Perp — protezioni", 112 righe, e' stato spostato con uno
script per non alterarne il contenuto).

Il pulsante di salvataggio e il badge "modifiche non salvate" restano **fuori
dalle schede**, sempre visibili: verificato che nel loro blocco non compaia
`setupTab`.

## COSA È STATO VERIFICATO

Metodo: fotografia meccanica del pannello **prima** e **dopo**, con confronto riga
per riga (tipo di controllo, etichetta, campo, step, opzioni delle select).

| verifica | esito |
|---|---|
| `npx tsc --noEmit -p tsconfig.app.json` | nessun errore |
| Controlli renderizzati | **85 prima, 85 dopo**, `diff` vuoto |
| Campi `settings.*` | **83 prima, 83 dopo**, `diff` vuoto |
| Duplicati introdotti | rilevati 3 in corso d'opera (`spot_sl_mode`, `spot_trailing_enabled`, `spot_time_stop_enabled`) e rimossi; conteggio tornato a 85 |
| Sezioni per scheda | verificate una per una con estrazione automatica |
| Salva / badge dirty | fuori dai condizionali di scheda |

## SCOSTAMENTI DAL PIANO

- **Spacchettamento di "Filtri mercato" anticipato** dallo Step B allo Step A, per
  non separare i toggle dai loro parametri (vedi sopra).
- **`npm run build` non eseguito**: la regola di AGENTS.md vieta build frontend
  locali quando possono caricare il `.env` reale, ed esiste un `.env` da 2298 byte
  nella root. E' stato usato solo `tsc --noEmit`, che non legge `.env`.
  **La build completa resta da verificare in CI.**
- **Lint non eseguito**: AGENTS.md registra un debito lint React preesistente da
  risolvere come task separato; non e' un gate.
- Lavoro su branch dedicato anziche' su `main`, per garantire la reversibilita'
  richiesta dall'utente.

## QUESTIONI APERTE

- **Nessuna verifica visiva**: il refactor non e' stato provato su dispositivo,
  perche' richiede una build APK da CI. L'app installata sul telefono **non e'
  toccata** finche' non si costruisce una nuova release.
- Le tendine sui blocchi pesanti (Smart SL, filtro shock BTC) sono rimandate allo
  step successivo, come concordato.
- Restano non esposti dall'app 4 parametri reali:
  `spot_structural_stop_lookback_candles`, `perp_structural_stop_lookback_candles`,
  `spot_partial_take_profit_pct`, `spot_trailing_distance_pct`.
- L'ordine dei campi dentro le sezioni non e' stato rivisto (rimandato).

## STATO DELIVERABLE

**Completato sul branch `feature/setup-spot-perp`**, non integrato in `main`.
Reversibile con `git checkout main`; il branch puo' essere eliminato senza
conseguenze. Backup delle impostazioni live in
`~/backups/settings_prerefactor_*.json` sulla VPS (97 campi).
