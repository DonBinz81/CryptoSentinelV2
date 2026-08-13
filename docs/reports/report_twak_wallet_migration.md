# Report Migrazione Wallet TWAK + Fix Bloccanti

## 1. COSA È STATO FATTO

- Segnato il blocco TWAK 403 come risolto nel piano: causa legata ad account/wallet specifico, soluzione con nuova API key, nuovo wallet e reinit TWAK.
- Aggiunto helper `backend/scripts/select_twak_wallet.py` per selezionare in RuntimeState il nuovo wallet pubblico TWAK `0xDF27d02a536F1AaAF16a25D5E76DA50d716EAfeB`.
- Allineato `ExecutionService` alle settings effettive runtime per wallet, network, registry TWAK/PancakeSwap e x402.
- Corretto `/api/v1/execution/status`: su mainnet espone `chain: bsc` e `testnet_only: false`.
- Corretto lo status provider TWAK/PancakeSwap: `chain`, `domain` e `testnet_only_execution` riflettono la rete effettiva.
- Allineato `twak_chain` runtime: `bsc` su mainnet, `bsctestnet` su testnet.
- Corretto default domain negli script TWAK route probe/smoke: `smartchain` su mainnet, `smartchain-testnet` su testnet.
- Aggiunto `scripts/twak-password-file.cjs` per leggere password TWAK da file UTF-8 ed evitare problemi encoding PowerShell con caratteri non-ASCII.
- Aggiunto `TWAK_WALLET_PASSWORD=` a `.env.example` con valore vuoto.
- Documentato in `backend/README.md` il workaround password/keychain e il comando per selezionare il nuovo wallet runtime.
- Chiuso il debito test HMAC TWAK: i test ora validano il formato SDK attuale usato dal signer.
- Aggiunta migrazione automatica wallet: se il vecchio wallet TWAK compare in config/RuntimeState, viene escluso e sostituito dal nuovo wallet operativo.

## 2. COME È STATO FATTO

- Non è stato letto, stampato o modificato `.env`.
- Le credenziali reali TWAK devono essere aggiornate manualmente nel `.env` locale dall'utente.
- Il nuovo wallet è gestito come indirizzo pubblico: può essere salvato in RuntimeState senza esporre materiale privato.
- `effective_execution_settings()` ora applica anche `twak_chain`, così dashboard e CLI TWAK usano la stessa rete logica.
- Gli script operativi derivano il domain TWAK dalla rete configurata invece di usare sempre `smartchain-testnet`.

## 3. COSA È STATO VERIFICATO

- Verificato localmente che la CLI TWAK `0.19.1` non supporta `--password-file`.
- Verificato che `twak wallet address --help` e `twak compete register --help` espongono solo `--password`, keychain o `TWAK_WALLET_PASSWORD`.
- Verificato il wrapper Node con comando help, senza password reale:
  - `node scripts/twak-password-file.cjs --password-file scripts/twak-password-file.cjs -- wallet address --help`
- Aggiunto test unitario per status mainnet execution provider.
- `backend\.venv\Scripts\python.exe -m py_compile backend/app/execution/service.py backend/app/execution/network_selection.py backend/app/execution/providers/twak_provider.py backend/app/execution/providers/pancakeswap_provider.py backend/scripts/select_twak_wallet.py backend/scripts/twak_rpc_route_probe.py backend/scripts/test_spot_swap.py backend/tests/unit/test_execution_wallets.py` completato con successo.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_execution_wallets.py backend/tests/unit/test_execution_providers.py backend/tests/unit/test_execution_layer.py backend/tests/integration/test_execution_api.py -q` completato con `35 passed`.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests -q` completato con `124 passed`.

## 4. SCOSTAMENTI DAL PIANO

- `.env` non è stato aggiornato dall'agente per regole di sicurezza repository. L'utente deve impostare manualmente `TWAK_ACCESS_ID`, `TWAK_HMAC_SECRET`, wallet address e password se necessaria.
- Il comando reale `backend/scripts/twak_rpc_route_probe.py` non è stato eseguito dall'agente perché richiede credenziali TWAK e config locale sensibile.
- La selezione RuntimeState del wallet non è stata eseguita dall'agente; è stato predisposto lo script esplicito da lanciare localmente.

## 5. QUESTIONI APERTE

- Eseguire localmente:
  - `backend\.venv\Scripts\python.exe backend\scripts\select_twak_wallet.py`
  - riavviare backend
  - verificare `GET /api/v1/execution/wallets`
  - verificare `GET /api/v1/execution/status`
- Eseguire quote-only TWAK route probe con nuovo wallet e token reali.
- Confermare se l'esecuzione live mainnet deve restare gated o essere abilitata solo in Step 10/deploy.

## 6. VERIFICHE TECNICHE

| Verifica | Esito |
|---|---|
| TWAK 403 root cause | Risolto manualmente con nuovo wallet/API key |
| Password-file TWAK CLI | CLI non supporta flag nativo; wrapper Node predisposto |
| Mainnet chain status | Fix implementato e testato con unit test |
| Gas floor `0.000005` | Già presente in `configs/risk.yaml`, fixture test allineati |
| Warm-up OHLCV | Già implementato nel commit precedente |
| `.env` update | Manuale, non eseguito dall'agente |
| HMAC TWAK tests | Aggiornati al formato SDK attuale; passano |
| Full backend suite | 124 passed |

## 7. STATO DELIVERABLE

Migrazione predisposta lato codice, documentazione e helper. Restano da eseguire localmente le operazioni che richiedono `.env`, backend avviato e credenziali reali.
