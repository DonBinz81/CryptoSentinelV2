# Report Task Intermedio - Ambiente + Riorganizzazione Configurazione

## 1. COSA È STATO FATTO

- Riorganizzata la configurazione in tre categorie per ciclo di vita e ownership:
  - segreti in `.env` / `.env.example` solo template vuoto;
  - configurazione di installazione in `configs/instance.example.yaml` e futuro `configs/instance.yaml` locale gitignored;
  - configurazione funzionale versionata in `configs/risk.yaml`, `configs/strategy_spot.yaml`, `configs/strategy_perp.yaml`, `configs/eligible_tokens.yaml`.
- Creato `configs/README.md` con categorie, ordine di precedenza e guardrail hard.
- Rifattorizzato `backend/app/core/config.py` come unico punto di caricamento runtime.
- Aggiunta fusione YAML + `.env` in un unico oggetto `Settings` validato.
- Aggiunti guardrail hard fail-closed all'avvio:
  - portfolio minimo sempre > 1 USD;
  - minimo 1 trade/giorno;
  - drawdown cap negativo e non più permissivo di -15%;
  - lista token eligible esattamente da 149 elementi.
- Aggiornato `.env.example` per contenere solo segreti e path sensibili a valori vuoti.
- Aggiornato `.gitignore` per escludere `configs/instance.yaml` e `configs/*.local.yaml`.
- Aggiunta dipendenza diretta `PyYAML==6.0.3` in `backend/requirements.txt`.
- Aggiornato `backend/README.md` con configurazione, precedenza e separazione `.env`/YAML.
- Aggiornato `docs/PROJECT_STRUCTURE.md` con struttura, stack, variabili, stato, decisioni e note revisore.
- Verificato che il workflow GitHub Actions esistente è configurato per compilare APK con Temurin JDK 21; non è stata installata toolchain Java locale.

## 2. COME È STATO FATTO

- `Settings` riceve i valori YAML tramite `load_yaml_settings()` e usa `pydantic-settings` con precedenza esplicita: variabili ambiente e `.env` > `configs/instance.yaml` > YAML funzionali versionati > default Pydantic.
- I file YAML sono caricati solo da `backend/app/core/config.py`; il resto del backend continua a dipendere da `get_settings()` / `Settings`.
- I file funzionali sono separati per dominio:
  - `risk.yaml` per rischio e qualification guardrail;
  - `strategy_spot.yaml` per strategia Spot;
  - `strategy_perp.yaml` per strategia Perpetual;
  - `eligible_tokens.yaml` per universo token della gara.
- I path a file segreti, inclusi wallet cifrato e service account Firebase, sono stati mantenuti in `.env.example` perché anche il path può rivelare materiale sensibile.
- Gli errori Pydantic sono configurati con `hide_input_in_errors=True` per evitare stampa dei valori di configurazione in caso di validazione fallita.
- `configs/instance.example.yaml` include `dashboard.port: 5176` e CORS per `localhost:5176` / `127.0.0.1:5176`.
- Per Java/APK è stata scelta la strada GitHub Actions: il workflow esistente usa `actions/setup-java` con Temurin JDK 21, superiore al minimo richiesto Java 17 e coerente con il flusso già usato dal progetto.

## 3. COSA È STATO VERIFICATO

- Verificato il loader Settings da directory temporanea, senza eseguire comandi dalla root che possano caricare `.env` locale:
  - `settings_ok 5176 149 5.0 -15.0`.
- Verificato import dell'app FastAPI:
  - `app_ok CryptoSentinel Agent Backend`.
- Verificato `PyYAML` disponibile nell'ambiente backend:
  - `pyyaml_ok 6.0.3`.
- Verificato `compileall` su `backend/app` con esito positivo.
- Verificato guardrail fail-closed con config temporanea fuori limite (`min_portfolio_value_usd: 1.0`): avvio rifiutato con `ValidationError` e messaggio `min_portfolio_value_usd must stay above the hard $1 qualification floor`.
- Verificato che l'errore di validazione non stampi più l'input di configurazione dopo `hide_input_in_errors=True`.
- Verificato che `configs/eligible_tokens.yaml` carichi esattamente 149 elementi.
- Verificato che il workflow `.github/workflows/build-apk.yml` esista e usi `Setup Java 21` con `distribution: temurin`.

## 4. SCOSTAMENTI DAL PIANO

- Non è stato installato/configurato JDK 17 sulla macchina locale. Motivo: il progetto compila APK tramite GitHub Actions e l'utente ha confermato di preferire questo flusso per non installare SDK/JDK localmente.
- Non è stata rilanciata una build APK locale. Motivo: la macchina locale ha Java 8 e la policy scelta è demandare APK a GitHub Actions.
- Non è stata lanciata una nuova run GitHub Actions da qui. Motivo: le modifiche sono locali/non committate; una run remota costruirebbe lo stato già presente su GitHub, non necessariamente questo workspace.
- La build APK resta quindi da verificare al prossimo push o `workflow_dispatch` su GitHub Actions.
- `FCM_CREDENTIALS_PATH` è stato classificato come segreto in `.env.example`, anche se era indicato tra gli esempi di installazione, perché la stessa richiesta specifica che i path ai file segreti devono stare nella categoria SEGRETI.

## 5. QUESTIONI APERTE

- Confermare dopo push/run CI che l'APK debug viene prodotto correttamente dal workflow GitHub Actions con JDK 21.
- Confermare se `DATABASE_URL` dovrà restare sempre in `.env` oppure se in futuro separare URL non sensibili SQLite/locali in `configs/instance.yaml` e URL con credenziali in `.env`.
- Drawdown cap esatto gara, DEX Perp e approvals TWAK restano questioni Telegram non bloccanti: si procede con default prudenziali già fissati nel piano.
- Quando arriveranno endpoint di execution o modifica configurazione, mantenere admin come confine netto: read non deve mai soddisfare admin.
- In Step 5 trasformare readiness DB da `not_checked` a check reale di connettività.

## 6. STATO DELIVERABLE

Parziale.

La riorganizzazione configurazione è completata e verificata. La parte APK è predisposta su GitHub Actions con JDK 21, ma l'esito della build remota va verificato al prossimo push o run manuale del workflow.
