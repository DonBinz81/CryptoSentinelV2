# Report — La soglia di liquidità entra nella disponibilità (2026-08-17)

## COSA È STATO FATTO

Una coin con **41 $ di pool** risultava «disponibile» nel setup, perché la pool tecnicamente
esisteva. Era una mezza verità: il Risk Manager avrebbe comunque rifiutato il trade, quindi
l'interfaccia prometteva qualcosa che il motore non può mantenere.

Ora la disponibilità spot applica la **stessa soglia** del `liquidity_guard`: sotto quel
valore lo stato è `unavailable`, con il motivo e i due numeri nel messaggio.

## COME È STATO FATTO

**Una sola fonte per la soglia.** Il valore è letto da `mobile_agent_settings` in
RuntimeState — esattamente da dove lo legge il Risk Manager — con fallback alla
configurazione. Leggere soltanto il default avrebbe ricreato due verità, perché la soglia si
cambia dall'app: la UI avrebbe detto «tradabile» mentre il motore rifiutava.

**Una profondità non misurabile non rende indisponibile un pair.** Se la misura è `None` —
rete di test, simbolo non mappato, lettura fallita — il comportamento resta quello di prima:
`unknown`, che avverte senza bloccare. Solo una misura **reale e sotto soglia** produce
`unavailable`. È la stessa regola applicata in tutto il modulo: un limite nostro non deve
mai somigliare a un mercato assente.

**Formato dei numeri**: separatore delle migliaia all'italiana (`50.000`, non `50,000`),
coerente con il resto dei messaggi.

### File

| file | natura |
|---|---|
| `backend/app/execution/venue_availability.py` | `_liquidity_floor`, soglia applicata in `_spot_status`, helper di formato |
| `backend/tests/unit/test_venue_availability.py` | 3 test nuovi; l'helper delle settings finte estese ai due campi |

## COSA È STATO VERIFICATO

**Suite completa sulla VPS**: **295 passed, 2 failed, 2 skipped** (le due preesistenti).
Golden test invariato.

**Prova su mainnet con la mappa reale a 55 indirizzi**:

```
BTC · ETH · CAKE · TRX · U          available
GRAM     659 $   unavailable — liquidità insufficiente, soglia 50.000 $
WLFI       0 $   unavailable
ETC       41 $   unavailable
```

**In produzione** (testnet, come atteso): tutte e 31 le coin della watchlist spot restano
`unknown` con il motivo «rete BSC di test», quindi **nessun blocco introdotto oggi**; il
motore continua a lavorare (decisioni spot su `GRAM` e `H` subito dopo il riavvio).
Deploy verificato per hash, backup in `predeploy_20260817_225034`, zero errori.

## SCOSTAMENTI DAL PIANO

Nessuno. Restava la scelta fra «`unavailable`» e «`available` con avviso»: adottata la
prima, perché il caso che ha motivato il lavoro — ETC a 41 $ mostrata come disponibile — è
esattamente ciò che si voleva evitare.

## QUESTIONI APERTE

1. **L'effetto si vedrà solo su mainnet**: su testnet la profondità non è misurabile e lo
   stato resta `unknown`.
2. **`LUNC`** resta senza indirizzo BSC: unica coin della watchlist spot che in live
   verrebbe saltata con `spot_token_not_mapped`.
3. Il perp non ha un concetto equivalente di profondità: su Aster la disponibilità è una
   proprietà del mercato, non della liquidità di una pool.

## STATO DELIVERABLE

Completo, deployato e verificato. Commit `ad43cda`.
