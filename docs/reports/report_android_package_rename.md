# Report Android Package Rename

## 1. COSA È STATO FATTO

- Rinominato l'app id Android da `com.cryptosentinel.app` a `com.cryptosentinelai.app`.
- Aggiornati `namespace` e `applicationId` in `android/app/build.gradle`.
- Aggiornato `appId` in `capacitor.config.ts`.
- Aggiornate le stringhe Android `package_name` e `custom_url_scheme`.
- Spostati i sorgenti Java da `android/app/src/main/java/com/cryptosentinel/app/` a `android/app/src/main/java/com/cryptosentinelai/app/`.
- Aggiornate le dichiarazioni `package` nei file Java nativi.
- Aggiornati `docs/PROJECT_STRUCTURE.md` e `docs/CURRENT_STRUCTURE.md`.

## 2. COME È STATO FATTO

- Il cambio è stato applicato su tutti i punti che definiscono identità Android e package Java.
- Il percorso fisico dei sorgenti Java è stato allineato al nuovo package per evitare incoerenze con Gradle/Android Studio.
- Non sono stati modificati segreti, `.env`, service account o file in `secrets/`.

## 3. COSA È STATO VERIFICATO

- Ricerca repository dei riferimenti al vecchio package.
- Verificata presenza dei sorgenti Java nel nuovo path `com/cryptosentinelai/app`.
- Verificato che i riferimenti attivi in Android/Capacitor puntino a `com.cryptosentinelai.app`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno. È una correzione necessaria per evitare collisione con l'app/fork esistente.

## 5. QUESTIONI APERTE

- Firebase richiede una nuova Android app registrata con package `com.cryptosentinelai.app`.
- Il relativo `google-services.json` dovrà essere generato e gestito fuori repo o tramite GitHub Secrets, mai committato.
- La build APK va verificata in GitHub Actions dopo commit/push.

## 6. STATO DELIVERABLE

Raggiunto lato codice/configurazione locale; build CI da verificare dopo push.
