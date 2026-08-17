# Report - Spiegazione contestuale sulla sezione Onboarding

Data: 2026-08-17
Branch: `main`

---

## COSA È STATO FATTO

Aggiunto il punto interrogativo con la spiegazione anche alla sezione **Onboarding**
della scheda Sistema, che ne era priva: era l'unico blocco del setup senza alcun testo
di aiuto, ne' inline ne' a comparsa.

Per accogliere quella spiegazione, che e' la piu' lunga dell'app (10 righe), il
componente `HelpTip` ha ora una posizione alternativa **in cima allo schermo**,
usata solo dove serve.

## COME È STATO FATTO

**Il testo** descrive i 7 servizi controllati dall'endpoint
`POST /api/v1/mobile/agent/onboarding/validate` — CMC, Claude, Wallet, BSC RPC, FCM,
TWAK, x402 — con una riga ciascuno, il significato di `ready`/`missing` e
l'avvertenza che **il controllo verifica solo che i valori siano impostati, non che
funzionino**: l'endpoint fa `bool(...)` sulla presenza delle credenziali, niente
chiamate di prova. Contenuto ricavato dal codice della route, non dedotto.

**Prop `top` su `HelpTip`.** Il posizionamento esistente apre il riquadro sotto il "?",
o sopra se stimava di non starci (`STIMA = 170`). Con questa spiegazione la stima e'
insufficiente: il riquadro misura **364px**, e ancorato al "?" di Onboarding (y=502 su
790) sarebbe finito a **890 su 790**, tagliato di 100px. Con `top` il riquadro si apre
a `top: 64` centrato, sempre interamente visibile.

Aggiunto anche `max-h-[70vh] overflow-y-auto` come rete di sicurezza per testi futuri
piu' lunghi dello schermo. Non ha effetto sui riquadri attuali (nessuno la raggiunge).

**Scostamento in corso d'opera, poi rientrato.** In una prima stesura il
posizionamento in alto era stato applicato a **tutti** gli 85 help. L'utente ha
chiesto di lasciare invariata la regola precedente e di usare la nuova solo dove
serve: ripristinato il comportamento originale e reso opzionale. Oggi `top` e' usato
da **1 solo** HelpTip su 4 punti di aggancio.

## COSA È STATO VERIFICATO

Verifiche sull'app in esecuzione (anteprima con `envDir` isolato, nessuna chiave di
produzione caricata), oltre che sul codice.

| verifica | esito |
|---|---|
| `npx tsc --noEmit -p tsconfig.app.json` | nessun errore |
| Controlli renderizzati | **85**, `diff` vuoto sulla baseline pre-modifica |
| Campi `settings.*` | **83**, invariati |
| Riquadro Onboarding | top **64**, bottom **428** su viewport 790: interamente visibile, centrato |
| Help normale in cima (`?` a y=517) | si apre **sotto**, a 541 — regola precedente intatta |
| Help normale in fondo (`?` a y=712) | si apre **sopra**, bottom 704 — regola precedente intatta |
| Un solo riquadro alla volta | confermato: aprendone un altro il precedente si chiude |
| Chiusura toccando altrove | confermata (da 1 riquadro a 0) |
| Corpo del testo | 13px, 10 righe, nessuno scorrimento interno necessario |

## SCOSTAMENTI DAL PIANO

- Il posizionamento in alto, inizialmente esteso a tutti gli help, e' stato ristretto
  al solo Onboarding su indicazione dell'utente (vedi sopra).
- `npm run build` non eseguito in locale (regola AGENTS.md: `.env` reale nella root).
  Usato `tsc --noEmit` piu' l'anteprima isolata; la build vera gira in CI.
- `docs/PROJECT_STRUCTURE.md` non aggiornato: nessun file nuovo.

**Correzione a un dato dei report precedenti**: durante questo lavoro avevo annunciato
che i controlli fossero 86 e non 85. Era sbagliato: l'86ª riga dello snapshot e' la
riga di totale stampata dallo script. **85 e' il numero corretto** e i report
precedenti non vanno modificati.

## QUESTIONI APERTE

- Le altre sezioni della scheda Sistema (Admin session, Kill switch, Liquidita')
  restano senza "?": Kill switch e Liquidita' hanno gia' un testo descrittivo inline,
  Admin session no. Non richiesto, non fatto.
- La soglia `STIMA = 170` resta approssimativa per gli help ordinari: funziona perche'
  nessuno di essi supera quell'altezza, ma e' una stima, non una misura.
- Verifica su dispositivo reale da fare con l'APK.

## STATO DELIVERABLE

Committato su `main`, build APK in CI.
