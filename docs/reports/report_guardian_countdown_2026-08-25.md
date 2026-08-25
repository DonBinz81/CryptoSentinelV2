# Guardiano: conto alla rovescia live per la riattivazione

Data: 25 agosto 2026 · Branch: `claude/guardian-countdown` · Commit: `423a2ca`
Perimetro: C (app Android e UI) — lato app di NOTE/95 (backend, chat B)

## COSA

David: sapere quanto manca alla riattivazione del guardiano perp, in diretta in app.
Il backend espone `reentry_hours` nello snapshot da oggi (chat B, commit `7baadf1`);
mancava solo il lato app.

## COME

Un blocco sotto il banner giallo/rosso in `GuardianBanner.tsx`:

- **ancora** = il più recente fra `last_stop_at` e `changed_at`
- **bersaglio** = ancora + `reentry_hours` ore
- countdown = `bersaglio − ora`, ricalcolato ogni secondo con `setInterval`, nessun
  polling verso il backend: tutti i dati necessari sono già nello snapshot che l'app
  riceve dal refresh normale

Un passo alla volta, come nel motore (`guardian.py:252-263`): da RED il prossimo
passo è GIALLO, da GIALLO è VERDE — non salta direttamente a verde.

Due scelte deliberate:

- il testo dice esplicitamente **"è una proiezione, non una promessa"** e **"si
  azzera a ogni nuovo stop pieno perp"** — un countdown che sembra più affidabile di
  quanto sia è peggio di nessun countdown
- se il bersaglio è già passato (il ciclo lento di 5 minuti non ha ancora girato),
  non mostra un numero negativo: dice che sta aspettando il ciclo

## VERIFICATO

Banco di anteprima (regola del progetto: dati finti prima del `tsc`, prima del
commit), tre casi:

1. **RED** con i dati **reali** riportati dalla chat B in produzione oggi (ancora
   `10:28:05Z`, `reentry_hours=6`) — "Prossimo passo: GIALLO tra 1h 26m"
2. **YELLOW** con pochi minuti residui, per vedere i secondi scorrere
3. **bersaglio già passato** — mostra il messaggio di attesa, non un numero negativo

Confermato che il countdown è davvero live, senza ricaricare la pagina: letto
`"4m 56s"`, atteso 3 secondi nel banco, riletto `"4m 37s"`.

`npx tsc -b` ed ESLint puliti.

## SCOSTAMENTI

Nessuno noto.

## DELIVERABLE

- `src/services/agentApi.ts` — campo `reentry_hours` su `GuardianStatus`
- `src/components/GuardianBanner.tsx` — `CountdownRiattivazione`, montato nel banner
- Branch `claude/guardian-countdown`, commit `423a2ca`, da `main` `171c438`
