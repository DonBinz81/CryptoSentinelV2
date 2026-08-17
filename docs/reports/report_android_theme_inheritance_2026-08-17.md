# Report - Ereditarieta' del tema Android e colori persi su API 35+

Data: 2026-08-17
Branch: `main`
Seguito di: `report_dropdown_readability_2026-08-17.md`

---

## COSA È STATO FATTO

Corretto il difetto emerso durante il fix precedente: i colori dichiarati dall'app
(`colorAccent` blu, `windowBackground`, `statusBarColor`) **non arrivavano su
Android 15+**, perche' `values-v35/styles.xml` ridichiarava `AppTheme` da zero.
E' la causa dell'accento verde acqua visto nello screenshot dell'utente.

Emersa e coperta anche una seconda strada non prevista: l'activity dichiara un tema
**diverso** da quello a cui era agganciato il fix precedente.

## COME È STATO FATTO

**Difetto 1 - risorsa qualificata che sostituisce invece di fondersi.**
Una risorsa in `values-v35/` **rimpiazza integralmente** l'omonima in `values/`: gli
item non si sommano. `AppTheme` e `AppTheme.NoActionBar` erano ridichiarati li' con
parent `Theme.AppCompat.DayNight.NoActionBar` e il solo opt-out edge-to-edge, quindi
su API 35+ perdevano tutti gli altri item.

Correzione: estratto uno stile **`AppThemeBase`** in `values/` con tutti gli item
comuni; `AppTheme` e `AppTheme.NoActionBar` lo estendono in **entrambi** i file, e la
variante `v35` aggiunge soltanto `android:windowOptOutEdgeToEdgeEnforcement`. I colori
sono ora dichiarati **una volta sola** e non possono piu' divergere fra i due file.

**Difetto 2 - il tema dell'activity non e' quello che si presumeva.**
`AndroidManifest.xml` assegna all'`<application>` il tema `AppTheme`, ma
**`MainActivity` lo sovrascrive** con `AppTheme.NoActionBarLaunch`, che ha parent
`Theme.SplashScreen` (androidx). Quello stile **non definisce `postSplashScreenTheme`**
e nel progetto **non risulta il plugin splash screen** che eseguirebbe il passaggio al
tema post-avvio. Non e' quindi determinabile staticamente quale tema sia attivo quando
l'utente apre un menu a tendina.

Conseguenza sul fix precedente: se l'activity resta sul tema di lancio, in **v1.0.31**
l'aggancio `alertDialogTheme` (messo solo su `AppTheme` e `AppTheme.NoActionBar`) non
veniva letto e funzionava la sola regola CSS.

Correzione: `colorAccent`, `colorPrimary`, `colorPrimaryDark` e l'aggancio
`alertDialogTheme` / `android:alertDialogTheme` **ripetuti anche su
`AppTheme.NoActionBarLaunch`**. Non potendo ereditare da `AppThemeBase` (parent
splash-screen gia' occupato), la ripetizione e' inevitabile ed e' commentata nel file.
Cosi' il risultato non dipende da quale dei due temi vinca a runtime.

## COSA È STATO VERIFICATO

| verifica | esito |
|---|---|
| XML dei due `styles.xml` ben formati | ok (parser) |
| Ogni `@style/...` referenziato esiste | ok: `AppAlertDialog` definito 1 volta, agganciato 4; `AppThemeBase` definito 1, esteso 4 |
| Stili referenziati dal manifest (`AppTheme`, `AppTheme.NoActionBarLaunch`) | entrambi definiti, entrambi con l'aggancio ai dialoghi |
| `AppTheme.NoActionBar` | non referenziato da manifest ne' da codice: resta definito ma inutilizzato (preesistente) |
| Compilazione risorse Android | vedi sezione stato (fallirebbe se uno stile non si risolvesse) |

## SCOSTAMENTI DAL PIANO

- L'intervento concordato era il solo difetto 1 ("ripetere tre valori nel file v35").
  E' stato risolto **estraendo uno stile base** invece di duplicare: stesso effetto,
  ma i colori restano dichiarati in un punto solo.
- Il difetto 2 non era previsto: e' emerso ispezionando il manifest prima di scrivere.
  Ampliamento comunicato all'utente contestualmente.
- `postSplashScreenTheme` **non** aggiunto: cambierebbe il comportamento di avvio e
  richiederebbe `installSplashScreen()` lato codice. Fuori dallo scopo.
- `npm run build` non eseguito in locale (regola AGENTS.md: `.env` reale nella root).
- `docs/PROJECT_STRUCTURE.md` non aggiornato: nessun file nuovo.

## QUESTIONI APERTE

- **Quale tema sia attivo a runtime resta non determinato.** Il fix e' scritto per non
  dipenderne, ma la domanda in se' non e' chiusa: si risolve solo leggendo il tema
  dell'activity su dispositivo.
- `AppTheme.NoActionBar` non e' usato da nessuno. Rimuoverlo e' possibile ma e'
  pulizia, non correzione: lasciato.
- Su API 35+ `AppTheme.NoActionBarLaunch` non ha l'opt-out edge-to-edge (era gia' cosi').
  Se l'activity resta su quel tema e comparisse una fascia bianca in cima, e' li' che
  va aggiunto. Nessuna fascia risulta segnalata finora.
- **Verifica sul campo ancora da fare, con il telefono in tema chiaro.**

## STATO DELIVERABLE

Committato su `main`, build APK in CI.
Reversibile con `git revert` del commit.
