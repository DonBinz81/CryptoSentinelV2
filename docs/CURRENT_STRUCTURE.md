# CURRENT STRUCTURE

Ultimo aggiornamento: 2026-06-10

Questo documento fotografa lo stato attuale di CryptoSentinel prima dell'integrazione del nuovo progetto hackathon. Descrive solo cio' che e' presente nel repository, separandolo dai target futuri indicati in `plans/Plan_forHackathon.md`.

## 1. STRUTTURA CARTELLE ATTUALE

```text
CryptoSentinelHackathon/ - app CryptoSentinel esistente, frontend React/Vite con wrapper Android Capacitor.
|-- .github/ - configurazioni GitHub.
|   `-- workflows/ - automazioni CI/CD.
|       `-- build-apk.yml - workflow per compilare/pubblicare APK Android.
|-- android/ - progetto Android Capacitor con codice nativo custom.
|   |-- app/ - modulo Android principale.
|   |   |-- src/ - sorgenti e risorse Android.
|   |   |   |-- androidTest/ - test strumentali Android.
|   |   |   |   `-- java/com/getcapacitor/myapp/ExampleInstrumentedTest.java - test strumentale di esempio.
|   |   |   |-- main/ - app Android effettiva.
|   |   |   |   |-- AndroidManifest.xml - dichiara activity, BootReceiver, FileProvider e permessi Android.
|   |   |   |   |-- java/com/cryptosentinelai/app/ - codice nativo Java custom.
|   |   |   |   |   |-- MainActivity.java - entrypoint Android; registra plugin, imposta status bar, pulisce cache su update, schedula worker.
|   |   |   |   |   |-- AppSettingsPlugin.java - bridge Capacitor per impostazioni, download APK, sync alert, apertura link/download.
|   |   |   |   |   |-- PriceCheckWorker.java - WorkManager ogni 15 minuti per controllare alert/preferiti anche in background.
|   |   |   |   |   `-- BootReceiver.java - riattiva il worker dopo il riavvio del dispositivo.
|   |   |   |   `-- res/ - risorse Android: icone launcher, splash, layout, XML, stringhe e stili.
|   |   |   `-- test/ - test unitari JVM Android.
|   |   |       `-- java/com/getcapacitor/myapp/ExampleUnitTest.java - test unitario di esempio.
|   |   |-- build.gradle - configurazione modulo Android, versioning, signing debug e dipendenze native.
|   |   |-- capacitor.build.gradle - integrazione Gradle generata da Capacitor.
|   |   |-- debug.keystore - keystore debug locale.
|   |   `-- proguard-rules.pro - regole ProGuard/R8.
|   |-- gradle/wrapper/ - Gradle wrapper.
|   |   |-- gradle-wrapper.jar - runtime wrapper.
|   |   `-- gradle-wrapper.properties - distribuzione Gradle usata.
|   |-- build.gradle - configurazione Gradle root.
|   |-- capacitor.settings.gradle - inclusione moduli Capacitor.
|   |-- gradle.properties - proprieta' Gradle.
|   |-- gradlew - wrapper Gradle Unix.
|   |-- gradlew.bat - wrapper Gradle Windows.
|   |-- settings.gradle - settings progetto Android.
|   `-- variables.gradle - versioni SDK e librerie Android condivise.
|-- docs/ - documentazione esistente e documenti di revisione.
|   |-- CURRENT_STRUCTURE.md - fotografia dello stato attuale prima dell'integrazione.
|   |-- PROJECT_STRUCTURE.md - documento di riferimento aggiornato a ogni step.
|   |-- Strategia_Perpetual.md - note strategia perpetual futura.
|   |-- Strategia_Spot.md - note strategia spot futura.
|   `-- index.html - pagina statica/documentale.
|-- plans/ - piani operativi.
|   `-- Plan_forHackathon.md - piano target per evoluzione in agente autonomo BNB hackathon.
|-- public/ - asset statici serviti/copiati da Vite.
|   |-- icons/ - icone PWA/app.
|   |   |-- icon-192.png - icona 192x192.
|   |   `-- icon-512.png - icona 512x512.
|   |-- crypto-icon.svg - icona crypto.
|   |-- favicon.svg - favicon.
|   |-- icons.svg - set icone vettoriali.
|   |-- manifest.json - manifest PWA con nome, colori, orientamento e icone.
|   |-- splash.html - splash page statica.
|   `-- sw.js - service worker statico.
|-- scripts/ - script di supporto.
|   `-- gen-icons.mjs - generazione asset icone.
|-- src/ - frontend React/TypeScript.
|   |-- assets/ - immagini importate dal bundle.
|   |   |-- hero.png - immagine hero/app.
|   |   |-- react.svg - asset React standard.
|   |   `-- vite.svg - asset Vite standard.
|   |-- components/ - componenti UI.
|   |   |-- AlertModal.tsx - creazione/modifica alert di soglia e range.
|   |   |-- AlertsTab.tsx - lista alert, storico e gestione alert range.
|   |   |-- CoinCard.tsx - card singola coin con prezzo, variazioni, preferito, alert e grafico.
|   |   |-- CoinChartSheet.tsx - bottom sheet grafico line/candle con alert sovrapposti.
|   |   |-- EnergySavingBanner.tsx - banner per impostazioni risparmio energetico Android.
|   |   |-- FavMovePopup.tsx - popup in-app per movimento significativo dei preferiti.
|   |   |-- LogoLighthouse.tsx - logo UI.
|   |   |-- Navbar.tsx - navigazione tab dashboard/preferiti/alert/settings.
|   |   |-- NotificationBanner.tsx - richiesta/stato permessi notifiche.
|   |   |-- SettingsTab.tsx - impostazioni refresh, valuta, alert preferiti, update e pulizia dati.
|   |   |-- SplashOverlay.tsx - splash animata al cold start.
|   |   `-- UpdateNotification.tsx - banner aggiornamento APK disponibile.
|   |-- hooks/ - logica applicativa React.
|   |   |-- useAlerts.ts - alert a soglia, storico, notifiche e sync nativo.
|   |   |-- useCoinChart.ts - fetch dati market chart/OHLC CoinGecko per grafici.
|   |   |-- useCryptoData.ts - polling CoinGecko markets, cache e paginazione.
|   |   |-- useCurrency.ts - valuta selezionata.
|   |   |-- useFavoritePriceAlerts.ts - alert percentuali sui preferiti.
|   |   |-- useFavorites.ts - gestione preferiti in localStorage.
|   |   |-- usePullToRefresh.ts - gesture pull-to-refresh.
|   |   |-- useRangeAlerts.ts - alert ingresso/uscita range con cooldown.
|   |   `-- useSearch.ts - ricerca coin tramite API CoinGecko.
|   |-- utils/ - integrazioni e utility.
|   |   |-- audio.ts - feedback sonoro per alert.
|   |   |-- energySaving.ts - apertura/stato impostazioni batteria.
|   |   |-- haptics.ts - feedback aptico Capacitor.
|   |   |-- notifications.ts - notifiche locali e bridge notifiche/impostazioni.
|   |   `-- update.ts - check release GitHub, download APK, sync alert nativi.
|   |-- App.tsx - orchestrazione stato UI, tab, dati, alert, preferiti, update e bridge nativo.
|   |-- index.css - CSS globale e Tailwind.
|   |-- main.tsx - mount React.
|   |-- types.ts - tipi Coin, PriceAlert, RangeAlert e storico.
|   `-- vite-env.d.ts - tipi ambiente Vite.
|-- .gitignore - esclusioni Git.
|-- capacitor.config.ts - appId `com.cryptosentinelai.app`, nome app, webDir `dist`.
|-- eslint.config.js - configurazione lint.
|-- index.html - entrypoint HTML Vite.
|-- LICENSE - licenza.
|-- package-lock.json - lockfile npm.
|-- package.json - script e dipendenze npm.
|-- postcss.config.js - configurazione PostCSS.
|-- README.md - descrizione funzionale attuale dell'app.
|-- tailwind.config.js - configurazione tema Tailwind.
|-- tsconfig.app.json - TypeScript app.
|-- tsconfig.json - TypeScript root.
|-- tsconfig.node.json - TypeScript tooling/config.
`-- vite.config.ts - configurazione Vite, React plugin e costanti build.
```

## 2. STACK ATTUALE

### Frontend e mobile

| Tecnologia | Versione/config | Uso attuale |
|---|---:|---|
| React | ^19.2.6 | UI mobile/web. |
| React DOM | ^19.2.6 | Rendering DOM. |
| TypeScript | ~6.0.2 | Tipizzazione frontend/config. |
| Vite | ^8.0.12 | Dev server e build web. |
| Tailwind CSS | ^3.4.19 | Styling utility-first. |
| PostCSS / Autoprefixer | ^8.5.15 / ^10.5.0 | Pipeline CSS. |
| Capacitor Core | ^8.3.4 | Bridge web/native. |
| Capacitor Android | ^8.3.4 | Target Android. |
| Capacitor CLI | ^8.3.4 | Sync/build piattaforme. |
| Capacitor Haptics | ^8.0.2 | Feedback aptico. |
| Capacitor Local Notifications | ^8.2.0 | Notifiche locali native. |
| lightweight-charts | ^5.2.0 | Grafici lineari e candlestick. |
| qrcode | ^1.5.4 | Generazione QR code, presente come dipendenza. |

### Tooling

| Tecnologia | Versione | Uso attuale |
|---|---:|---|
| ESLint | ^10.3.0 | Linting. |
| @vitejs/plugin-react | ^6.0.1 | Supporto React in Vite. |
| typescript-eslint | ^8.59.2 | Lint TypeScript. |
| eslint-plugin-react-hooks | ^7.1.1 | Regole hooks. |
| eslint-plugin-react-refresh | ^0.5.2 | Regole React Refresh. |
| canvas | ^3.2.3 | Supporto generazione asset/script. |
| @types/node | ^24.12.3 | Tipi Node. |
| @types/react / @types/react-dom | ^19.2.14 / ^19.2.3 | Tipi React. |
| @types/qrcode | ^1.5.6 | Tipi QR code. |

### Android nativo

| Componente | Versione/config | Uso attuale |
|---|---:|---|
| minSdkVersion | 24 | Android 7.0 minimo. |
| compileSdkVersion | 36 | SDK compilazione. |
| targetSdkVersion | 36 | Target Android. |
| androidx.work:work-runtime | 2.9.0 | Worker periodico background. |
| androidx.appcompat | 1.7.1 | Compatibilita' Android. |
| androidx.coordinatorlayout | 1.3.0 | Layout support. |
| androidx.core:core-splashscreen | 1.2.0 | Splash screen Android. |
| cordovaAndroidVersion | 14.0.1 | Compatibilita' plugin Cordova/Capacitor. |
| JUnit / AndroidX Test / Espresso | 4.13.2 / 1.3.0 / 3.7.0 | Test Android di base. |

### Servizi esterni attuali

| Servizio | Uso attuale |
|---|---|
| CoinGecko API | Fonte dati prezzi, market list, ricerca e grafici OHLC/market chart. |
| GitHub Releases API | Check update APK tramite release `latest` e tag `dev`. |
| GitHub Pages | URL APK pubblico `https://iridexx.github.io/CryptoSentinel/CryptoSentinel-debug.apk`. |

## 3. FUNZIONALITA' ESISTENTI

| Area | Stato attuale |
|---|---|
| Monitoraggio prezzi | Lista crypto da CoinGecko ordinata per market cap, paginazione 50/100/200/400/600, polling configurabile, cache locale. |
| Valute | Supporto USD, EUR e BTC tramite hook valuta e query CoinGecko. |
| Ricerca | Ricerca coin tramite `useSearch`, separata dalla lista principale. |
| Ordinamento | Rank, variazione 24h, variazione 7g, volume e prezzo. |
| Timeframe UI | 1h, 24h e 7g per visualizzazione variazioni nella dashboard. |
| Pull-to-refresh | Refresh manuale con gesture mobile. |
| Preferiti | Gestione lista preferiti in locale, tab dedicata e contatore in navbar. |
| Alert soglia | Alert sopra/sotto prezzo, note, modifica, reset, toggle attivo/disattivo, storico ultimi 50 eventi. |
| Alert percentuali | Creazione alert con variazione percentuale rispetto al prezzo corrente tramite modale. |
| Alert range | Notifica ingresso/uscita da intervallo prezzo con cooldown. |
| Alert preferiti | Soglie percentuali rialzo/ribasso sui preferiti con popup in-app e notifiche. |
| Grafici | Bottom sheet con grafico lineare o candlestick via CoinGecko e `lightweight-charts`; overlay soglie alert. |
| Notifiche foreground | Notifiche locali Capacitor quando l'app e' aperta/native platform disponibile. |
| Notifiche background Android | WorkManager nativo ogni 15 minuti controlla alert, range e preferiti anche con app chiusa. |
| Persistenza locale | `localStorage` frontend e `SharedPreferences` Android per sync dati alert/preferiti. |
| Riavvio dispositivo | `BootReceiver` ripristina worker dopo boot. |
| Aggiornamenti app | Check release GitHub, download APK tramite Android DownloadManager e install intent. |
| Ottimizzazione batteria | Banner e plugin per aprire impostazioni batteria/notifiche. |
| Feedback UX | Splash cold start, haptic feedback, beep alert, animazione variazione rank. |

## 4. FILE CHIAVE

| File | Descrizione |
|---|---|
| `src/App.tsx` | Componente root; coordina tab, polling dati, alert, preferiti, update, notifiche e bridge Android. |
| `src/types.ts` | Tipi dati principali: Coin, PriceAlert, RangeAlert e storico alert. |
| `src/hooks/useCryptoData.ts` | Fetch e polling CoinGecko markets con cache, paginazione e retry soft. |
| `src/hooks/useCoinChart.ts` | Fetch CoinGecko market chart/OHLC per grafici line/candle. |
| `src/hooks/useAlerts.ts` | Gestione alert soglia, storico, notifiche locali e sync al worker nativo. |
| `src/hooks/useRangeAlerts.ts` | Gestione alert range con stato dentro/fuori e cooldown. |
| `src/hooks/useFavoritePriceAlerts.ts` | Rileva movimenti percentuali sui preferiti e aggiorna prezzi di riferimento. |
| `src/hooks/useFavorites.ts` | Persistenza e toggle preferiti. |
| `src/hooks/useCurrency.ts` | Gestione valuta selezionata. |
| `src/hooks/useSearch.ts` | Ricerca coin. |
| `src/components/CoinCard.tsx` | Rendering card coin e azioni principali. |
| `src/components/CoinChartSheet.tsx` | UI grafico coin e gestione alert dal grafico. |
| `src/components/AlertModal.tsx` | Creazione alert soglia, percentuale e range. |
| `src/components/AlertsTab.tsx` | Gestione alert attivi, range alert e storico. |
| `src/components/SettingsTab.tsx` | Impostazioni refresh, valuta, notifiche, alert preferiti, update e reset dati. |
| `src/utils/notifications.ts` | Canale notifiche locali, permessi e invio notifiche alert/range/preferiti. |
| `src/utils/update.ts` | Check GitHub release, download APK e sync alert/range verso Android. |
| `src/utils/energySaving.ts` | Integrazione impostazioni risparmio energetico. |
| `src/utils/haptics.ts` | Feedback aptico. |
| `android/app/src/main/java/com/cryptosentinelai/app/MainActivity.java` | Avvio Android, registrazione plugin e scheduling worker. |
| `android/app/src/main/java/com/cryptosentinelai/app/AppSettingsPlugin.java` | Plugin Capacitor custom per impostazioni, download APK, alert sync e link esterni. |
| `android/app/src/main/java/com/cryptosentinelai/app/PriceCheckWorker.java` | Worker nativo per controlli prezzo background e notifiche Android. |
| `android/app/src/main/java/com/cryptosentinelai/app/BootReceiver.java` | Ripristino worker al boot. |
| `android/app/src/main/AndroidManifest.xml` | Permessi e componenti Android dichiarati. |
| `package.json` | Script npm e dipendenze frontend/mobile. |
| `vite.config.ts` | Build Vite e costanti `__APP_VERSION__`, `__APP_BUILD_DATE__`, `__APP_BUILD_NUMBER__`. |
| `capacitor.config.ts` | Configurazione app Capacitor Android. |
| `android/app/build.gradle` | Configurazione build Android, SDK, version code/name e dipendenze native. |
| `plans/Plan_forHackathon.md` | Piano target per evoluzione in agente autonomo. |

## 5. COSA MANCA RISPETTO AL PIANO

| Area target | Stato attuale | Gap da colmare |
|---|---|---|
| Backend FastAPI | Assente | Creare backend Python/FastAPI con API autenticata, health check, logging strutturato e heartbeat. |
| Database | Assente lato server | Introdurre SQLite/PostgreSQL per utenti, configurazioni, trade, decisioni, posizioni, PnL snapshot e log. |
| Autenticazione API | Assente | Implementare token read-only/admin e canale sicuro mobile/dashboard-backend. |
| CoinMarketCap | Assente | Migrare dati da CoinGecko a CMC API/CMC MCP, con rate limit, caching e accounting crediti. |
| Agente AI | Assente | Implementare brain Claude meta-controller, signal engine, loop veloce/lento, modalita' degradata. |
| Strategie trading | Solo documentate | Codificare strategia spot momentum/VWAP/ATR e strategia perp volume profile/mean reversion. |
| Risk management trading | Assente | Guardrail capitale, drawdown, max posizioni, slippage, liquidita', gas reserve, daily loss limit e kill switch. |
| Execution spot | Assente | Integrare Trust Wallet Agent Kit per signing ed esecuzione spot su BSC. |
| Execution perpetual | Assente | Integrare BNB AI Agent SDK o EIP-712 per perpetual. |
| Registrazione gara | Assente | Implementare/runbook `twak compete register` o MCP `competition_register` e verifica on-chain. |
| x402 | Assente | Aggiungere pagamento dati/servizi x402 su BSC o fallback secondo piano. |
| Wallet/accounting | Assente | Gestire wallet BSC/Base, balance, gas, USDC x402, asset in-scope e riconciliazione on-chain. |
| Dashboard web completa | Assente | Creare dashboard Vite separata/completa con viste Spot, Perp, Globale, System Health, log viewer, replay/export. |
| Mobile agent UI | Assente | Aggiungere viste Spot/Perp/Globale, impostazioni agente, stato AI, onboarding credenziali e kill switch. |
| FCM server-side | Assente | Migrare notifiche critiche a Firebase Cloud Messaging lato backend 24/7. |
| Observability | Limitata | Aggiungere logging strutturato, metriche servizi, carburante, errori, tx hash, decision log e export revisione. |
| i18n | Assente | Estrarre testi hardcoded italiani e introdurre inglese default con italiano conservato. |
| Sicurezza credenziali | Assente lato backend | Definire `.env.example`, gestione segreti, private key cifrata, chmod 600, gitignore e policy no-secret. |
| Deploy VPS | Assente | Preparare systemd/reverse proxy/HTTPS/backup/NTP per operativita' 24/7. |
| Test end-to-end trading | Assente | Aggiungere dry-run, testnet BSC, test scaling mainnet e verifiche vincoli gara. |

## Sintesi baseline

CryptoSentinel oggi e' una app mobile locale-first di market monitoring: legge CoinGecko, salva stato localmente, usa Capacitor per notifiche locali e WorkManager Android per controlli in background. Non e' ancora un sistema agentico: mancano backend, database, CMC, AI brain, execution on-chain, dashboard operativa, risk engine, FCM server-side e infrastruttura 24/7.
