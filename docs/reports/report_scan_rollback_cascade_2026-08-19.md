# Report - Fix upstream: la sessione del ciclo di scansione va riportata in salute dopo un errore

Data: 2026-08-19
Branch: `chat-infra/rollback-scan-session` (da `main`)

**Attribuzione: il fix è di Marco**, V1 upstream `Iridexx/CryptoSentinelHackathon`,
commit `9504142` «Fix agent scan rollback cascade» (19/08/2026). Qui è stato portato nel
fork, adattato al nostro ciclo, verificato e coperto da un test. Il repo upstream si legge
soltanto: nessun push da parte nostra.

---

## COSA È STATO FATTO

Portata la funzione `_rollback_failed_scan_session` e la sua chiamata come prima istruzione
nei due `except` per-asset del ciclo di scansione (`slow_tick`), uno per lo spot e uno per
il perp.

Il difetto che corregge: il nostro ciclo aveva già un `try/except` per asset e **sembrava
protetto**, ma non lo era. Quando un flush ORM fallisce, la sessione `AsyncSession` resta in
stato *pending rollback*: ogni asset scansionato dopo quello rotto muore con
`PendingRollbackError`. Un solo asset che esplode fa saltare l'intero ciclo, anche per gli
asset sani.

È il meccanismo che in `NOTE/36` ci è costato ore di diagnosi sbagliata: il bot non apriva
più, la colpa è stata data ai filtri di segnale, e la causa vera era un `INSERT` fallito su
`agent_decisions` che avvelenava la sessione condivisa. Allora abbiamo curato il sintomo (il
database corrotto). **Marco ha corretto la causa.**

## COME È STATO FATTO

Il punto di innesto è equivalente al suo, pur non coincidendo le righe: il nostro
`slow_tick` scorre due liste separate (`spot_assets`, `perp_assets`) con un `except` ciascuno,
e `run_agent_slow_tick` apre **una sola sessione per l'intero ciclo** — quindi la condizione
di cascata è identica.

```python
except Exception as exc:
    await _rollback_failed_scan_session(session)   # <- prima istruzione, come da upstream
    scan_errors.append(str(exc))
    logger.warning("scanner_perp_asset_error", asset=asset, error=str(exc))
```

## COSA È STATO VERIFICATO

### La cascata esiste davvero, e solo in un caso preciso

Prima di scrivere il test ho misurato **quando** la sessione si avvelena, con una prova
empirica sul nostro stack (SQLite + aiosqlite + SQLAlchemy async):

| scenario | senza rollback, l'operazione successiva |
|---|---|
| eccezione Python semplice (`RuntimeError`) | **funziona** — nessuna cascata |
| `SELECT` su tabella inesistente | **funziona** — nessuna cascata |
| `INSERT` testuale invalido, anche dopo una scrittura valida | **funziona** — nessuna cascata |
| **flush ORM fallito** (chiave duplicata, come l'`INSERT` di `agent_decisions`) | **`PendingRollbackError`** — cascata |

Con il rollback, l'ultimo caso torna a funzionare. **Il fix è quindi necessario ed efficace**,
ma si innesca solo sul flush ORM: è il dettaglio che rende il test facile da scrivere male.

### Il test, e perché la prima stesura era da buttare

La prima versione del test simulava il guasto con un `RuntimeError` e verificava che il
rollback fosse stato chiamato. **Passava anche senza il fix**: era tautologica — misurava la
propria chiamata, non l'effetto. Riscritta usando un flush ORM fallito (chiave duplicata) e
verificando che gli asset successivi **arrivino davvero al database**:

| | esito |
|---|---|
| con il fix | ✅ passa |
| **senza il fix** (rollback disabilitato) | ❌ fallisce su `assert persisted == ["BBB", "CCC"]` → `assert [] == ['BBB', 'CCC']` |

Cioè, senza il fix, **nessuno** degli asset sani successivi riesce a scrivere. La cascata è
dimostrata, non asserita.

### Suite completa

```
337 passed, 2 failed (preesistenti: test_meta_controller_reduce,
                      test_support_ticket_thread_and_admin_status_flow), 2 skipped
```

## SCOSTAMENTI DAL PIANO

Nessuno sul contenuto del fix, che è stato portato così com'è. Due scostamenti di metodo,
entrambi in più rispetto a quanto chiesto:

1. è stata aggiunta la **prova empirica** su quando la sessione si avvelena, perché senza
   quella non era possibile scrivere un test che dimostrasse qualcosa;
2. il primo test è stato **riscritto da capo** dopo aver verificato che passava anche senza
   il fix.

## QUESTIONI APERTE

**Risposta alla domanda «il rollback annulla anche scritture valide fatte prima?»: no, e il
compromesso è più piccolo di quanto temuto.** Nel nostro codice ogni scrittura viene
committata appena fatta — `AgentDecisionRepository.save()` esegue `add()` + `commit()` per
ogni decisione, e lo stesso vale per le aperture di posizione. Quando il rollback scatta, il
lavoro valido degli asset precedenti è **già persistito**: viene scartato solo lo stato a
metà dell'asset che è appena fallito, che è incoerente e va scartato comunque.

Resta un caso teorico: se in futuro qualcuno accumulasse più scritture in una sola
transazione senza commit intermedi, il rollback ne annullerebbe l'insieme. Vale la pena
saperlo prima di riorganizzare la persistenza del ciclo.

Nota per l'upstream: se la V1 committa allo stesso modo, vale lo stesso ragionamento.

## STATO DELIVERABLE

- `backend/app/agent/service.py` — funzione portata + innesto nei due `except`, con
  attribuzione a Marco nel docstring.
- `backend/tests/unit/test_agent_step6.py` — test di regressione che riproduce la cascata
  reale e fallisce se il fix viene rimosso.
- Non deployato: in attesa di decisione sul merge.
