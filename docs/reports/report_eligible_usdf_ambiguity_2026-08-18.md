# Report - Due monete, un ticker: `USDF` sostituita con `SUI` nell'universo eligible

Data: 2026-08-18

---

## COSA È STATO FATTO

`configs/eligible_tokens.yaml` conteneva **150 voci ma 149 simboli unici**: le entry `USDf`
(riga 100) e `USDF` (riga 112) collassavano una volta normalizzate in maiuscolo, come si
vedeva a ogni avvio nel log `risk_manager_eligible_tokens_loaded`
(`eligible_token_count: 150, eligible_symbol_count: 149`).

Non era un errore di battitura: sono **due monete diverse che condividono il ticker**.

| | Falcon USD (`USDf`) | Aster USDF (`USDF`) |
|---|---|---|
| slug | `falcon-finance` | `astherus-usdf` |
| rank | 54 | 229 |
| prezzo | 0,996 $ | 0,998 $ |
| capitalizzazione | 1,34 mld | 112 mln |
| volume 24h | 308.619 $ | **18.421 $** |
| indirizzo in `SPOT_TOKEN_MAP` | assente | assente |
| pair perp su Aster | non quotato | **non quotato** |

Rimossa `USDF` (Aster USDF) e aggiunta **`SUI`** (rank 34, 2,67 mld di capitalizzazione,
248 M di volume giornaliero, `TRADING` su Aster). Conteggio invariato a 150, e ora i simboli
unici sono **150**.

## COME È STATO FATTO

Il difetto vero non era il conteggio, era l'**ambiguità**: `risk/manager.py:55` costruisce
`eligible_symbols` come insieme di simboli in maiuscolo, e la riga 91 verifica
`intent.asset.upper() not in self.eligible_symbols`. Quindi il guardrail non bloccava nessuna
delle due — **le trattava come lo stesso simbolo**. È la stessa famiglia di rischio della
nota 48, dove il ticker `BTC` risolveva a un token estraneo: un ticker non è un
identificatore.

Identificazione fatta **per slug** e non per ticker, con dati di mercato reali: la ricerca su
ticker `USDF` restituisce otto risultati distinti, fra cui le due monete in questione.

Criterio della scelta:

- **quale rimuovere**: quella meno utile delle due. Aster USDF ha 18.421 $ di volume
  giornaliero ed è una stablecoin ancorata a 1,00 — per una strategia mean-reversion non
  produrrebbe che fee, lo stesso motivo per cui `U` (United Stables) è stata esclusa dalla
  watchlist (nota 49 §8). Da notare che **non è quotata nemmeno da Aster**, la sua stessa
  venue;
- **quale aggiungere**: fra le candidate liquide assenti dall'universo e verificate
  `TRADING` su Aster (SUI, WLD, ARB, APT, TIA, SEI, OP), `SUI` è la più liquida di un ordine
  di grandezza sul volume;
- **cosa lasciare**: `USDf` (Falcon USD) resta. Non è tradabile qui, ma è una voce legittima
  della lista della competizione e ora non è più ambigua.

Aggiornati, come impone la regola stessa, il commento in testa al YAML e `AGENTS.md`, dove è
stato aggiunto il vincolo di **unicità dopo normalizzazione** — che prima non era scritto da
nessuna parte, ed è la ragione per cui il difetto è passato inosservato.

## COSA È STATO VERIFICATO

| verifica | esito |
|---|---|
| Voci nel file | **150** |
| Simboli unici dopo normalizzazione | **150** (erano 149) |
| Duplicati residui | **nessuno** |
| `SUI` non già presente prima della modifica | confermato |
| `SUI` quotata su Aster | `SUIUSDT` **TRADING** (su 553 pair) |
| `USDF` su Aster | non quotato — confermato che la rimozione non toglie nulla di operativo |
| Deploy | hash identici fra repo e produzione |
| Guardrail all'avvio | `eligible_token_count: 150`, `eligible_symbol_count: 150` |
| Servizio dopo il riavvio | `active`, `health/live` 200, zero errori |

## SCOSTAMENTI DAL PIANO

Nessuno. La proposta iniziale prevedeva anche l'ipotesi di rimuovere entrambe le stablecoin:
scartata dal proprietario del repository in favore della sostituzione singola, che mantiene
la divergenza dall'upstream al minimo.

## QUESTIONI APERTE

1. `USDf` (Falcon USD) resta nell'universo ma **non è tradabile**: nessun indirizzo in mappa
   e nessun pair su Aster. Non è un difetto — l'universo della competizione non coincide con
   ciò che le nostre venue eseguono — ma vale sapere che occupa un posto inerte. Lo stesso
   valeva per `USDF` prima di questa modifica.
2. La verifica «tutte le entry sono tradabili su almeno una venue» **non esiste come
   controllo automatico**. Oggi si fa a mano; sarebbe un buon presidio, sul modello della
   disponibilità per venue già esposta nel setup.
3. `SUI` è ora nell'universo ma **non in watchlist**: perché venga trattata va selezionata
   dall'app. È una scelta del proprietario, non fatta d'iniziativa.

## STATO DELIVERABLE

- `configs/eligible_tokens.yaml` — modificato, deployato, verificato per hash.
- `AGENTS.md` — aggiunto il vincolo di unicità dopo normalizzazione.
- Documentazione: questo report; nota di archivio aggiornata.
