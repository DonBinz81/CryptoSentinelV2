# Scanner: un pair morto non tiene il banner giallo in eterno

Data: 26 agosto 2026 · Branch: `claude/scanner-error-threshold` · Commit: `0ad2fc5`
Perimetro: C (app Android e UI) — diagnosi della chat B, fix nostro

## COSA

David: il riquadro "SCANNER: FILTRI ATTIVI" restava acceso da un giorno intero,
anche con zero filtri attivi. Diagnosi in sola lettura della chat B: il dato
backend era corretto e fresco (`filter: 0`), il difetto era nel criterio di
visualizzazione dell'app.

## COME

`marcatoBloccato()` accendeva il giallo con `error > 0`, **senza soglia**. HTX era
in watchlist perp ma senza klines su nessun exchange
(`no_klines_any_cex_HTXUSDT`): falliva la scansione a **ogni** ciclo di 5 minuti,
per sempre. Un pair morto nel catalogo — non un guasto del sistema — ma il codice
trattava `error: 1` esattamente come `error: 50`.

È lo **stesso errore di ragionamento** già corretto per i filtri (nota 72, dove
`filter > 0` dava un falso "bloccato" su 1/28), qui ripetuto sull'errore.

Corretto con una soglia proporzionale, coerente con quella dei filtri ma più
severa (10% invece di 20%, perché un errore è comunque più serio di un filtro):

- `erroriRotti(m) = m.error >= max(2, 10% degli scansionati)` → banner giallo
- sotto soglia: **non sparisce silenziosamente** — compare come nota discreta nel
  chip verde ("1 perp non scansionabile"), invece che come allarme

## VERIFICATO

Banco di anteprima (regola del progetto: dati finti prima del `tsc`, prima del
commit), due casi:

1. I numeri **esatti** di produzione di oggi (spot 39 scansionati/0 errori, perp 32
   scansionati/filter 2/error 1) → prima era giallo perenne, ora **verde con la
   nota**
2. Un guasto vero (5 errori su 30, 16%) → resta **giallo**, come deve

`npx tsc -b` ed ESLint puliti.

## SCOSTAMENTI

Nessuno noto. David ha rimosso HTX manualmente dalla watchlist come sollievo
immediato mentre il fix era in corso — il fix resta necessario per il prossimo
pair morto (la watchlist perp è stata appena estesa a 200 asset, il che rende più
probabile, non meno, che ricapiti).

## DELIVERABLE

- `src/components/ScannerStatusPanel.tsx`
- Branch `claude/scanner-error-threshold`, commit `0ad2fc5`, da `main` `451790c`
