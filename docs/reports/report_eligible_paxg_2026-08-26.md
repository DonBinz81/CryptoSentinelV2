# Report - PAXG aggiunta all'universo eligible e alla watchlist perp

Data: 2026-08-26
Branch: `chat-infra/eligible-paxg`
Perimetro: D — infrastruttura e dati

---

## COSA È STATO FATTO

David ha chiesto perché PAX Gold non fosse tra le crypto tradabili nel perp. La verifica ha
mostrato che non c'era una ragione tecnica valida: PAXG non è mai stato nell'universo
eligible, e gli altri due token oro (XAUt, XAUM) erano stati rimossi il 17/08 con la
motivazione «illiquid on perp» — che **oggi non regge**.

Aggiunta PAXG all'universo (150 → 151 voci) e alla watchlist perp (37 → 38 simboli).

## COME È STATO FATTO

**I dati che hanno smentito la motivazione esistente**, presi da Aster (24h):

| | volume 24h | scambi | escursione |
|---|---:|---:|---:|
| **PAXG** | **254.067 $** | 1.717 | 1,92% |
| CAKE *(in watchlist)* | 27.111 $ | 255 | 3,08% |
| TRX *(in watchlist)* | 137.834 $ | 639 | 1,57% |
| INJ *(in watchlist)* | 194.443 $ | 578 | 7,39% |

PAXG è più liquida di tre coin che il bot trada già, e la sua escursione è in linea con BTC
(2,07%). `PAXGUSDT` risulta `TRADING` su Aster.

**Sul limite dei 150**: non era un vincolo tecnico. Il codice impone `100-200`
(`config.py`, `HARD_ELIGIBLE_TOKEN_MIN_COUNT`/`MAX_COUNT`); il 150 era una convenzione di
questo fork scritta in `AGENTS.md`, derivata dai 149 dell'upstream. Aggiornata a 151 con
l'autorizzazione esplicita di David, aggiungendo in quella regola la distinzione fra limite
tecnico e convenzione, che prima non era scritta da nessuna parte.

**La watchlist**: `PUT /agent/watchlist/perp` ha inizialmente risposto
`400 - Assets not in the master watchlist: PAXG`. È il guardrail della nota 28 che funziona
come deve: un simbolo entra prima nella master, poi nelle liste di mercato. Fatti i due
passi nell'ordine, verificando che la watchlist spot restasse invariata.

## COSA È STATO VERIFICATO

| verifica | esito |
|---|---|
| Conteggio e unicità dopo normalizzazione | **151 / 151** |
| `get_settings()` sull'interprete del servizio | costruito, **il backend parte** |
| Deploy di `eligible_tokens.yaml` | hash identico a `main` |
| Riavvio | `active`, health 200, **0 errori**, `eligible_token_count: 151` |
| Watchlist master | 71 → **72**, PAXG presente |
| Watchlist perp | 37 → **38**, PAXG presente |
| Watchlist spot | **39, invariata** |
| Warmup klines | `PAXGUSDT` spot e futures, **HTTP 200** |
| Ciclo di scansione successivo | **38 asset scansionati**, 0 errori |

Prima del riavvio è stato preso lo snapshot a caldo del database
(`~/backups/prestop_paxg_20260826_201509.db` + `-wal`), come impone la nota 54.

## SCOSTAMENTI DAL PIANO

Nessuno sul risultato. Due passaggi non previsti, entrambi risolti:

1. Il primo test di validazione è **fallito per un errore mio**: avevo istanziato `Settings()`
   direttamente, che non applica i YAML e parte da lista vuota (0 token, sotto il minimo di
   100). Rifatto con `get_settings()`, la via che usa davvero l'avvio.
2. Il `PUT` sulla watchlist perp è stato rifiutato finché PAXG non è entrata nella master.

## QUESTIONI APERTE

1. **XAUUSDT resta escluso** pur avendo 9,9 M$ di volume 24h — quaranta volte PAXG. Se
   l'oro si rivelasse utile, è il candidato successivo.
2. **Il senso strategico non è stato valutato qui**: la strategia è mean-reversion sul
   Volume Profile, tarata su crypto; l'oro ha driver macro diversi e bassa correlazione col
   paniere. Domanda per il perimetro B, non risolvibile con i volumi.
3. **Costi contro volatilità**: su un asset a basso ATR i costi fissi possono superare il
   movimento del TP1 — è quanto documentato dalla nota 26 su XAUT. Non è un problema di
   liquidità e riguarda ogni simbolo poco volatile, ma su PAXG va sorvegliato.

## STATO DELIVERABLE

- `configs/eligible_tokens.yaml` — 151 voci, PAXG documentata in testata. In produzione.
- `AGENTS.md` — regola aggiornata a 151 con la distinzione limite/convenzione.
- Watchlist master e perp aggiornate via API (nessun accesso diretto al database).
- `docs/reports/report_eligible_paxg_2026-08-26.md` — questo report.
