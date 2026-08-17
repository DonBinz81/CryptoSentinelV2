# Report - Smart SL Rebuy TP Recovery (allineamento upstream)

## COSA È STATO FATTO

- Portato nel fork il fix upstream `e61c0fd` ("Fix Smart SL rebuy TP recovery") della V1,
  assente dal nostro codice perché successivo al commit di fork `3fe9fc8`.
- Aggiunto il metodo `AgentService._adjust_smart_sl_recovery_take_profits()` in
  `backend/app/agent/service.py`, identico all'implementazione upstream.
- Rimosso il blocco inline di ricalcolo TP dal ramo di rebuy globale (`smart_sl_rebuy_all`),
  sostituito dalla chiamata al nuovo metodo.
- Estesa la chiamata anche al ramo di rebuy per livello (`smart_sl_rebuy_l1/l2`), dove il
  ricalcolo dei TP non veniva eseguito affatto.
- Portato il test di regressione upstream con i numeri del caso DOT reale e chiusura TP1
  configurata al 70%.

## COME È STATO FATTO

- Clone in sola lettura di `Iridexx/CryptoSentinelHackathon` (branch `main`) in area
  temporanea, estrazione del diff di `e61c0fd` e confronto riga per riga con il nostro codice.
- Il difetto corretto: la vecchia formula distribuiva il target 40%/60% fra TP1 e TP2, ma
  divideva entrambe le quote per `pos.size / 2`, assumendo implicitamente uscite 50%/50%.
  Con una chiusura TP1 diversa dal 50% i TP generati non coprivano la perdita Smart SL.
- Il nuovo metodo calcola:
  - perdita Smart SL assoluta sommata sui livelli;
  - target netto = perdita x `(1 + perp_smart_sl_tp_recovery_delta_pct / 100)`;
  - target lordo = target netto + fee di apertura - slippage - funding residui, con
    fallback al target netto se il risultato non è positivo;
  - dimensioni reali delle due uscite da `perp_tp1_close_pct`, e ripartizione del target
    lorda con `tp1_target_fraction = min(0.4, tp1_fraction * 0.8)`.
- Guardie di uscita: ricalcolo disabilitato, size non positiva, perdita Smart SL non
  negativa, o una delle due quote di uscita non positiva.

## COSA È STATO VERIFICATO

- Equivalenza col riferimento upstream, per estrazione delle funzioni e `diff`:
  - `_process_smart_sl`: 282 righe, **identica** a quella di `main` upstream;
  - `_adjust_smart_sl_recovery_take_profits`: 62 righe, **identica**.
- Test eseguiti sulla VPS in copia isolata sotto `/tmp` (nessun accesso a `/opt`), con
  l'interprete `/opt/cryptosentinelv2/app/backend/.venv/bin/python` (pytest 8.3.4):
  - test nuovo `test_perp_smart_sl_rebuy_tp_adjustment_uses_actual_tp1_close_pct`: **1 passed**;
  - `backend/tests/unit` baseline da `HEAD` senza modifiche: **204 passed, 2 failed, 1 skipped**;
  - `backend/tests/unit` con il fix: **205 passed, 2 failed, 1 skipped**.
  - Le 2 failure sono **preesistenti e identiche nel baseline**: `test_meta_controller_reduce`
    e `test_agent_service_dry_run_persists_perp_decision_and_trade` (quest'ultimo dipende dai
    dati di mercato reali: il filtro shock BTC blocca l'entry al momento della run).
- Configurazione: `configs/strategy_perp.yaml` non richiede modifiche. Il `git diff` upstream
  `3fe9fc8..main` su quel file è **vuoto**: `e61c0fd` non introduce nuovi default.
- Impatto a runtime: l'ultimo backup delle impostazioni live disponibile
  (`~/backups/settings_prerefactor_20260816_232238.json`, 16/08 23:22 UTC) riporta
  `perp_smart_sl_max_reentries = 0`, quindi il ramo di rebuy non viene eseguito.

## SCOSTAMENTI DAL PIANO

- Nessuno sul codice: il fix è stato portato senza varianti, come richiesto.
- I test non sono eseguibili in locale su questa postazione Windows ARM64: `cryptography`
  non ha wheel per l'architettura e la build da sorgente non completa. Sono stati eseguiti
  sulla VPS in copia isolata sotto `/tmp`, escludendo dal pacchetto `.env`, `secrets/` e
  `configs/instance.yaml`.

## QUESTIONI APERTE

- La configurazione live usa `perp_tp1_close_pct = 50.0`, non `70.0` come la V1 di Marco.
  A quel valore il ricalcolo delle distanze coincide con quello della vecchia formula:
  l'unico effetto residuo del fix è l'inclusione di fee e funding nel target, che allontana
  leggermente i TP. Il fix diventa determinante se la percentuale di chiusura al TP1 viene
  cambiata dall'app.
- Il valore live è letto da un backup del 16/08 23:22 UTC, non dall'API in tempo reale.
- Il ricalcolo dei TP dopo un rebuy per livello è ora attivo: comportamento nuovo per il
  fork, allineato all'upstream, non ancora osservato su trade reali perché il rebuy è spento.
- Nessuna validazione su backtest: il motore di backtest non simula le sequenze Smart SL.

## STATO DELIVERABLE

- Deliverable completato: codice allineato all'upstream, test di regressione presente e
  verde, suite unit senza regressioni.
- Deploy eseguito sulla VPS il 17/08/2026 alle 01:13:54 UTC, con backup del database a
  servizio fermo (`~/backups/pre_smartsl_20260817_011354.db`, `integrity_check` = ok) e
  del codice sostituito. Servizio `active`, loop dell'agente avviati, nessun errore nei
  log successivi al riavvio. Impostazioni live non modificate.
