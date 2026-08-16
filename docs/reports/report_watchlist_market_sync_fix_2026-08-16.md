# Report - Fix watchlist di mercato non salvabili

Data: 2026-08-16

---

## COSA È STATO FATTO

Risolto il bug per cui l'app mostrava "Errore salvataggio watchlist" a ogni
toggle di una coin nelle sotto-schede Spot e Perp, rendendo le watchlist di
mercato non modificabili.

Il difetto e' **ereditato dall'upstream** (`Iridexx/CryptoSentinelHackathon`,
commit `3fe9fc8`): `backend/app/agent/watchlist.py` era byte-identico e il
`catch` muto e' presente anche in `src/components/AgentTab.tsx` upstream.

## COME È STATO FATTO

Causa: **asimmetria fra lettura e scrittura** delle watchlist di mercato.

| | funzione | filtro applicato |
|---|---|---|
| Lettura | `_load_symbols` | solo `eligible_tokens` |
| Scrittura | `set_market_watchlist` | deve stare nella **master** |

Restringendo la master, la lista spot/perp persistita conservava simboli orfani;
il client la rileggeva e la rispediva intera al primo toggle, ottenendo 400 su
qualsiasi coin.

Modifiche:

- `backend/app/agent/watchlist.py`
  - `_load_symbols` accetta `restrict_to`: le letture di spot/perp filtrano anche
    sulla master, cosi' cio' che il client rilegge e' sempre ri-salvabile.
  - nuova `_prune_market_watchlists()`: la PUT della master pota spot e perp dai
    simboli non piu' presenti.
  - `set_market_watchlist` elenca **tutti** i simboli fuori master, non solo il primo.
- `src/components/AgentTab.tsx`: il `catch` mostra il messaggio del backend invece
  di sostituirlo con un testo generico.
- `backend/tests/unit/test_watchlist_market_sync.py`: 4 test di regressione.

## COSA È STATO VERIFICATO

- **Controprova**: i 4 test falliscono tutti sul codice precedente e passano tutti
  sul fix.
- Suite `backend/tests/unit`: 200 passed, 1 skipped, 2 failed. Le 2 failure sono
  **preesistenti e non correlate**, verificate eseguendole sul codice originale:
  `test_meta_controller_reduce`, `test_execution_guardrails_cannot_be_relaxed`.
- Verifica end-to-end su ambiente live via HTTPS:
  - rilettura e reinvio della lista spot (il ciclo che falliva): **200**
  - toggle perp con rimozione e reinserimento di NEAR: **200** / **200**
  - simbolo fuori master forzato: **400** con messaggio leggibile
    (`Assets not in the master watchlist: SUI, TRX`)
- Stato finale watchlist: master 16, perp 16, spot 11.

## SCOSTAMENTI DAL PIANO

- Test eseguiti con il virtualenv della VPS (`/opt/cryptosentinelv2/app/backend/.venv`)
  anziche' `backend\.venv\Scripts\python.exe`: **quel venv non esiste su questa
  workstation**. Copia del repo in `/tmp` per non toccare la produzione durante i test.
- Su decisione dell'utente, le 7 coin presenti solo nella spot e fuori master
  (TRX, ZEC, TON, SHIB, ETC, ASTER, CAKE) sono state rimosse anziche' allargare
  la master.

## QUESTIONI APERTE

- **Bug latente non risolto**: deselezionando *tutte* le coin di un mercato, la
  lista risulta vuota e `selected_*_watchlist` ricade sulla master. Non e'
  possibile avere una watchlist di mercato vuota.
- Le 2 failure preesistenti della suite unit restano aperte.
- Il fix e' trasferibile alla V1 upstream (patch autosufficiente); la
  segnalazione e' stata preparata ma l'invio spetta all'utente.

## STATO DELIVERABLE

**Completato.** Deployato in produzione, commit `39cb2ef` pushato su
`DonBinz81/CryptoSentinelV2`. Backend riavviato e verificato.
