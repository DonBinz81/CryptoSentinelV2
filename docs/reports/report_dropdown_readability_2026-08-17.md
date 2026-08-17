# Report - Leggibilita' dei menu a tendina sul dispositivo

Data: 2026-08-17
Branch: `main`

---

## COSA È STATO FATTO

Le voci dei menu a tendina del setup agente (Long / Short / Both e simili) apparivano
**testo scuro su fondo scuro**, praticamente illeggibili — e non sempre: a volte
uscivano chiare. Segnalato dall'utente con screenshot.

Il colore del testo di quelle voci e' stato fissato chiaro (`#f9fafb`) in modo che
non dipenda piu' dal tema impostato sul telefono.

Nessuna modifica a controlli, parametri, valori o layout: solo colore.

## COME È STATO FATTO

**Causa.** Il popup di un `<select>` non e' HTML: Android lo disegna come finestra di
sistema, che prende i colori dal **tema dell'app Android**, non dal foglio di stile.
Il tema e' `Theme.AppCompat.DayNight`, cioe' *segui il telefono*, mentre lo sfondo e'
inchiodato a un colore scuro in entrambe le modalita'. Con il telefono in tema chiaro
si otteneva testo scuro (deciso dal sistema) su fondo scuro (deciso da noi).

Conferma nello screenshot: il radio selezionato era **verde acqua**, il `colorAccent`
di default di AppCompat, non il blu `#3b82f6` dichiarato dall'app — segno che gli
item del tema non stavano arrivando (vedi sotto).

**Interventi** (tutti in aggiunta, nessuna riga esistente modificata):

1. `src/index.css` - `select option`/`select optgroup` con `color: #f9fafb` e
   `background-color: #111827`. Copre i dispositivi dove il popup lo disegna il
   motore web invece del sistema.
2. `android/.../values/styles.xml` - nuovo stile `AppAlertDialog`
   (`textColor`, `textColorPrimary`, `textColorSecondary`,
   `textColorAlertDialogListItem` chiari; sfondo `#111827`; accento `#3b82f6`),
   agganciato ad `AppTheme` e `AppTheme.NoActionBar` via `alertDialogTheme` e
   `android:alertDialogTheme`.
3. `android/.../values-v35/styles.xml` - **stesso aggancio ripetuto**. Una risorsa
   qualificata **sostituisce** quella base invece di fondersi con essa: senza questa
   ripetizione il fix non avrebbe avuto alcun effetto su Android 15+, cioe' proprio
   sul dispositivo che ha segnalato il problema.

Lo sfondo della finestra e' stato fissato oltre al testo, pur essendo fuori dalla
richiesta letterale ("solo le scritte bianche"): senza, su un telefono in tema chiaro
la finestra potrebbe uscire bianca e il testo bianco sparirebbe. Il valore scelto
(`#111827`, `dark-800`) e' quello che i campi hanno gia', quindi visivamente invariato.
Scelta comunicata all'utente ed esplicitamente accettata.

## COSA È STATO VERIFICATO

| verifica | esito |
|---|---|
| XML dei due `styles.xml` ben formati | ok (parser) |
| `npx tsc --noEmit -p tsconfig.app.json` | nessun errore |
| Ampiezza del diff | **32 righe aggiunte, 0 rimosse, 0 modificate** |
| Aggancio presente in entrambi i file di tema | verificato |
| Build APK | vedi sezione stato |

## SCOSTAMENTI DAL PIANO

- La proposta iniziale prevedeva di portare il tema Android da `DayNight` a scuro
  fisso. **Respinta dall'utente**: solo il colore del testo, il tema resta `DayNight`.
  Applicata la versione ristretta.
- Fissato anche lo sfondo della finestra di sistema (motivazione sopra).
- `npm run build` non eseguito in locale (regola AGENTS.md: `.env` reale nella root).
  Usato `tsc --noEmit`; la build vera gira in CI.
- `docs/PROJECT_STRUCTURE.md` non aggiornato: nessun file nuovo, nessuna cartella
  nuova, nessun modulo spostato.

## QUESTIONI APERTE

- **Difetto preesistente non corretto**: `values-v35/styles.xml` ridefinisce `AppTheme`
  da zero invece di estenderlo, quindi su Android 15+ l'app perde `colorPrimary`,
  `colorAccent`, `android:windowBackground`, `android:statusBarColor` e
  `windowLightStatusBar` dichiarati in `values/styles.xml`. E' la causa dell'accento
  verde acqua al posto del blu. **Segnalato all'utente, lasciato aperto per sua
  decisione**: si risolve ripetendo quegli item nel file `v35` o estraendo uno stile
  base comune.
- **Verifica sul campo da fare con il telefono in tema chiaro**: e' la condizione che
  produceva il difetto. In tema scuro le tendine erano gia' leggibili, quindi provare
  solo in scuro non dimostra nulla.

## STATO DELIVERABLE

Committato su `main`. Reversibile con un `git revert` del commit: essendo sole
aggiunte, la rimozione riporta esattamente al comportamento precedente.
