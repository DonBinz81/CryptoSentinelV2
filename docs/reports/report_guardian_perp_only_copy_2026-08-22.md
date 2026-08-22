# Guardiano: i testi dicono "perp", non più un blocco generico

Data: 22 agosto 2026 · Branch: `claude/guardian-perp-only-copy` · Commit: `afacb87`
Perimetro: C (app Android e UI) — segnalazione girata dalla chat E (seconda strategia perp)

## COSA

David, guardando il pannello **Spot**, ha creduto che il guardiano giallo/rosso stesse
limitando anche lo spot. Non è mai stato vero: il guardiano è perp-only per
costruzione. Il banner però è identico e appare in cima all'header su entrambi i
pannelli (Spot e Perp), e i testi non nominavano mai il mercato a cui si riferiscono.

## COME

Verificato sul codice, non solo sul resoconto ricevuto:

- `record_stop` (il segnale che alimenta il guardiano) è chiamato **solo** da
  `_close_perp_position` (`service.py:1450`, chiamata a riga 1567) — nessun
  equivalente lato spot
- il blocco RED sta dentro `evaluate_perp` (righe 977-993)
- lo scaling YELLOW ha la guardia esplicita `market == "perp"` (riga 2841)

Tre punti indipendenti, tutti perp-only. Corretto in `GuardianBanner.tsx`:

- titolo rosso: **"PROTEZIONE PERP ATTIVA"** (era "PROTEZIONE ATTIVA")
- titolo giallo: **"PRUDENZA PERP"** (era "PRUDENZA")
- chip verde: **"Regime normale (perp)"** (era "Regime normale")
- nuova riga su giallo/rosso: **"Lo spot non è toccato: entra normalmente."**

Prima di aggiungere quella riga, verificato che non introducesse una nuova
imprecisione: `POST /risk/close-all` (il pulsante "Chiudi tutto" dentro lo stesso
banner) chiude **spot e perp insieme**, quindi la riga parla esplicitamente del
*blocco automatico* del guardiano, non dei comandi manuali — che restano
volutamente globali e non sono stati toccati.

## VERIFICATO

- Banco di anteprima (regola del progetto: dati finti **prima** di `tsc`/commit) sui tre
  stati verde/giallo/rosso: i testi nominano il perp, la riga di chiarimento compare
  correttamente solo su giallo e rosso.
- `npx tsc -b` (non `--noEmit`) e ESLint puliti su `GuardianBanner.tsx`.

## SCOSTAMENTI

Nessuno noto. Modifica di sole stringhe, nessuna logica toccata.

## DELIVERABLE

- `src/components/GuardianBanner.tsx`
- Branch `claude/guardian-perp-only-copy`, commit `afacb87`, da `main` `d0c93db`
