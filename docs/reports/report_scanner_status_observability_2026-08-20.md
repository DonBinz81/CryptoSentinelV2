# Report - Osservabilità del ciclo di scansione

Data: 2026-08-20
Branch: `chat-infra/scanner-status`
Perimetro: D — infrastruttura e dati (con estensione autorizzata, vedi SCOSTAMENTI)

---

## COSA È STATO FATTO

David, tramite la chat C: *«il perp è fermo da ieri, non so se sono i filtri o se è la
strategia che non trova edge»*. La stessa domanda valeva per lo spot, e **non era
rispondibile**: quando il motore scarta un asset perché la qualità del segnale è sotto
soglia, l'esito non veniva conservato da nessuna parte.

`slow_tick()` costruiva già il dato giusto (`_scanner_summary()` per ogni asset: azione e
motivo) e lo restituiva a `run_agent_slow_tick()` — ma il chiamante in
`loops/agent.py:34` **scartava il valore di ritorno**. L'unico evento persistito era
`perp_entry_rejected`, che copre solo i due blocchi duri (shock BTC e guardiano rosso), non
il caso ordinario «nessun segnale abbastanza buono».

Aggiunto:

1. **Persistenza** dell'esito di ogni ciclo in `RuntimeState`, chiave `last_scan_cycle`.
2. **Endpoint** `GET /api/v1/views/scanner-status` che l'app legge per mostrare, separati
   per mercato, quando è girato l'ultimo ciclo e come si distribuiscono i motivi.

## COME È STATO FATTO

**Persistenza** — riusato `set_runtime_value()`, lo stesso canale già usato per
`mobile_agent_settings`: nessuna tabella nuova, nessuna migrazione di schema. La scrittura è
in un `try/except` che logga e prosegue: un problema di osservabilità non deve mai fermare
il ciclo di trading.

**Classificazione** — `_classify_scan_reason()` smista ogni esito in cinque secchi:
`entered` / `no_edge` / `filter` / `error` / `other`. È una **lista chiusa** di motivi noti,
non un'euristica sul testo: un motivo non ancora mappato finisce in `other` e **resta
visibile**, invece di essere silenziosamente scambiato per uno dei due che più contano
distinguere. È lo stesso principio dei presidi che «sembrano attivi e non mordono»
(NOTE/49): meglio un dato dichiarato ignoto che un dato inventato.

**Errori per-asset** — gli asset che sollevano un'eccezione non arrivano mai a produrre una
voce in `scanner_results` (escono dal `try` prima), quindi sarebbero invisibili nel
riepilogo. Sono contati direttamente nel ciclo (`spot_scan_errors` / `perp_scan_errors`) e
passati allo snapshot, non dedotti.

**Freschezza** — l'endpoint espone `age_seconds` e `stale`. La soglia è 3 cicli mancati
(`perp_volume_profile_candle_minutes`, default 5m) con minimo 15 minuti: distingue «il ciclo
gira e non trova nulla» da «il ciclo non gira più», che è un problema diverso.

## COSA È STATO VERIFICATO

Test eseguiti **sulla VPS** (in locale impossibile: Windows ARM64), pacchetto senza segreti,
verifica dell'assenza di `.env`/`instance.yaml`/`secrets/` fatta sia nel pacchetto sia nella
destinazione.

| prova | esito |
|---|---|
| Suite intera | **342 passed**, 2 skipped |
| Fallimenti | 2, **verificati preesistenti**: rieseguiti sul codice di `main` intatto, falliscono identici (`test_meta_controller_reduce`, `test_support_ticket_thread_and_admin_status_flow`) |
| `test_scan_cycle_snapshot_tells_no_edge_from_real_block` | ✅ 3 asset, tutti `no_edge`, zero `filter` — il caso di David |
| `test_scan_cycle_snapshot_tells_real_block_from_no_edge` | ✅ 3 `filter` (guardiano rosso) + 1 `error` da eccezione reale |
| `test_scanner_status_endpoint_reports_no_cycle_yet` | ✅ dice esplicitamente che non c'è ancora un ciclo |
| `test_scanner_status_endpoint_flags_stale_snapshot` | ✅ `stale: true` su snapshot vecchio |
| `test_scanner_status_endpoint_fresh_snapshot_not_stale` | ✅ |

I due test sullo snapshot sono costruiti come **coppia speculare**: stesso numero di asset,
stesso esito apparente («il bot non apre»), distribuzioni opposte. È esattamente la
distinzione che prima non esisteva.

## SCOSTAMENTI DAL PIANO

**Estensione di perimetro, autorizzata**. Questa chat (D) ha per perimetro
`backend/app/persistence/**`, `configs/**`, script di sistema e `.env`. Il lavoro tocca
anche `backend/app/agent/service.py` (aggancio nel ciclo) e
`backend/app/api/routes/views.py` (endpoint di lettura), che ricadono sotto «logica di
strategia» e «interfaccia dell'app». Fermato il lavoro e chiesta decisione a David, che ha
**autorizzato esplicitamente** di procedere da qui, per non spezzare un cambiamento coerente
su due chat.

**Non toccata la logica di quality/skip**, come indicato dalla chat C: nessuna soglia,
nessun filtro, nessuna decisione di trading è cambiata. Il comportamento del bot è
identico — cambia solo cosa lascia scritto dietro di sé.

`loops/agent.py` **non è stato modificato**: la scrittura avviene dentro `slow_tick()`, dove
il dato nasce. Agganciarla al chiamante avrebbe funzionato allo stesso modo, ma avrebbe
lasciato la persistenza scoperta per ogni altro invocatore di `slow_tick()` (i test, e
l'endpoint manuale di scansione).

## QUESTIONI APERTE

1. **Solo l'ultimo ciclo**, nessuno storico. Sufficiente per la domanda posta («adesso cosa
   sta facendo?»); una serie storica richiederebbe una tabella e una politica di
   retention — da valutare se emergesse la necessità di analizzare l'andamento nel tempo.
2. **La parte app non è fatta**: l'endpoint espone il dato, ma mostrarlo in interfaccia è
   perimetro C.
3. `_SCAN_*_REASONS` va tenuto allineato se si aggiungono nuovi motivi di skip. Un motivo
   nuovo non mappato non si perde (finisce in `other` con il suo nome), ma va spostato nel
   secchio giusto perché il riepilogo resti leggibile.

## STATO DELIVERABLE

- `backend/app/agent/service.py` — `_build_scan_cycle_snapshot()`, `_classify_scan_reason()`,
  scrittura in `RuntimeState` a fine ciclo, conteggio errori per mercato.
- `backend/app/api/routes/views.py` — `GET /api/v1/views/scanner-status`.
- `backend/tests/unit/test_agent_step6.py` — 5 test nuovi.
- Commitato su `chat-infra/scanner-status`. **Non deployato, non mergiato**: in attesa
  dell'ok esplicito (regola fissa del resume).
