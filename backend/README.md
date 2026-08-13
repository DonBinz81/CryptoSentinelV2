# CryptoSentinel Backend

FastAPI backend for the BNB Hack Track 1 autonomous trading agent.

The backend includes the Step 3 provider-neutral market data layer and the Step 4 execution boundaries. Spot execution uses the official Trust Wallet Agent Kit CLI; perpetual execution uses a separate BNB Agent SDK/EIP-712 bridge. Both remain testnet-only, fail closed on unsafe configuration, and are not connected to the future autonomous decision loop yet.

## Market data diagnostics

Structured logs are written to the console and, by default, to `logs/backend.log`.
The file rotates daily and keeps 14 days unless changed in `configs/instance.yaml`.

Each API request receives an `X-Request-ID`. Market-data events with the same ID include:

- `request_started`, `request_completed`, or `request_failed`
- `provider_cache_hit`, `provider_request_started`, `provider_request_completed`, or `provider_request_failed`
- `market_list_completed`, `market_search_completed`, `identity_resolution_completed`, and `price_list_completed`

Useful PowerShell commands:

```powershell
Get-Content .\logs\backend.log -Wait
Select-String -Path .\logs\backend.log -Pattern 'market_list_completed|market_search_completed|identity_resolution_completed|provider_request_failed'
```

Logs contain endpoint names, counts, timings, missing asset IDs, status, and credit usage. Authorization headers, API tokens, and provider keys are never logged.

If alert requests reach the backend but no `/api/v1/market-data/*` request is
logged, verify the APK build-time `VITE_API_READ_TOKEN`: market-data requests
require it before any network call is attempted.

## Current Scope

- FastAPI application factory in `backend/app/main.py`.
- Public liveness endpoint for process supervision.
- Authenticated readiness, heartbeat, and status endpoints.
- Admin-only manual heartbeat endpoint.
- Structured JSON/console logging via `structlog`.
- CORS and reverse-proxy header support for future HTTPS deployment.
- Provider-neutral market list, price, search, and OHLCV endpoints.
- CoinGecko default adapter for UI/market data, with CMC still available for agent/resolver paths.
- Admin-only global provider selection persisted in runtime state; background alerts use their configured alert provider.
- Conservative security headers, with HSTS enabled when `API_BASE_URL` uses `https://`.
- In-memory heartbeat loop used by health checks.
- Server-side notification service with `critical`, `warning`, and `info` severities.
- FCM token registry persisted to local JSON until database persistence is introduced.
- Alert configuration and checker state persisted to local JSON until database persistence is introduced.
- Background price checker for price thresholds, ranges, and favorite-coin percentage moves.
- Firebase Admin SDK delivery client that returns `skipped` when FCM is not configured instead of pretending success.
- Single `Settings` loader that merges `.env` secrets with `configs/*.yaml`.
- Startup guardrails for competition qualification: portfolio floor, daily trade minimum, drawdown cap, and 149 eligible tokens.
- BSC JSON-RPC failover with bounded transaction submission and on-chain receipt reconciliation.
- Non-disablable 15% BNB gas reserve, positive reserve floor, and gas-versus-profit rejection.
- Exact ERC-20 approval policy restricted to allowlisted official DEX contracts.
- Separate TWAK spot and BNB Agent SDK/EIP-712 perpetual execution paths.
- BSC-only x402 endpoint fallback with per-call and daily spending caps.
- Admin-only on-chain competition registration status check.

## Run Locally

Use the startup scripts in `backend/scripts/`. They activate the virtualenv automatically, read host and port from `Settings` (no hardcoded values), and accept an optional flag to enable Uvicorn's reload mode for local development.

**First-time setup** — create the virtualenv and install dependencies:

```bash
python -m venv backend/.venv
# Windows
backend/.venv/Scripts/activate
# Linux / macOS
source backend/.venv/bin/activate

pip install -r backend/requirements.txt
```

**Windows (PowerShell) — run from the project root:**

```powershell
# Production (no reload)
.\backend\scripts\run_backend.ps1

# Development (--reload attivo)
.\backend\scripts\run_backend.ps1 -Dev
```

**Linux / macOS — run from the project root:**

```bash
chmod +x backend/scripts/run_backend.sh

# Production
./backend/scripts/run_backend.sh

# Development
./backend/scripts/run_backend.sh --dev
```

Host and port are read from `configs/instance.yaml` via `Settings`; do not duplicate those values in the scripts or environment. The `-Dev` / `--dev` flag enables `--reload` only when explicitly passed.

Create local config files first. The repository only includes `.env.example` and `configs/instance.example.yaml`; never commit `.env`, `configs/instance.yaml`, or real secrets.

Minimum local `.env` secrets for authenticated endpoints:

```env
API_READ_TOKEN=replace-with-local-read-token
API_ADMIN_TOKEN=replace-with-local-admin-token
API_DEVICE_TOKEN=replace-with-limited-device-registration-token
API_ALERTS_TOKEN=replace-with-limited-alert-sync-token
CMC_API_KEY=replace-with-cmc-key
```

Minimum `configs/instance.yaml` installation values for real FCM delivery:

```yaml
fcm:
  enabled: true
  project_id: your-firebase-project-id
  critical_topic: cryptosentinel-critical
  token_store_path: backend/storage/fcm_tokens.json
```

Minimum `.env` secret for real FCM delivery:

```env
FCM_CREDENTIALS_PATH=C:/secure/path/firebase-service-account.json
```

The Firebase service account JSON must not be committed.

## Configuration Precedence

Runtime precedence is:

1. Environment variables and `.env`.
2. Local `configs/instance.yaml`.
3. Versioned functional YAML defaults in `configs/`.
4. Pydantic defaults inside `Settings`.

Application code must read configuration only through `backend.app.core.config.Settings`.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health/live` | Public | Process liveness. |
| GET | `/health/ready` | Read/Admin token | Readiness and dependency status. |
| GET | `/health/heartbeat` | Read/Admin token | Internal heartbeat state. |
| GET | `/api/v1/status` | Read/Admin token | Backend mode, user scope, and conservative risk defaults. |
| POST | `/api/v1/admin/heartbeat` | Admin token | Manual admin heartbeat tick. |
| GET | `/api/v1/notifications/status` | Read/Admin token | FCM subsystem status and token count. |
| POST | `/api/v1/notifications/devices` | Device/Admin token | Register an FCM device token. |
| POST | `/api/v1/notifications/devices/unregister` | Device/Admin token | Remove an FCM device token. |
| POST | `/api/v1/notifications/send` | Admin token | Send an FCM notification to registered devices. |
| POST | `/api/v1/alerts/sync` | Alerts/Admin token | Replace the mobile alert configuration used by the backend checker. |
| GET | `/api/v1/alerts/pending-favorites` | Alerts/Admin token | Return favorite-move badges awaiting user acknowledgement. |
| DELETE | `/api/v1/alerts/pending-favorites/{coin_id}` | Alerts/Admin token | Acknowledge and remove one favorite-move badge. |
| GET | `/api/v1/market-data/provider` | Read/Admin token | Active provider, rate/cache/credit diagnostics, and CMC MCP status. |
| PUT | `/api/v1/market-data/provider` | Admin token | Select CMC or CoinGecko for UI/market data and persist the choice in RuntimeState. |
| GET | `/api/v1/market-data/markets` | Read/Admin token | Normalized market-cap list from the selected provider. |
| GET | `/api/v1/market-data/prices` | Read/Admin token | Normalized current prices for assets and currencies. |
| GET | `/api/v1/market-data/search` | Read/Admin token | Search through the selected provider. |
| GET | `/api/v1/market-data/ohlcv` | Read/Admin token | Normalized OHLCV history from the dedicated exchange candle source. |
| GET | `/api/v1/execution/status` | Read/Admin token | Non-sensitive execution readiness and guardrails. |
| GET | `/api/v1/execution/competition/status` | Admin token | Verify the wallet against the official competition contract. |

The default UI/market provider is configured under `market_data.provider`. Developer settings may change it at runtime with an admin token held only in component state. Background alerts use `market_data.alert_provider` and ignore the runtime UI selector so they do not accidentally consume CMC credits. No automatic fallback is implemented.

CoinGecko is the default provider for latest pricing, listings, search, and alerts. CMC remains available for agent-specific identity/contract resolution and MCP usage under the Basic credit budget. Public OHLCV chart requests are intentionally served by the dedicated exchange candle source (`ExternalOHLCVService`, Binance klines first with CEX fallback) so the app does not depend on paid CMC OHLCV endpoints. The legacy CMC OHLCV adapter remains available for compatibility tests but is not used by `/api/v1/market-data/ohlcv`.

## Step 4 Execution Setup

Install the backend requirements and the official TWAK CLI:

```powershell
npm install -g @trustwallet/cli@0.19.1
twak --version
```

On Windows, restart PowerShell after installation if `twak` is still not
recognized. The expected npm launcher is normally
`%APPDATA%\npm\twak.cmd`. CryptoSentinel resolves this `.cmd` launcher
automatically; alternatively set `twak.cli_path` in local
`configs/instance.yaml` to its absolute path.

### Encrypt the BNB SDK wallet

Run the encryption script from the project root:

```powershell
.\backend\.venv\Scripts\python.exe .\backend\scripts\encrypt_wallet.py
```

The script asks for the private key and passphrase through hidden interactive
input. It accepts no CLI arguments, refuses to overwrite an existing keystore,
and writes only the encrypted Web3 keystore to
`secrets/wallet-keystore.json`. Its output contains only confirmation and the
derived public address.

Add these entries to the local `.env`:

```dotenv
WALLET_ENCRYPTED_PRIVATE_KEY_PATH=secrets/wallet-keystore.json
WALLET_KEY_PASSPHRASE_ENV=CRYPTOSENTINEL_WALLET_PASSPHRASE
CRYPTOSENTINEL_WALLET_PASSPHRASE=replace-with-the-keystore-passphrase
TATUM_RPC_API_KEY=
```

`WALLET_KEY_PASSPHRASE_ENV` contains the name of the variable holding the
passphrase, not the passphrase itself. Never commit `.env` or the keystore.

The encrypted keystore is used by the BNB SDK/EIP-712 path. TWAK manages a
separate self-custody wallet for spot execution and does not import this
keystore. Create the TWAK wallet interactively without placing its password in
the shell history:

```powershell
twak wallet create --no-keychain
twak wallet address --chain bsc
```

Fund the address returned by the second command with enough BNB for mainnet gas.
Keep enough BNB above the configured 15% reserve and the `0.000005` BNB floor.

On Windows PowerShell, do not pass non-ASCII TWAK wallet passwords through
`--password`, `TWAK_WALLET_PASSWORD`, or `twak wallet keychain save --password`
directly. PowerShell/CLI argument encoding can alter special characters and
cause `Wallet authentication failed`. Put the exact password in a local UTF-8
text file outside the repository and use the Node wrapper:

```powershell
node scripts/twak-password-file.cjs --password-file C:\tmp\twak-password.txt -- wallet keychain save --password-from-file --json
twak wallet address --chain bsc --json
```

For one-off commands without storing the password in TWAK keychain:

```powershell
node scripts/twak-password-file.cjs --password-file C:\tmp\twak-password.txt -- wallet address --chain bsc --json
```

Delete the password file after confirming the keychain works.

### Configure BSC

Copy the Step 4 sections from `configs/instance.example.yaml` into the local
`configs/instance.yaml`. Replace legacy values with:

```yaml
bsc:
  network: testnet
  chain_id: 97
  rpc_urls:
    - https://bsc-testnet-rpc.publicnode.com
    - https://data-seed-prebsc-1-s1.bnbchain.org:8545
    - https://data-seed-prebsc-2-s1.bnbchain.org:8545
    # Authenticated (requires TATUM_RPC_API_KEY in .env):
    # - https://bsc-testnet.gateway.tatum.io
  explorer_base_url: https://testnet.bscscan.com
  required_confirmations: 1

competition:
  contract_address: "0x212c61b9b72c95d95bf29cf032f5e5635629aed5"
  chain_id: 56
  rpc_urls:
    - https://bsc-dataseed.bnbchain.org
    - https://bsc-dataseed1.defibit.io
  explorer_base_url: https://bscscan.com

x402:
  enabled: false
  network: bsc
```

The competition contract is intentionally on BSC mainnet. It is used only for
registration/status and must not replace the BSC testnet trading RPC.

Tatum is optional. Set `TATUM_RPC_API_KEY` in `.env` and uncomment the Tatum
URL in local `configs/instance.yaml`. CryptoSentinel sends `x-api-key` only to
`tatum.io` hosts; PublicNode and BNB Chain endpoints remain unauthenticated.
For future mainnet operation, configure a BSC mainnet Tatum endpoint only in
Step 9. Step 4 trading remains locked to chain ID 97.

The configured RPC list is used by CryptoSentinel for balance/gas preflight,
failover, receipt polling, and on-chain verification. TWAK CLI `0.19.1` does
not expose a custom RPC option for `swap`; its `bsctestnet` chain currently
uses TWAK's internal `https://bsc-testnet.twnodes.com` endpoint. Therefore a
TWAK broadcast failure can still occur even when CryptoSentinel's Tatum/BNB
Chain preflight succeeds.

Spot and perpetual execution are deliberately separate. Spot uses TWAK on
`bsctestnet`; perpetual orders are EIP-712 signed only for chain ID 97 and
allowlisted verifying contracts. Perpetual submission remains disabled until
an official testnet venue URL and contract are configured.

Spot quote and route-step preparation use the Trust Wallet REST Amber API:
`/amber-api/v1/domains`, `/amber-api/v1/providers`, `/amber-api/v1/route`,
and `/amber-api/v1/route/step`. The CLI remains used only for TWAK wallet
address and competition commands. The REST API returns route and transaction
data; signing and broadcast still require a wallet provider. x402 prefers
EIP-3009 and does not enable Permit2 auto-approval.

The gas decision is mandatory for spot execution. A trade is rejected when it
would consume the protected BNB reserve or estimated gas is not lower than
expected profit. TWAK does not expose unsigned swap calldata before execution,
so the smoke test uses the supplied conservative gas limit multiplied by the
gas price read through RPC failover. The estimation mode and failures are
written to structured logs.

### Run a guarded spot smoke test

First verify that TWAK returns the funded mainnet address:

```powershell
twak wallet address --chain bsc --json
twak wallet balance --chain bsc --json
```

Then run one small swap through CryptoSentinel's Step 4 layer:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\backend\.venv\Scripts\python.exe .\backend\scripts\test_spot_swap.py `
  0.0001 BNB USDT `
  --to-asset <TESTNET_USDT_CONTRACT_ADDRESS> `
  --slippage 0.5 `
  --gas-limit 350000 `
  --expected-profit-usd 1.00 `
  --bnb-price-usd 600
```

Use a current BNB/USD value and a defensible expected-benefit estimate; the
command intentionally fails if the gas guard rejects them. It prompts for the
TWAK wallet password only to read the wallet address and requires typing
`TESTNET` before calling the REST route endpoints. Token availability and
liquidity on PancakeSwap testnet must be checked before choosing the pair.

With the REST path, a successful smoke test prints `Status: prepared` and the
number of returned route-step transactions. That means Amber authentication,
quote, provider routing, and route-step preparation worked. It does not mean a
transaction was signed or broadcast.

The smoke test writes structured diagnostic events to `logs/backend.log` even
when FastAPI is not running. Relevant events are:

- `spot_smoke_test_started`
- `rpc_endpoint_failed` or `spot_rpc_preflight_failed`
- `spot_gas_guard_evaluated`
- `twak_command_failed` or `spot_twak_swap_failed`
- `spot_receipt_reconciled`

TWAK diagnostics are bounded and redact URLs, credentials, tokens, passwords,
private-key labels, and 32-byte hexadecimal values.

If a swap fails, check the events in order:

1. No `spot_smoke_test_started`: the script did not reach execution setup.
2. `rpc_endpoint_failed`: one RPC failed; the next endpoint is tried.
3. `spot_rpc_preflight_failed`: every configured RPC failed.
4. Rejected `spot_gas_guard_evaluated`: balance/reserve or gas/profit check failed.
5. `twak_command_failed`: quote, liquidity, TWAK wallet, or TWAK internal RPC failed.
6. `spot_receipt_reconciled` is not confirmed: the transaction reverted or remains unknown.

If `TWAK REST credentials are not configured` appears, `Settings` does not see
both `TWAK_ACCESS_ID` and `TWAK_HMAC_SECRET`. Add them to `.env` with exactly
those names and restart the shell/backend process.

If migrating to a new TWAK wallet, persist the public execution wallet in
RuntimeState:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\backend\.venv\Scripts\python.exe .\backend\scripts\select_twak_wallet.py --address 0xDF27d02a536F1AaAF16a25D5E76DA50d716EAfeB
```

Competition registration is a separate BSC mainnet prerequisite, not a trading
operation:

```powershell
twak compete status --json
twak compete register --json
```

Verify registration through `/api/v1/execution/competition/status` and BscScan.
Never pass wallet passwords as command-line arguments.

Authentication accepts either:

```http
Authorization: Bearer <token>
```

or:

```http
X-API-Token: <token>
```

## Mobile Push Registration

The mobile app uses `@capacitor/push-notifications` to obtain the FCM registration token and posts it to `/api/v1/notifications/devices` when these Vite variables are configured at build time:

```env
VITE_BACKEND_API_BASE_URL=https://your-backend.example
VITE_API_READ_TOKEN=replace-with-limited-read-token
VITE_API_DEVICE_TOKEN=replace-with-limited-device-registration-token
VITE_API_ALERTS_TOKEN=replace-with-limited-alert-sync-token
```

If those variables are missing, foreground local notifications continue to work while remote push registration and closed-app delivery are skipped.

## Directory Structure

```text
backend/
|-- app/
|   |-- api/ - FastAPI routers and API dependencies.
|   |-- agent/ - autonomous agent heartbeat, brain, loops, risk engine, and modular signals.
|   |-- core/ - configuration, logging, auth, security headers, and runtime primitives.
|   |-- data/ - market data adapters, CMC integration, MCP integration, and cache boundaries.
|   |-- domain/ - domain models split by common, spot, perp, and global state.
|   |-- execution/ - trading execution adapters for TWAK, BNB SDK/EIP-712, x402, and wallet custody.
|   |-- i18n/ - translation files and localization helpers.
|   |-- notifications/ - alert state, background price checker, notification service, and FCM integration.
|   |-- observability/ - logging, metrics, health, and replay/export support.
|   |-- persistence/ - database models, repositories, and migrations.
|   |-- schemas/ - API schemas and DTOs.
|   |-- services/ - application services coordinating domain logic.
|   `-- tasks/ - scheduled jobs and background task entrypoints.
|-- scripts/ - startup and operational scripts (run_backend.ps1, run_backend.sh).
|-- tests/ - unit and integration tests.
`-- requirements.txt - backend Python dependencies.
```

## Security Notes

- `API_READ_TOKEN` can read health/status endpoints.
- `API_DEVICE_TOKEN` can only register/unregister push tokens.
- `API_ALERTS_TOKEN` can only replace the current alert configuration.
- `API_ADMIN_TOKEN` can call admin endpoints and send notifications.
- Device token registration deliberately does not use read or admin tokens in the mobile app.
- If tokens are missing, protected endpoints return `503` instead of silently running unauthenticated.
- Wallet private keys must remain encrypted at rest. Store only encrypted key paths and passphrase source names in environment variables.
- HTTPS is expected at the reverse proxy on VPS. The app is prepared for proxy headers and HSTS once `API_BASE_URL=https://...` is configured.
