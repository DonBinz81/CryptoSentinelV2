# Report Fix CI Pages

## 1. COSA È STATO FATTO

- Corretto il workflow `.github/workflows/build-apk.yml` per pubblicare la pagina sul branch `gh-pages`.
- Mantenuta la regola di deploy solo da `main` tramite `if: github.ref == 'refs/heads/main'`.
- Rimosso l'uso di `actions/deploy-pages` e dell'ambiente protetto `github-pages`, che causava il rifiuto del deploy.
- Aggiornato `docs/PROJECT_STRUCTURE.md`.

## 2. COME È STATO FATTO

- Il job `deploy-pages` continua a dipendere dal job `build`.
- Il job `deploy-pages` scarica l'artifact `CryptoSentinel-debug.apk`, prepara `pages-dist`, copia `docs/index.html` e l'APK.
- La pubblicazione usa `peaceiris/actions-gh-pages@v4` con `publish_branch: gh-pages`.
- Il job ha permesso `contents: write`, necessario per aggiornare il branch `gh-pages`.

## 3. COSA È STATO VERIFICATO

- Verificato che il deploy Pages sia ancora limitato a `main`.
- Verificato che non siano più presenti `environment: github-pages`, `pages: write` o `id-token: write` nel job Pages.
- Verifica remota finale da eseguire dopo push: nuova run GitHub Actions su `main`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno sul comportamento richiesto: ogni build su `main` deve aggiornare la pagina.
- Cambia solo il meccanismo tecnico: branch `gh-pages` invece di ambiente protetto `github-pages`.

## 5. QUESTIONI APERTE

- Confermare nelle impostazioni del repository che GitHub Pages usa il branch `gh-pages` come sorgente.

## 6. STATO DELIVERABLE

Raggiunto lato configurazione workflow; da confermare con run CI dopo push.
