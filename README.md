# CryptoSentinelV2 — Market Watch

**CryptoSentinelV2** è un'app Android per monitorare i prezzi delle criptovalute in tempo reale e ricevere notifiche personalizzate quando il mercato si muove.

---

## Funzionalità principali

### Monitoraggio prezzi
- Lista aggiornabile delle top criptovalute per capitalizzazione (fino a 600)
- Prezzi in tempo reale tramite backend multi-provider, con CoinGecko predefinito e CMC riservabile all'agente
- Supporto multi-valuta: USD, EUR e BTC
- Ricerca rapida per nome o simbolo
- Pull-to-refresh manuale

### Grafici
- Grafico a linea e a candele per ogni coin
- Timeframe selezionabile: 1 giorno, 7 giorni, 30 giorni, 1 anno
- Linee di soglia degli alert sovrapposte al grafico
- Si apre toccando il nome della coin, si chiude scorrendo verso il basso

### Alert di prezzo
- **Soglia fissa** — notifica quando il prezzo supera o scende sotto un valore
- **Variazione percentuale** — notifica su variazione % rispetto al prezzo attuale
- **Range** — notifica quando il prezzo entra o esce da un intervallo definito
- Note personalizzate su ogni alert
- Toggle per attivare/disattivare singoli alert senza cancellarli
- Storico degli ultimi 50 alert scattati

### Preferiti
- Aggiunta di coin ai preferiti con monitoraggio separato
- Alert di movimento percentuale sui preferiti (rialzo e ribasso configurabili)
- Popup di notifica in-app al rilevamento del movimento

### Notifiche
- Notifiche FCM server-side anche con app chiusa o in background
- Controllo alert backend ogni 60 secondi per soglie, range e movimenti preferiti
- Visualizzazione push anche quando l'app è in foreground
- Canale notifiche dedicato con vibrazione e suono

### Altro
- Schermata di benvenuto animata all'avvio (solo al cold start)
- Aggiornamenti in-app scaricabili direttamente dall'app
- Supporto per l'ottimizzazione batteria con accesso diretto alle impostazioni Android

---

## Stack tecnologico

| Livello | Tecnologia |
|---|---|
| Frontend | React 19 + TypeScript + Vite |
| Stile | Tailwind CSS |
| Grafici | TradingView Lightweight Charts v5 |
| Mobile | Capacitor 8 (Android) |
| Backend | Python + FastAPI |
| Background | Task asincrono backend |
| Notifiche | Firebase Cloud Messaging + Capacitor Local Notifications |
| Dati | Backend multi-provider CMC/CoinGecko |

---

## Requisiti

- **Android** 7.0+ (API 24)
- Compilato con SDK 36 (Android 16)
- Backend FastAPI configurato e raggiungibile per registrazione device e alert FCM

---

## Build locale

### Prerequisiti
- Node.js 18+
- Android Studio con SDK 36
- Java 17+

### Comandi

```bash
# Installa le dipendenze
npm install

# Build web
npm run build

# Sincronizza con il progetto Android
npx cap sync android

# Apri in Android Studio
npx cap open android
```

Per il dev server web (senza Android):
```bash
npm run dev
```

---

## Struttura del progetto

```
src/
├── components/        # Componenti UI React
│   ├── CoinCard       # Card singola coin con prezzo e variazioni
│   ├── CoinChartSheet # Bottom sheet con grafico e alert della coin
│   ├── AlertModal     # Modale creazione/modifica alert
│   ├── AlertsTab      # Lista di tutti gli alert attivi e storico
│   ├── SplashOverlay  # Schermata di avvio animata
│   └── ...
├── hooks/             # Custom hooks
│   ├── useCryptoData  # Fetch e polling prezzi dal backend normalizzato
│   ├── useCoinChart   # Fetch dati storici per il grafico
│   ├── useAlerts      # Gestione alert di soglia
│   ├── useRangeAlerts # Gestione alert di range
│   └── useFavoritePriceAlerts  # Alert movimento sui preferiti
└── utils/
    ├── alertSync      # Sincronizzazione configurazione alert al backend
    ├── notifications  # Registrazione FCM e notifiche locali foreground
    └── update         # Comunicazione con il plugin nativo AppSettings

backend/app/notifications/
├── alert_store.py     # Configurazione alert e stato checker persistiti
├── price_checker.py   # Controllo prezzi ogni 60 secondi e invio FCM
├── service.py         # Orchestrazione notifiche
└── fcm/               # Client Firebase e registro device token

android/app/src/main/java/com/cryptosentinelv2/app/
├── MainActivity.java       # Entry point Android
└── AppSettingsPlugin.java  # Plugin Capacitor per funzionalità native
```

---

## Note sull'API

L'app usa il backend normalizzato con il provider globale selezionato. CoinGecko è il default per mercato e alert; CMC resta disponibile per funzioni agente/resolver con budget base protetto da cache e rate limiter.

---

## Licenza

Uso personale. Non affiliato con CoinMarketCap o CoinGecko.
