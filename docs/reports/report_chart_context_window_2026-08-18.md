# Report - Contesto candele del grafico posizione: 24h prima dell'apertura, fino a 24h dopo la chiusura

Data: 2026-08-18
Branch: `chat-infra/chart-context` (da `main` `a51233b`) — **non deployato, non su main**:
merge unico coordinato dal proprietario insieme al grafico `lightweight-charts` (nota 57).

---

## COSA È STATO FATTO

Richiesta: il grafico della posizione deve poter mostrare fino a **24 ore prima
dell'apertura** e fino a **24 ore dopo la chiusura** (288 candele a 5m per lato).

Tre modifiche, con i **default invariati** come da sequenza anti-regressione:

1. **Nuovo parametro `chart_pre_open_candles`** (default 20, range 1-288): governa solo la
   finestra grafica. Prima il grafico riusava `structural_stop_lookback_candles`, che esiste
   per calcolare lo stop strutturale: allargare la vista avrebbe spostato anche il
   riferimento dello stop. Le due finestre sono ora separate.
2. **Cap del fetch pre-apertura da 260 a 620** candele (288 pre + candele del trade +
   margine). Binance serve fino a 1000 klines per richiesta: anche la finestra massima
   resta una singola chiamata.
3. **`post_close_candles`: massimo da 50 a 288**, default 10 invariato (si alza dal Setup).

Corretto anche il docstring obsoleto di `_fetch_post_close_candles`: diceva «funziona per
trade chiusi di recente», ma la funzione usa `start_time` dalla chiusura (recupero per
intervallo) e regge trade chiusi da giorni. Documentazione aggiornata, codice intatto.

## COME È STATO FATTO

| file | modifica |
|---|---|
| `configs/risk.yaml` | `chart_pre_open_candles: 20` con commento (default nei YAML, regola AGENTS.md) |
| `backend/app/core/config.py` | campo `chart_pre_open_candles` + mappatura YAML→Settings |
| `backend/app/schemas/mobile_agent.py` | `post_close_candles` `le=50`→`le=288`; nuovo `chart_pre_open_candles` (1-288, default 20) |
| `backend/app/agent/service.py` | il default runtime del nuovo campo viene dai Settings |
| `backend/app/api/routes/views.py` | `_enrich_trade_chart_context` accetta `pre_open_candles`; cap 260→620; i chiamanti passano il valore dalle mobile settings; docstring post-close corretto |

Il parametro segue lo stesso percorso runtime di `post_close_candles`: YAML → Settings →
default delle mobile settings → override dall'app via API settings. L'esposizione nel
pannello Setup **non è di questo lavoro** (perimetro C, fotografia meccanica obbligatoria).

Retrocompatibilità: `pre_open_candles=None` fa ricadere sul lookback dello stop, cioè il
comportamento identico a prima — è anche il caso coperto dal secondo test nuovo.

## COSA È STATO VERIFICATO

Suite completa su VPS in copia isolata (`/tmp/cc2`, interprete di produzione):

```
prima delle modifiche   295 passed, 2 failed (preesistenti), 2 skipped
dopo, con i 4 test nuovi  299 passed, 2 failed (stessi), 2 skipped
```

Test nuovi:

1. finestra 288 **indipendente** dal lookback dello stop: il grafico arriva a 24h ma
   `stop_reference.pre_candles` resta 20; il limit supera il vecchio cap di 260;
2. senza parametro esplicito il comportamento è identico a prima (start = 20 candele);
3. post-close su un **trade chiuso 18 giorni prima**: il fetch parte da `closed_at`,
   288 candele recuperate — il recupero per intervallo non dipende da quanto è recente;
4. gli schemi accettano 288 e rifiutano 289 e 0; default 10/20 confermati.

Misura su **trade reale** (BTC, chiuso 18/08 18:30), timeout `feed 1.5s / chart 4.0s`:

```
pre=20  post=10   →  0,31 s totali | payload  4,0 KB
pre=288 post=288  →  0,56 s totali | payload 28,4 KB
```

Ampiamente nei timeout: nessun allargamento necessario. Payload sotto la stima dei 45-50 KB.
Le sole 14 candele post ottenute sono corrette: il trade era chiuso da ~1h20, più candele
non esistono ancora.

## SCOSTAMENTI DAL PIANO

Nessuno. Le direttive della nota 57 corrispondevano al codice reale; l'unica precisazione:
`post_close_candles` non aveva un default nei YAML (è cablato nello schema mobile e in
`service.py:223`), quindi il nuovo parametro è stato messo in `risk.yaml` seguendo il
percorso dei parametri globali esistenti, e il suo default runtime legge dai Settings.

## QUESTIONI APERTE

1. **Esposizione nel Setup dell'app**: perimetro C (chat del grafico), con fotografia
   meccanica del pannello.
2. **Deploy**: da fare **solo nel merge unico** con il grafico; i default invariati lo
   renderebbero sicuro anche prima, ma la sequenza concordata prevale.
3. La misura post-close a 288 piene su un trade vecchio è coperta dal test con feed finto;
   sulla rete reale è stata misurata con le 14 candele disponibili. Da rimisurare su un
   trade più vecchio quando ce ne sarà uno con 24h di storia post-chiusura.

## STATO DELIVERABLE

- Codice completo sul branch `chat-infra/chart-context`, test verdi, misure fatte.
- Non deployato, non su `main`: in attesa del merge unico coordinato dal proprietario.
