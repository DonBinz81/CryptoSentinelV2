# Report - Spiegazioni contestuali nel setup agente

Data: 2026-08-17
Branch: `feature/setup-spot-perp`

---

## COSA È STATO FATTO

Aggiunto un punto interrogativo accanto a **ogni** controllo del setup (85 in
tutto): toccandolo si apre un riquadro con una spiegazione sintetica del
parametro. Obiettivo dichiarato dall'utente: rendere il pannello comprensibile a
chi non ha costruito il bot.

Spostata inoltre la sezione "Risk · Chiusura di emergenza" **fuori dalle
sotto-schede**, fissa in cima al setup, sopra il menu Generale/Spot/Perp/Sistema.

## COME È STATO FATTO

**Componente `HelpTip`**: pulsante circolare da 16px accanto all'etichetta e
riquadro `fixed` centrato orizzontalmente sullo schermo.

- **Un solo riquadro aperto per volta**: l'apertura emette un evento globale
  (`helptip:open`) e gli altri si chiudono.
- Si chiude toccando altrove, scorrendo, ridimensionando o cambiando scheda.
- **Posizionamento verticale adattivo**: sotto il punto interrogativo, oppure
  sopra se in fondo allo schermo non c'e' spazio (stima 170px).
- **Larghezza adattiva** (`w-max`) con tetto a 19rem o alla larghezza dello
  schermo meno un margine: i testi brevi restano stretti, le liste di opzioni si
  allargano quanto serve senza andare a capo.
- `whitespace-pre-line`: nelle tendine ogni scelta sta su una riga propria.
- Carattere 13px (partito da 12, portato a 14, ridotto a 13 su indicazione
  dell'utente per equilibrio fra leggibilita' e ingombro).

**Punto critico risolto**: il `HelpTip` vive dentro l'elemento `<label>` che
comanda il campo. Senza intervento, toccare il punto interrogativo di un
interruttore ne avrebbe **invertito la spunta**. Il gestore chiama
`preventDefault()` e `stopPropagation()`.

**Prop `help` opzionale** aggiunta a `NumberInput`, `SelectInput` e
`ToggleInput`: dove non viene passata, il rendering resta identico a prima.

**Testi**: inseriti con uno script che si aggancia a `value={settings.X}` /
`checked={settings.X}`, quindi indipendente dalla formattazione del JSX e
immune a inserimenti nel punto sbagliato. Tre controlli non agganciabili
automaticamente (due generati in ciclo per gli scalini del ratchet, uno con
condizione al posto del campo) sono stati completati a mano.

Criterio di scrittura: **cosa fa** il parametro e **cosa comporta** usarlo, in
linguaggio non tecnico; per le tendine, una riga per ciascuna scelta.

## COSA È STATO VERIFICATO

Verifiche a ogni passaggio, con fotografia meccanica del pannello confrontata con
la baseline pre-refactor.

| verifica | esito |
|---|---|
| `npx tsc --noEmit` | pulito a ogni step |
| Controlli renderizzati | **85**, `diff` vuoto rispetto alla baseline |
| Campi `settings.*` | **83**, invariati |
| Copertura spiegazioni | **85/85**, nessun controllo scoperto |
| Tocco del "?" su un interruttore | la spunta **non cambia** |
| Un solo riquadro per volta | confermato: aprendone uno il precedente si chiude |
| Chiusura toccando altrove / cambiando scheda | confermata |
| Riquadro da campo in colonna destra (`?` a 235px) | centrato, dentro lo schermo |
| Riquadro da campo a fondo schermo (`?` a 787px su 812) | si apre verso l'alto, interamente visibile |
| Tendina a 3 scelte (Mode) | 4 righe scritte, 4 rese: nessuna va a capo |

Verifiche eseguite sull'app in esecuzione, non solo sul codice.

## SCOSTAMENTI DAL PIANO

- La chiusura di emergenza era stata concordata dentro la scheda Sistema; su
  richiesta successiva dell'utente e' stata portata fissa in cima, sempre
  visibile da ogni scheda. Il kill switch a tre livelli resta in Sistema.
- **`npm run build` non eseguito** (regola AGENTS.md: `.env` reale nella root).
  Usato `tsc --noEmit`, che non legge `.env`. **La build resta da verificare in CI.**
- Anteprima eseguita con un vite config temporaneo fuori dal repo, con `envDir`
  puntato a una cartella priva di `.env`: nessuna chiave di produzione caricata,
  confermato dall'app stessa che segnala il backend non configurato.
- Commenti del nuovo componente in italiano, coerenti con la prassi del
  repository (scelta dell'utente, gia' documentata).

## QUESTIONI APERTE

- **La forma del riquadro dipende dalla lunghezza del testo**: le spiegazioni di
  una sola frase producono riquadri larghi e bassi (rapporto ~3.4:1), quelle di
  due frasi restano intorno a 1.7:1. Uniformare richiederebbe di allungare
  artificialmente i testi brevi.
- **Contenuti da rivedere con l'utente**: le spiegazioni dei parametri dello
  Smart SL di secondo round (`split_l1_r2`, `split_l2_r2`, `split_l3_r2`) e dei
  delta di rebuy sono state dedotte dai commenti di `configs/strategy_perp.yaml`;
  vanno confermate.
- Nessuna verifica su dispositivo reale: richiede una build APK da CI.
- Le tendine sui blocchi pesanti (Smart SL, filtro shock BTC) restano rimandate.

## STATO DELIVERABLE

**Completato sul branch `feature/setup-spot-perp`**, non integrato in `main`.
Reversibile con `git checkout main`.
