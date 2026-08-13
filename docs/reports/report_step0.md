# Report Step 0 - Setup & Architecture

## 1. COSA È STATO FATTO

- Read the full project plan from `plans/Plan_forHackathon.md` before making changes.
- Read the full Spot strategy from `docs/Strategia_Spot.md` before making changes.
- Read the full Perpetual strategy from `docs/Strategia_Perpetual.md` before making changes.
- Verified the existing baseline document `docs/CURRENT_STRUCTURE.md` before creating the backend scaffold.
- Created the FastAPI/Python backend scaffold under `backend/`.
- Created backend package boundaries for API, agent, configuration, security, data, domain, execution, i18n, notifications, observability, persistence, schemas, services, tasks, scripts, and tests.
- Created explicit market separation from the first scaffold: `spot`, `perp`, and `global_state` packages.
- Added single-user-ready-for-multi model primitives with `user_id` in `backend/app/domain/common/models.py`.
- Added placeholder domain models for Spot positions, Perpetual positions, and Global portfolio snapshots.
- Added a modular signal engine contract in `backend/app/agent/signals/base.py`.
- Added Spot signal placeholders for V1 momentum and V2 relative strength.
- Added Perpetual signal placeholders for V1 Volume Profile and V2 order-flow delta.
- Added wallet custody boundary documentation in code: raw private keys must never be stored in env, source, logs, or plaintext files.
- Created i18n locale files in `backend/app/i18n/locales/en.json` and `backend/app/i18n/locales/it.json`.
- Created `backend/requirements.txt` with initial backend dependencies.
- Created root `requirements.txt` delegating to `backend/requirements.txt` for root-level installation convenience.
- Created root `.env.example` with empty values and explanatory comments for all required backend variables.
- Updated `.gitignore` for Python artifacts, virtual environments, local databases, `.env`, wallet secrets, service account files, and backend local state.
- Created `backend/README.md` with backend structure and Step 0 boundaries.
- Created this report in `docs/reports/report_step0.md`.
- Updated `docs/PROJECT_STRUCTURE.md` for the post-Step-0 repository structure, stack, env variables, step status, decisions, and reviewer notes.

## 2. COME È STATO FATTO

- The existing React/Capacitor app was left intact; the backend was added under a separate `backend/` directory to avoid mixing frontend/mobile code with server-side trading logic.
- The backend scaffold follows a layered structure: API boundary, domain models, services, persistence, agent logic, execution adapters, observability, and notifications.
- Spot and Perpetual execution paths are split from the beginning because the plan requires TWAK for Spot and BNB AI Agent SDK / EIP-712 for Perpetual.
- Global portfolio state is isolated in `global_state` so Spot, Perp, and aggregate PnL/drawdown can evolve independently.
- `user_id` is included in base domain models now, using a fixed default UUID for single-user operation, so future multi-user support does not require rewriting model ownership.
- Signal modules use a common abstract contract so V1 signals and V2 additions can be plugged in without rewriting the agent orchestration.
- i18n starts with locale JSON files to prevent new backend-facing strings from being hardcoded.
- `.env.example` contains only empty assignments and comments. No real API keys, wallet data, private URLs, or contract values were written.
- Wallet custody is represented as an encrypted-key boundary. The environment contract stores paths and passphrase source names only, not raw private keys.
- `backend/README.md` was created instead of replacing the existing root `README.md`, because the root file already documents the current mobile app.

## 3. COSA È STATO VERIFICATO

- Ran `python -m compileall backend` successfully: all Python scaffold files compile syntactically.
- Verified `.env.example` has no non-empty assignments using `Select-String -Pattern '^[A-Z0-9_]+=.+'`; no matches were found.
- Verified new backend files are present using `rg --files backend .env.example .gitignore docs plans`.
- Confirmed `.gitignore` includes `.env`, Python caches, virtual environments, local DB files, backend local state, service account JSON files, and wallet-secret patterns.
- Confirmed no backend server endpoints or Step 1 functionality were implemented.

## 4. SCOSTAMENTI DAL PIANO

- No functional FastAPI app, health endpoint, authentication implementation, logging setup, or heartbeat was implemented. This is intentional: those are Step 1 deliverables, not Step 0.
- The backend README was created at `backend/README.md` rather than replacing root `README.md`, to preserve the existing CryptoSentinel mobile app documentation.
- Root `requirements.txt` was added as a small delegator to `backend/requirements.txt` to satisfy root-level reviewer expectations without duplicating dependency lists.

## 5. QUESTIONI APERTE

- Confirm the exact drawdown cap for the competition; the plan currently uses a prudential default of -15%.
- Confirm which Perpetual DEX/provider should be used for live execution.
- Confirm whether TWAK approval mode should be exact/limited and how autonomous approvals are enforced.
- Confirm where encrypted wallet material will be stored on the deployment host.
- Confirm whether SQLite is enough for the hackathon run or PostgreSQL should be used immediately on VPS.
- Confirm final model choice and spend limits for Anthropic/Claude before inserting any real key.
- Confirm whether the competition contract address should be committed as public config later or injected only through environment.

## 6. STATO DELIVERABLE

Raggiunto.

Step 0 produced the backend scaffold, env contract, dependency files, gitignore updates, multi-user-ready model boundary, i18n structure, modular signal engine structure, backend README, report, and updated project structure documentation. Step 1 has not been started.
