# Report CI Artifact Release Fix

## 1. COSA È STATO FATTO

- Corretto `.github/workflows/build-apk.yml` dopo una run in cui l'APK era stato compilato ma l'artifact era stato saltato.
- Spostato `Upload APK come artefatto CI` subito dopo `Rinomina APK`.
- Resi non bloccanti gli step `Aggiorna release dev` e `Pubblica release latest`.
- Aggiornato `docs/PROJECT_STRUCTURE.md`.

## 2. COME È STATO FATTO

- L'artifact `CryptoSentinel-debug.apk` viene caricato prima di qualsiasi operazione `gh release`.
- Gli step release hanno `continue-on-error: true`.
- In questo modo una failure accessoria nelle release non impedisce il download dell'APK e non blocca `deploy-pages`.

## 3. COSA È STATO VERIFICATO

- La run precedente ha mostrato:
  - `Restore google-services.json`: success.
  - `Build APK debug`: success.
  - `Aggiorna release dev`: failure.
  - artifact upload: skipped perché era dopo lo step fallito.
- La correzione elimina questa dipendenza.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno sul deliverable APK. Le release GitHub sono considerate accessorie rispetto ad artifact CI e Pages.

## 5. QUESTIONI APERTE

- La nuova build va rilanciata dopo commit/push per confermare artifact e Pages.
- Se serve una release GitHub sempre aggiornata, va analizzato separatamente il motivo del fallimento `gh release`.

## 6. STATO DELIVERABLE

Raggiunto lato workflow; da verificare con nuova run CI.
