# Report CI google-services Secret

## 1. COSA È STATO FATTO

- Aggiornato `.github/workflows/build-apk.yml`.
- Aggiunto lo step `Restore google-services.json` prima di `Build web app`, `npx cap sync android` e `./gradlew assembleDebug`.
- Lo step ricostruisce `android/app/google-services.json` dal GitHub Secret `GOOGLE_SERVICES_JSON`.
- Aggiornato `docs/PROJECT_STRUCTURE.md`.

## 2. COME È STATO FATTO

- Il secret viene passato come variabile d'ambiente mascherata:
  `GOOGLE_SERVICES_JSON: ${{ secrets.GOOGLE_SERVICES_JSON }}`.
- Il contenuto non viene stampato.
- Il workflow fallisce esplicitamente se il secret non è configurato.
- Il file viene scritto solo nel runner CI:
  `printf '%s' "$GOOGLE_SERVICES_JSON" | base64 -d > android/app/google-services.json`.
- `android/app/google-services.json` resta ignorato da Git e non deve essere committato.

## 3. COSA È STATO VERIFICATO

- Verificato che `.env`, `secrets/` e `android/app/google-services.json` siano ignorati da `.gitignore`.
- Verificato che lo step sia posizionato prima di `npx cap sync android` e prima della build Gradle.
- Non è stato letto, stampato o committato il contenuto di `android/app/google-services.json`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno. La modifica abilita FCM nell'APK prodotto da CI senza versionare credenziali Firebase.

## 5. QUESTIONI APERTE

- L'utente deve creare il GitHub Secret `GOOGLE_SERVICES_JSON` con il contenuto base64 del file locale.
- Il file Firebase deve essere quello della Android app con package `com.cryptosentinelai.app`.

Comando PowerShell locale per generare il base64 senza stamparlo a terminale:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("android/app/google-services.json")) | Set-Clipboard
```

Alternativa PowerShell per salvare in un file temporaneo da aprire manualmente:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("android/app/google-services.json")) | Set-Content -NoNewline "C:\\tmp\\google-services.base64.txt"
```

Comando Linux/macOS:

```bash
base64 -w 0 android/app/google-services.json
```

GitHub path:

`Repository Settings -> Secrets and variables -> Actions -> New repository secret -> GOOGLE_SERVICES_JSON`

## 6. STATO DELIVERABLE

Raggiunto lato workflow. Da verificare con push/run CI dopo aver creato il secret GitHub.
