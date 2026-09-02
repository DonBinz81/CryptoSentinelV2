# App: il pulsante "Riprendi" era solo dentro Setup, non dove si ferma

Data: 2 settembre 2026 · Branch: `claude/resume-button-runtime-card` · Commit: `3a9f449`
Perimetro: C (app Android e UI)

## COSA

David: premuto hard stop, nessun tasto di ripristino visibile — "sinceramente ce n'è
bisogno".

## COME

Il pulsante "Riprendi agente" **esisteva già**, ma solo dentro `SetupPane`, sopra le
sotto-schede. Il comando che **ferma** tutto (⛔ "Chiudi tutto", nel banner del
guardiano) è sempre visibile su ogni scheda dell'app — quello che **riparte** stava
solo in Setup. Chi premeva l'emergenza dal banner restava bloccato senza sapere dove
andare a sbloccarsi.

Aggiunto "Riprendi agente" nella card **"Runtime"** in cima ad `AgentTab` — lo stesso
punto sempre visibile, appena sopra il banner del guardiano. Compare quando
`kill_switch` non è `"running"` (sia `hard_stop` sia `soft_stop`, non solo il primo),
disabilitato senza admin token con lo stesso avviso già usato altrove nell'app.

Estratto in `ResumeAgentButton`, componente isolato (come `GuardianBanner`,
`ScannerStatusPanel`) invece di codice inline dentro `AgentTab`: `AgentTab` fa chiamate
di rete reali al mount (`refresh()` chiama `fetchAgentStatus` e altri 8 endpoint), quindi
non è testabile nel banco di anteprima senza un mock del backend — il componente
piccolo estratto sì.

## VERIFICATO

Banco di anteprima (regola del progetto: dati finti prima del `tsc`, prima del commit),
quattro casi:

1. `hard_stop` con admin token → pulsante premibile, verificato anche il **click reale**
   (`"Attendi…"` compare dopo il click)
2. `hard_stop` senza admin token → disabilitato, avviso "serve l'admin token" visibile
3. `soft_stop` con admin token → compare identico, non solo per `hard_stop`
4. `running` → **nessun residuo**, il blocco sparisce del tutto

`npx tsc -b` ed ESLint puliti: stessi 5 avvisi preesistenti su `AgentTab.tsx`, nessuno
nuovo.

## SCOSTAMENTI

Nessuno noto.

## DELIVERABLE

- `src/components/AgentTab.tsx` — `ResumeAgentButton`, montato nella card Runtime
- Branch `claude/resume-button-runtime-card`, commit `3a9f449`, da `main` (allineato a
  `origin/main` al momento del lavoro)
