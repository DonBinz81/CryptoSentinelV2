# REPORT STEP 4 - LAYER DI ESECUZIONE

## 1. COSA È STATO FATTO

- Creati due percorsi distinti: spot tramite Trust Wallet Agent Kit e perpetual tramite BNB Agent SDK/EIP-712.
- Implementato client JSON-RPC BSC con fallback tra endpoint configurati.
- Implementati riserva gas hard del 15%, floor minimo BNB e blocco trade quando il gas stimato non è inferiore al profitto atteso.
- Implementata policy ERC-20 con spender in whitelist e approval esatta.
- Implementati retry limitati, riconciliazione ricevuta on-chain e stato `unknown` senza reinvio dopo un hash noto.
- Implementato provider wallet basato su keystore Web3 cifrato e policy BNB SDK per typed data.
- Integrati ERC-8004 identity ed ERC-8183 commerce dal pacchetto `bnbagent`.
- Implementato x402 BSC con EIP-3009, budget per chiamata/giornaliero e fallback tra servizi configurati.
- Implementata registrazione TWAK e verifica diretta `isRegistered(address)` sul contratto competizione.
- Aggiunti endpoint protetti di stato execution e competizione.
- Aggiunto `backend/scripts/encrypt_wallet.py` per creare interattivamente il keystore Web3 cifrato senza private key su CLI o disco in chiaro.
- Aggiunto `backend/scripts/test_spot_swap.py` per verificare TWAK, gas guard e ricevuta on-chain con uno swap BSC testnet.
- Aggiunta diagnostica strutturata per fase allo smoke test e dettaglio TWAK sanitizzato; verificato che TWAK `0.19.1` usa un RPC testnet interno non sovrascrivibile dal comando `swap`.
- Aggiunto supporto RPC Tatum autenticato: `x-api-key` viene iniettato solo per host `tatum.io`, con PublicNode e RPC BNB Chain come testnet default.
- La stima gas usa `gas_limit` conservativo per gas price RPC perché TWAK non espone calldata unsigned prima dell'esecuzione; modalità ed errori RPC sono loggati.
- Spot REST: quote e route-step sono stati spostati su Amber API (`domains`, `providers`, `route`, `route/step`). Il CLI resta per wallet address e competizione. La REST API prepara transazioni unsigned; non sostituisce da sola firma e broadcast.

## 2. COME È STATO FATTO

- Il layer usa `Settings` come unico punto di configurazione. RPC, timeout, retry, conferme, whitelist e provider x402 sono in `configs/instance.example.yaml`.
- Lo spot invoca il CLI ufficiale TWAK `0.19.1`; il subprocess riceve solo variabili OS essenziali e credenziali esplicite, senza argomenti sensibili.
- Dal codice ufficiale TWAK è stato verificato che lo swap controlla l'allowance e approva l'importo richiesto. L'approval illimitata del comando ERC-20 richiede conferma esplicita.
- Per x402 è stato scelto EIP-3009 senza `--auto-approve`, evitando il percorso Permit2 che può richiedere approval iniziale illimitata.
- La whitelist contiene il PancakeSwap V2 Router ufficiale BSC Testnet `0xD99D1c33F9fC3444f8101754aBC46c52416550D1`.
- Il percorso perp valida chain ID 97 e verifying contract EIP-712 prima della firma. L'invio è fail-closed finché non sono configurati endpoint e contratto di una venue perpetual testnet ufficiale.
- `bnbagent 0.3.6` espone ERC-8004, ERC-8183, wallet/signing policy e x402. Non espone un modulo memory pubblico dedicato; non è stato simulato.
- La registrazione competizione è separata dal trading testnet perché il contratto ufficiale è su BSC mainnet.
- Fonti ufficiali consultate: [TWAK](https://github.com/trustwallet/twak), [BNB Agent SDK](https://github.com/bnb-chain/bnbagent-sdk), [PancakeSwap V2 addresses](https://developer.pancakeswap.finance/contracts/v2/addresses).

## 3. COSA È STATO VERIFICATO

- `ruff check backend/app backend/tests`: superato.
- `compileall backend/app backend/tests`: superato.
- Suite backend completa: `42 passed, 1 skipped`.
- Test Step 4: guardrail config, approval esatta, riserva gas, RPC fallback, firma EIP-712, limiti TWAK, conferme on-chain, retry, budget x402 e API execution.
- Import e API di `bnbagent 0.3.6`: verificati nel virtualenv backend.
- CLI TWAK `0.19.1`: verificati versione e comandi `swap`, `compete` e `x402`.
- Autenticazione REST TWAK: formato HMAC-SHA256 verificato sul sorgente ufficiale TWAK `dist/index.js` e sulle Agent Skills installate. Il formato corretto è `METHOD;PATH;SORTED_QUERY;ACCESS_ID;NONCE;DATE` con data RFC 2822. Il codice in `spot_twak/client.py` è allineato; il profilo doppio rimosso. Il 403 ottenuto durante il test manuale è causato dal piano Free di `portal.trustwallet.com` che non include gli endpoint autenticati `tws.trustwallet.com`; non è un errore di firma.
- Pydantic-settings: corretto il bug per cui `TWAK_CLI_PATH=` e `TWAK_API_BASE_URL=` vuoti nel `.env` sovrascrivevano i default di `Field`. Aggiunti `field_validator` con `mode="before"` che ripristinano i default `"twak"` e `"https://tws.trustwallet.com"`.
- Trust Wallet Agent Skills installate in `.claude/skills/` tramite `npx skills add trustwallet/tw-agent-skills`. Le skill sono file markdown di documentazione per agenti AI, non un layer API separato.
- Wallet agente creato con `twak wallet create` e keystore Web3 cifrato generato con `encrypt_wallet.py`.
- RPC read-only: BSC Testnet chain ID 97, BSC Mainnet chain ID 56 e bytecode presente sul contratto competizione.
- Verificati live i tre RPC pubblici testnet versionati: PublicNode e due endpoint BNB Chain hanno restituito chain ID `0x61` (97).
- Smoke test `test_spot_swap.py` eseguito su BSC testnet: TWAK CLI raggiungibile, gas guard attivo, RPC fallback funzionante. Lo swap reale non ha prodotto ricevuta on-chain perché l'Amber API richiede piano a pagamento per il quote.
- Verificato automaticamente che lo script wallet produca materiale cifrato e azzeri il buffer mutabile della chiave.

## 4. SCOSTAMENTI DAL PIANO

- Nessuna venue perpetual BSC testnet ufficiale era definita nel piano. È stato implementato il boundary BNB SDK/EIP-712 e l'adapter di submission configurabile, ma non è stato inventato un protocollo.
- AgentData non è stato confermato come servizio BSC/x402 disponibile per i token richiesti. È supportato come endpoint configurabile con fallback, disabilitato per default.
- Il budget x402 giornaliero è in memoria. La persistenza affidabile appartiene allo Step 5.
- Il quote TWAK espone il provider PancakeSwap ma non garantisce documentalmente il pinning atomico del router tra quote ed execution; il limite resta documentato.

## 5. QUESTIONI APERTE

- **Amber API (spot quote)**: il piano Free di `portal.trustwallet.com` restituisce 403 sugli endpoint `tws.trustwallet.com`. Lo swap spot reale richiede piano a pagamento o accesso speciale da organizzatori hackathon. Il codice di firma è corretto e pronto.
- **Venue perpetual**: nessuna venue perpetual ufficiale su BSC testnet è stata identificata. Il bridge BNB SDK/EIP-712 è implementato e configurabile; l'invio è fail-closed finché il verifying contract e l'endpoint non sono noti.
- **Registrazione competizione**: da eseguire con `twak compete register` su BSC mainnet quando la finestra di registrazione è aperta (22-28 giugno 2026); verificare poi transazione BscScan e `isRegistered`.
- **AgentData/x402**: disponibilità, rete e token supportati da confermare prima di abilitare il provider.
- **`configs/instance.yaml` locale**: aggiornare con contratto competizione ufficiale e `x402.network: bsc`.

## 6. STATO DELIVERABLE

**PARZIALE.**

Il layer, i guardrail, gli adapter e i test automatici sono implementati. Il deliverable non può essere dichiarato raggiunto finché non vengono completati uno swap spot reale su BSC testnet, un ordine perp reale su una venue ufficiale configurata e la verifica della registrazione competizione con il wallet operativo.
