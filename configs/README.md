# Configuration Model

CryptoSentinel uses one runtime loading point: `backend/app/core/config.py`.
Application code must depend on `Settings` only and must not read YAML files,
`.env`, or secret files directly.

## Categories

1. Secrets: local `.env`, never versioned. The tracked `.env.example` contains
   only empty secret keys and sensitive secret-file paths.
2. Installation config: `configs/instance.yaml`, never versioned. The tracked
   `configs/instance.example.yaml` is the template for host-specific,
   non-secret values such as API URL, CORS origins, BSC network, wallet address,
   FCM project id, and execution mode.
3. Functional config: versioned YAML files in `configs/`. These contain default
   risk and strategy parameters that can later become per-user overrides.

## Precedence

Runtime precedence is explicit:

1. Environment variables and `.env`.
2. `configs/instance.yaml`.
3. Versioned functional defaults:
   `configs/risk.yaml`, `configs/strategy_spot.yaml`,
   `configs/strategy_perp.yaml`, and `configs/eligible_tokens.yaml`.
4. Pydantic field defaults inside `Settings`.

## Hard Guardrails

The following qualification guardrails are validated at startup and cannot be
disabled by config:

- Minimum portfolio value must stay above 1 USD.
- Minimum trade frequency must be at least 1 trade per day.
- Drawdown cap must be negative and no looser than -15%.
- Eligible-token universe must contain exactly 149 competition entries.
- BNB gas reserve must be at least 15% with a positive non-tradable floor.
- Step 4 live execution is allowed only on BSC testnet.
- Transaction attempts are bounded to at most 3 and confirmations are at least 1.
- Competition registration uses only the official contract on BSC chain 56.
- x402 can be enabled only on BSC.

If any source violates these rules, `Settings` raises a validation error and the
backend refuses to start.

## Optional RPC Authentication

`TATUM_RPC_API_KEY` is an optional secret in `.env`. The execution RPC client
sends it as `x-api-key` only when the configured endpoint hostname is
`tatum.io` or one of its subdomains. Other RPC providers never receive it.
