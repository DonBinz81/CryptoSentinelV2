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

---

## AGGIORNAMENTO 2026-08-27 - PAXG RITIRATA DALLA WATCHLIST

Il perimetro strategia (chat B) ha risposto alla domanda che questo report lasciava aperta,
e la risposta e' **no**. La verifica sulla liquidita' fatta qui era corretta ma misurava la
variabile sbagliata: il collo di bottiglia non e' il volume, e' la **volatilita'**.

| misura | valore |
|---|---|
| NATR mediano PAXG (14, 5m, 12 mesi) | **0,086%** |
| TP1 tipico (2,5 x ATR) | **0,215%** |
| Backtest 12 mesi, senza filtri | 1.396 trade, **PF 0,001**, -8.337 $ |
| TP1 raggiunto | **5%** delle volte (paniere: ~78%) |
| PF di PAXG contro i pair sani | **0,33** contro 0,48-0,67 |
| Con `min_rr` a 1,2 | **0 trade**: si auto-esclude |

⚠️ **RETTIFICA del 2026-08-27, segnalata dalla chat B.** La prima stesura di questa sezione
diceva che il TP1 (0,215%) sta **sotto il costo di un giro maker (0,28%)**, quindi
"si perde anche vincendo il 100% dei trade". **E' sbagliato**: lo 0,28% della nota 77 e' il
**deficit residuo del paniere a fee circa zero**, non il costo di un giro - i costi reali
sono ~0,05-0,1%. L'affermazione "matematicamente perdente" non regge e va cancellata.

**Il verdetto su PAXG resta valido**, ma per le ragioni corrette: profit factor **0,33**
contro lo 0,48-0,67 dei pair sani nello stesso setup (quindi il peggiore del gruppo, non
semplicemente negativo), negativo in **entrambe** le meta' del periodo, driver macro
estranei al paniere, e con il `min_rr` a 1,2 previsto dalla configurazione studiata
produce **zero trade** - si esclude da solo. Nessun rollback necessario.

E' comunque la stessa famiglia di problema della nota 26 su XAUT, e vale anche per
XAUUSDT nonostante i suoi 9,9 M$ di volume.

**Cosa e' stato fatto**: PAXG rimossa dalla **watchlist perp** via API (38 -> 37 simboli),
su decisione di David. Resta nell'universo eligible (151 voci, `AGENTS.md` invariato) e
nella master watchlist, quindi e' riattivabile dall'app senza altre modifiche. Watchlist
spot invariata (39). Verificato sul ciclo successivo: **37 asset scansionati, 0 errori**.

**L'unico trade prodotto**, per memoria: uno short aperto il 27/08 alle 02:17 e chiuso alle
03:04 in tre pezzi (TP1 +1,29 $, ratchet +0,41 $, breakeven +0,35 $) per **+2,05 $**. E' in
utile, ma non smentisce il verdetto: il movimento fino al TP1 e' stato dello 0,241%, appena
sopra i costi, e il risultato lo ha prodotto il **ratchet** incassando in fretta - non il
segnale. E' il meccanismo gia' descritto nelle note 14 e 20.

**Correlazione misurata dalla chat B**: +0,249 su base oraria contro BTC. Bassa, ma **non**
anticorrelata: l'ipotesi avanzata in questo report - che i filtri tarati su BTC potessero
bloccare PAXG proprio nei momenti utili - **non e' confermata dai dati**. La questione e'
comunque irrilevante, dato che l'asset non e' tradabile con questa geometria.

**Scoperta collaterale**: la chat B aveva rilevato che **TRX** sembrava avere lo stesso
difetto ed e' in watchlist perp dal principio. David ha autorizzato uno studio dedicato con
il metodo usato per ZEC (nota 77).

✅ **Esito (27/08): TRX NON va rimossa.** Lo studio ha mostrato che nello stesso setup
(senza filtri, fee circa zero) **tutto il paniere risulta negativo in entrambe le meta'**,
quindi il criterio da solo non discrimina: LINK 0,628, INJ 0,673, XRP 0,476, DOGE 0,513.
L'expectancy di TRX (-0,70/-0,88 $) sta **dentro la banda dei sani** ed e' migliore di XRP e
DOGE; ZEC era invece un outlier vero (-2,83/-3,11 $, circa quattro volte peggio). Sui dati
reali TRX e' **in utile**: +4,39 $ su 10 trade, mentre INJ (-36 $), CAKE (-30 $) e BNB
(-23 $) fanno molto peggio.

> 🔑 **E' questo controllo incrociato ad aver trovato l'errore rettificato sopra.** Applicando
> il criterio alla lettera si sarebbe rimossa anche TRX, ingiustificatamente. Vale come
> promemoria: un criterio che boccia un candidato va provato sui casi che si ritengono sani,
> prima di fidarsene.

Punto d'attenzione, non azione: i TP1 di TRX sono i piu' stretti del paniere (~0,205%),
quindi il margine sui costi reali e' sottile. Da ricontrollare quando il modello dei costi
del backtest sara' finalizzato.
