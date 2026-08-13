# Report fix risk eligible settings

## 1. COSA È STATO FATTO

- Verificato che `RiskManager` riceva la configurazione da `Settings.eligible_tokens`.
- Aggiunto log strutturato quando il risk manager carica l'universo eligible.
- Aggiunto `eligible_token_count` al log `backend_started`.
- Aggiunto conteggio eligible anche in `/api/v1/agent/status` per diagnosi runtime.
- Aggiunto test unitario che dimostra che il risk manager approva un asset presente solo in `Settings.eligible_tokens`.
- Corretto `/api/v1/agent/evaluate` per accettare sia body annidato (`payload.asset`) sia body piatto (`asset` al top-level).
- Corretto il flusso agent: se il signal è già `skip`, il risk manager non lo trasforma in un falso blocco `asset_not_in_eligible_universe`.

## 2. COME È STATO FATTO

- Nessuna lettura diretta di YAML fuori da `backend/app/core/config.py`.
- Il risk manager continua a essere costruito da `AgentService` con la stessa istanza `Settings`.
- Il log `risk_manager_eligible_tokens_loaded` espone solo conteggi, non path o valori sensibili.
- `AgentEvaluateRequest.normalized_payload()` preserva la compatibilità con la chiamata piatta usata nei test manuali.

## 3. COSA È STATO VERIFICATO

- Test mirati Step 6 risk/agent e payload API.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Se il payload non include candele OHLCV, l'esito corretto è `insufficient_ohlcv_history`, non un errore di universo eligible.

## 6. STATO DELIVERABLE

Fix diagnostico implementato e pronto per verifica su backend riavviato.
