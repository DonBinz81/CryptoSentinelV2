# Report Step 2 - Backend Notifications via FCM

## 1. COSA È STATO FATTO

- Added server-side Firebase Cloud Messaging support to the backend.
- Added `firebase-admin==7.4.0` to `backend/requirements.txt` after verifying the available PyPI version.
- Installed backend dependencies in the local `backend/.venv` virtual environment.
- Added `API_DEVICE_TOKEN` as a limited token scope for mobile push-token registration.
- Added `VITE_BACKEND_API_BASE_URL` and `VITE_API_DEVICE_TOKEN` for mobile builds.
- Added `FCM_TOKEN_STORE_PATH` to keep device tokens in a local JSON registry until database persistence is introduced.
- Added notification schemas in `backend/app/schemas/notifications.py`.
- Added a file-backed FCM token registry in `backend/app/notifications/fcm/token_store.py`.
- Added Firebase Admin SDK wrapper in `backend/app/notifications/fcm/client.py`.
- Added notification orchestration service in `backend/app/notifications/service.py`.
- Added notification API routes in `backend/app/api/routes/notifications.py`.
- Registered notification routes in the FastAPI router tree.
- Updated readiness to expose FCM status as `configured` or `not_configured` instead of a generic placeholder.
- Added notification severity levels: `critical`, `warning`, and `info`.
- Added device registration endpoint: `POST /api/v1/notifications/devices`.
- Added device unregister endpoint: `POST /api/v1/notifications/devices/unregister`.
- Added notification status endpoint: `GET /api/v1/notifications/status`.
- Added admin-only send endpoint: `POST /api/v1/notifications/send`.
- Installed `@capacitor/push-notifications@8.1.1` for the mobile app.
- Integrated mobile FCM token registration in `src/utils/notifications.ts`.
- Ran `npx cap sync android` and `npx cap copy android` to include the push plugin in Android.
- Updated `backend/README.md` with notification endpoints, env variables, and FCM setup notes.
- Updated `docs/PROJECT_STRUCTURE.md` with Step 2 structure, stack, env, decisions, and reviewer notes.

## 2. COME È STATO FATTO

- FCM delivery is implemented server-side through Firebase Admin SDK, not through client-only local notifications.
- The existing local notification and Android WorkManager flow was preserved as a fallback; Step 2 does not remove working local alert behavior.
- Device token registration uses a dedicated `API_DEVICE_TOKEN` scope. The mobile app does not need read/admin credentials.
- Notification sending is admin-only. This keeps the admin boundary clear before future endpoints that move funds or change configuration.
- Because the database is not implemented until Step 5, token persistence uses a local JSON file at `FCM_TOKEN_STORE_PATH`.
- The FCM client returns `skipped` with `fcm_not_configured` when credentials are unavailable, avoiding false-positive delivery status.
- Mobile remote push registration is conditional: if `VITE_BACKEND_API_BASE_URL` or `VITE_API_DEVICE_TOKEN` is missing, the app skips server registration and local notifications keep working.
- Capacitor Push Notifications was used instead of custom Java Firebase token code to keep the mobile integration aligned with the existing Capacitor architecture.

## 3. COSA È STATO VERIFICATO

- Ran `backend/.venv/Scripts/python -m compileall backend/app backend/tests` successfully.
- Verified `.env.example` still contains no non-empty assignments with `Select-String -Pattern '^[A-Z0-9_]+=.+'`; no matches were returned.
- Ran backend notification endpoint checks with FastAPI `TestClient` and temporary environment tokens:
- `POST /api/v1/notifications/devices` with device token returned `201`.
- `GET /api/v1/notifications/status` with read token returned `200` and token count `1`.
- `POST /api/v1/notifications/send` with read token returned `401`.
- `POST /api/v1/notifications/send` with admin token returned `200` and `skipped_reason=fcm_not_configured` because no Firebase credentials are present.
- `POST /api/v1/notifications/devices/unregister` with device token returned `200`.
- Ran `npm run build` successfully after the mobile push integration.
- Ran `npx cap sync android` successfully; Capacitor detected `@capacitor/push-notifications@8.1.1`.
- Ran `npx cap copy android` successfully after the final frontend build.
- Attempted Android debug build with Gradle. The build failed because the current JVM is Java 8, while Android Gradle Plugin and Google Services require Java 11 or newer.

## 4. SCOSTAMENTI DAL PIANO

- Real FCM delivery was not tested against Firebase servers because no `FCM_PROJECT_ID` and service account JSON are present in the repository. This is intentional: credentials must remain outside the repo.
- Device tokens are persisted in a JSON file rather than a database. This is temporary until Step 5 introduces database persistence.
- The mobile app still keeps local notifications and WorkManager checks. This is intentional as a fallback and avoids regressing existing alert behavior before the backend alert engine is complete.
- Android build verification is blocked by local Java 8. The project requires Java 11+ for the current Android Gradle Plugin; Java 17 remains the recommended target from the README.

## 5. QUESTIONI APERTE

- Non-blocking: Firebase project ID and service account JSON must be provided in local/prod `.env` to test real FCM delivery.
- Non-blocking until deploy: decide final `VITE_BACKEND_API_BASE_URL` for mobile builds.
- Non-blocking until deploy: generate a limited `API_DEVICE_TOKEN` for mobile registration.
- Non-blocking until Step 5: migrate token registry from JSON file to the database.
- Non-blocking environment issue: configure Java 17 or at least Java 11 before Android debug/release builds.

## 6. STATO DELIVERABLE

Parziale.

The backend FCM system, severity model, token registration, admin send endpoint, mobile token registration path, and fallback behavior are implemented and verified locally. Real end-to-end FCM delivery with the app closed requires Firebase credentials and a Java 11+ Android build environment, neither of which is present in the repository environment.
