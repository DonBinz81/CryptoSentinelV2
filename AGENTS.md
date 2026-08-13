# AGENTS.md

Operational rules for AI agents working on CryptoSentinelHackathon.

## Scope

- These rules apply to the whole repository unless a more specific `AGENTS.md` exists in a subdirectory.
- Follow the latest user instruction, but do not violate the security rules below.
- Work pragmatically: implement, verify, document, then report.

## Absolute Security Rules

- Never open, read, print, log, copy, or commit `.env`.
- Never open, read, print, log, copy, or commit anything under `secrets/` or `backend/secrets/`.
- Never open, read, print, log, copy, or commit service account JSON files, private keys, wallet key material, passphrases, or secret manager dumps.
- Use only `.env.example` for the environment variable contract.
- Keep `.env.example` values empty.
- Treat paths to secret files as sensitive values.
- Before committing, check staged file names and block real `.env`, `secrets/`, service account JSON, private keys, encrypted wallet files, and `configs/instance.yaml`.

## Required Documentation After Each Step

- Update `docs/PROJECT_STRUCTURE.md` at the end of every operational step.
- Add or update a report under `docs/reports/` when completing a step or relevant intermediate task.
- Use the project report structure:
  1. `COSA È STATO FATTO`
  2. `COME È STATO FATTO`
  3. `COSA È STATO VERIFICATO`
  4. `SCOSTAMENTI DAL PIANO`
  5. `QUESTIONI APERTE`
  6. `STATO DELIVERABLE`
- Do not start the next planned step without explicit user approval.

## Planning Documents

- Before any new planned step, read the relevant plan and strategy documents completely:
  - `plans/Plan_forHackathon.md`
  - `docs/Strategia_Spot.md`
  - `docs/Strategia_Perpetual.md`
- `docs/CURRENT_STRUCTURE.md` is the baseline project snapshot.
- `docs/PROJECT_STRUCTURE.md` is the current external-review reference.

## Configuration Rules

- The backend configuration has one loading point: `backend/app/core/config.py`.
- Application code must read configuration only through `Settings`.
- Do not read YAML, `.env`, or secret files directly outside the Settings loader.
- Runtime precedence is:
  1. Environment variables and `.env`
  2. `configs/instance.yaml`
  3. Versioned functional YAML defaults in `configs/`
  4. Pydantic defaults in `Settings`
- `.env.example` contains only secrets and sensitive paths.
- `configs/instance.example.yaml` is the tracked template for local non-secret installation config.
- `configs/instance.yaml` is local-only and gitignored.
- Functional defaults live in:
  - `configs/risk.yaml`
  - `configs/strategy_spot.yaml`
  - `configs/strategy_perp.yaml`
  - `configs/eligible_tokens.yaml`

## Hard Guardrails

- The backend must fail closed if qualification guardrails are violated.
- Portfolio value floor must stay above 1 USD.
- Minimum trade frequency must be at least 1 trade per day.
- Drawdown cap default is the prudent plan value, `-15%`, until official clarification.
- The eligible-token universe must contain exactly 149 competition entries.
- Trades outside the eligible-token universe must not be allowed.
- Telegram/open organizer questions are not blockers; use prudent defaults from the plan and update later if official answers arrive.

## Auth And Execution Boundaries

- Read token may be satisfied by admin token.
- Read token must never satisfy admin checks.
- Device token is limited to device registration/unregistration.
- Endpoints that move funds, change configuration, or affect execution must require admin-only authorization.
- Wallet private keys must remain encrypted at rest and never be stored or logged in clear text.

## Backend Rules

- Backend stack is Python + FastAPI.
- Code and code comments must be in English.
- Keep single-user ready-for-multi-user design: models and persisted data should include `user_id` where relevant.
- Preserve separation between Spot, Perp, and Global domains.
- Preserve i18n structure.
- Preserve modular signal engine structure, including Delta V2 and Relative Strength V2 placeholders.
- In Step 5, readiness must replace database `not_checked` with a real connectivity check.

## Frontend And Dashboard Rules

- Future dashboard must point to port `5176`.
- Existing frontend/mobile patterns should be preserved unless explicitly redesigning.
- Do not run local frontend builds if doing so may load real `.env`; prefer CI or safe temporary environments.
- Complete the legacy frontend IT-to-EN i18n conversion before Step 8. Keep English as the default and preserve Italian; replace strings without rewriting component logic.
- Resolve the existing React lint debt as a separate, narrowly scoped task before making `npm run lint` a mandatory CI gate.

## Active Constraints From Step 3 Review

- The accepted Step 3 follow-ups do not block Step 4.
- Implement the 5-minute Volume Profile feed in Step 6 using Binance klines:
  - Futures: `GET /fapi/v1/klines`
  - Spot: `GET /api/v3/klines`
- Keep the Binance kline feed specialized to the signal engine, including `signals/perp/volume_profile.py`; do not route it through the generic `MarketDataProvider`.
- Ensure the GitHub Actions secret `VITE_API_READ_TOKEN` is configured before APK builds that need frontend market-data access. Never print or inspect its value.

## Android And CI Rules

- Do not require local JDK/Android SDK installation unless the user explicitly asks.
- APK builds are expected through GitHub Actions.
- The workflow uses Temurin JDK 21, accepted because it is above the Java 17 minimum for the Android toolchain.
- `deploy-pages` must update GitHub Pages only from builds on `main`.
- Pages deployment uses the `gh-pages` branch and must not be blocked by the protected `github-pages` environment.

## Git Rules

- Never revert user changes unless explicitly requested.
- Never use destructive commands such as `git reset --hard` or `git checkout --` unless explicitly approved.
- Before commit, inspect staged file names for forbidden sensitive files.
- Commit messages should be concise and describe the deliverable.
- Push only when requested by the user.

## Verification Expectations

- For runtime bugs, inspect the available backend and frontend diagnostic logs before identifying a code-level cause or making corrective changes.
- Correlate related events through `X-Request-ID` where available, and base the diagnosis on logged evidence rather than assumptions.
- If the existing logs are insufficient, improve the relevant non-sensitive instrumentation first, reproduce the issue, and only then modify application behavior.
- For backend tests and import checks on this Windows workspace, use the project backend virtualenv interpreter: `backend\.venv\Scripts\python.exe` from the repository root. Do not assume `.venv\Scripts\python.exe` exists at the repository root.
- Verify backend import/startup paths after backend changes.
- Verify guardrail failures when changing configuration logic.
- Verify GitHub Actions status after CI workflow changes and report the run URL.
- If a test/build cannot be run, state exactly why and what remains to verify.
