# Report fix eligible tokens validator

## 1. COSA È STATO FATTO

- Aggiornato il validator `Settings.eligible_tokens` per deduplicare automaticamente i simboli preservando ordine e case.
- Confermato che il validator accetta qualsiasi stringa non vuota come simbolo, inclusi Unicode e mixed-case.
- Aggiunti test unitari dedicati per deduplica, simboli speciali e conteggio hard dopo la deduplica.

## 2. COME È STATO FATTO

- La normalizzazione avviene solo in `backend/app/core/config.py`, mantenendo il loader unico `Settings`.
- La deduplica usa l'ordine di comparsa originale e non trasforma mai il case, perché simboli come `USDf` e `USDF` possono essere distinti.
- Il guardrail resta fail-closed ma non usa piu' un conteggio fisso: dopo deduplica devono esserci tra 100 e 200 token unici.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_config_eligible_tokens.py -q`
- Esito: `3 passed`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno lato validator.
- La lista ufficiale ricevuta contiene 149 righe ma 148 simboli unici perché `SLX` è duplicato; su richiesta operativa è stato rimosso il duplicato e il guardrail è stato reso elastico tra 100 e 200 token unici.

## 5. QUESTIONI APERTE

- Se gli organizzatori correggono la lista ufficiale, aggiornare solo `configs/eligible_tokens.yaml` finché resta nell'intervallo 100-200.

## 6. STATO DELIVERABLE

Validator corretto e testato. Lista configurata a 148 token unici dopo rimozione del duplicato, valida nel range 100-200.
