# Plan_forHackathon

> **Documento operativo per lo sviluppo del progetto BNB Hack — Track 1: Autonomous Trading Agents**
> Destinatario: AI interna che svilupperà l'integrazione del codice.
> Lingua: italiano. Codice e interfacce: inglese.
> Questo documento è la fonte di verità del progetto. Va letto integralmente prima di scrivere codice.

---

## A. EXECUTIVE SUMMARY

### Cosa costruiamo
Un **agente di trading autonomo** su **BNB Smart Chain (BSC)** che:
1. Legge dati e segnali di mercato (CoinMarketCap)
2. Decide in autonomia tramite un modello AI (Claude) usato come **meta-controller**
3. Firma ed esegue trade in autonomia (Trust Wallet Agent Kit per lo spot, BNB AI Agent SDK / EIP-712 per i perp)
4. Opera entro regole di rischio rigide, monitorabile da app mobile e dashboard web

### Il punto di partenza
Il progetto è un **fork/evoluzione di CryptoSentinel**, un'app mobile esistente (React + TypeScript + Capacitor/Android) di monitoraggio prezzi crypto con sistema di alert. Attualmente usa CoinGecko, è in italiano, e non ha backend.

### La narrativa (importante per i giudici)
**"Da app che ti avvisa → app che agisce per te."**
Non è l'ennesimo trading bot costruito da zero: è un'app di monitoraggio reale che evolve in agente autonomo. Gli alert di volatilità già esistenti diventano il **trigger** dell'agente. Questo dà originalità + real-world relevance, due criteri di giudizio.

---

## B. OBIETTIVI HACKATHON + PREMI

### Track 1 — Autonomous Trading Agents
- Gara di trading live su BSC, valutata su **PnL reale + drawdown** (vedi sotto)
- Premi: 1° $10.000, 2° $6.000, 3° $4.000, 4°-5° $2.000

### Premi speciali (cumulabili, $2.000 ciascuno) — obiettivi di design
- **Best Use of TWAK**: TWAK come unico execution layer dello spot, signing self-custody, autonomous mode, x402. → puntiamo a questo con lo spot.
- **Best Use of Agent Hub (CMC)**: uso sostanziale di CMC (dati, MCP, x402). → coperto.
- **Best Use of BNB AI Agent SDK**: integrazione inventiva dell'SDK. → puntiamo con identità on-chain + moduli + perp execution.

### Filosofia di scoring (da chiarimenti organizzatori)
- Vince **massimo PnL con minimo drawdown** (risk-adjusted, non PnL grezzo)
- Il drawdown conta quanto il profitto → privilegiare CONSISTENZA su aggressività
- "Make it look good": la **presentazione conta** (dashboard, demo, UX curata fanno punteggio)
- Principio operativo: **il drawdown è funzione del tempo di reazione** → reattività come variabile di rischio

---

## C. VINCOLI HARD DI QUALIFICAZIONE (MAI VIOLARE)

Questi vincoli sono assoluti. Il codice deve garantirli sempre, come regole hardcoded non disattivabili:

1. **Registrazione on-chain** entro l'apertura della trading window (via `twak compete register` o MCP `competition_register`). Contratto: `0x212c61b9b72c95d95bf29cf032f5e5635629aed5` su BSC.
2. **Minimo 1 trade al giorno** (7 nella settimana di gara) → regola heartbeat hardcoded.
3. **Balance non-zero** di asset in-scope all'inizio della gara.
4. **Mai portafoglio ≤ $1**: ogni ora che inizia con portafoglio ≤ $1 conta 0% → guardia hardcoded che impedisce di scendere sotto una soglia di sicurezza.
5. **Solo i 149 token eligible** (lista in appendice). Trade fuori lista non contano.
6. **Spiegazione strategia** da fornire su DoraHacks.

### Chiarimenti organizzatori (dal Telegram BNB Hack — aggiornato 16 giugno 2026)

- **Esecuzione obbligatoria on-chain via TWAK.** Confermato dagli organizzatori: i trade della gara devono essere eseguiti on-chain tramite Trust Wallet Agent Kit. NON è ammessa esecuzione su exchange centralizzati. Conseguenza: un eventuale percorso DEX diretto (es. PancakeSwap via web3.py) può servire per TEST locali, ma i trade ufficiali della gara DEVONO passare per TWAK.
- **Fee TWAK ridotte durante la gara:** da 0.7% a 0.077% per la settimana di trading (22-28 giugno). Riduce l'impatto delle fee sulle strategie spot (prima servivano movimenti del ~3% per coprire le fee).
- **403 Forbidden su API swap TWAK — problema noto e diffuso.** Molti partecipanti con piano Free di `portal.trustwallet.com` ricevono 403 su tutti gli endpoint autenticati `tws.trustwallet.com` (swap, providers, prezzi via API), mentre le operazioni locali (wallet address) e `twak price` funzionano. Il codice di firma HMAC del progetto è verificato corretto contro il sorgente ufficiale. Risoluzione in carico a Trust Wallet/organizzatori. **Blocco esterno, non di codice.**
- **Spot vs Perp nel PnL ranking:** DA CONFERMARE. Domanda posta agli organizzatori, in attesa di risposta. Determina la priorità tra strategia spot e perpetual nello Step 6.

---

## D. ARCHITETTURA COMPLETA

```
┌─────────────────────┐     ┌──────────────────────┐
│   APP MOBILE         │     │  DASHBOARD WEB UNICA  │
│ React+TS+Capacitor   │     │  React + Vite         │
│ (telefono, essenziale│     │ (browser desktop/Mac, │
│  + funzioni agente)  │     │  TUTTO: monitoring +  │
│                      │     │  agente + health +    │
│                      │     │  log + replay + export│
└──────────┬───────────┘     └───────────┬───────────┘
           │      HTTPS + auth token      │
           │   (due client, stesso backend)│
           └──────────────┬───────────────┘
                          ▼
           ┌──────────────────────────────┐
           │   BACKEND FastAPI (Python)    │
           │  - API autenticata           │
           │  - Logging strutturato       │
           │  - Health check / heartbeat  │
           ├──────────────────────────────┤
           │  AGENTE                       │
           │  - Brain (Claude meta-ctrl)  │
           │  - Signal engine (modulare)  │
           │  - Risk management           │
           │  - Loop veloce / loop lento  │
           ├──────────────────────────────┤
           │  ESECUZIONE                   │
           │  - Spot → TWAK               │
           │  - Perp → BNB SDK / EIP-712  │
           │  - x402 (BSC) pagamenti      │
           ├──────────────────────────────┤
           │  PERSISTENZA                  │
           │  - DB (Spot/Perp/Globale)    │
           │  - PnL snapshot orari        │
           ├──────────────────────────────┤
           │  NOTIFICHE                    │
           │  - FCM server-side 24/7      │
           └──────────────┬───────────────┘
                          ▼
   CMC (dati) · BSC/PancakeSwap (trading) · Binance [V2: delta]
```

### Principi architetturali trasversali
- **Single-user ready-for-multi**: costruire per un utente, ma DB con `user_id` (costante per ora) e credenziali isolabili, così il multi-user è un'estensione non una riscrittura.
- **i18n**: testi non hardcoded, file di traduzione. Inglese di default, italiano conservato.
- **Signal engine modulare**: ogni componente del segnale è una fonte indipendente con fallback; aggiungere fonti (delta, relative strength) in V2 è un inserimento, non una riscrittura.
- **Blockchain = fonte di verità**: mai assumere lo stato, sempre verificare on-chain.
- **Build for one, design for many**: predisporre senza sovra-ingegnerizzare.

---

## E. STACK TECNOLOGICO + CREDENZIALI

| Layer | Tecnologia |
|---|---|
| Frontend mobile | React, TypeScript, Capacitor (Android) |
| Dashboard web | Vite |
| Backend | Python, FastAPI |
| AI | Claude API (meta-controller) |
| Dati mercato | CoinMarketCap (piano Startup: OHLCV storico) + CMC MCP |
| Esecuzione spot | Trust Wallet Agent Kit (TWAK) per hackathon + PancakeSwap diretto (web3.py) per uso reale — dietro interfaccia `ExecutionProvider` astratta |
| Esecuzione perp | BNB AI Agent SDK / EIP-712 (+ futuri DEX perp) — dietro interfaccia `PerpExecutionProvider` astratta |
| Pagamenti dati | x402 (su BSC via BNB SDK; servizi terzi es. AgentData) |
| Notifiche | Firebase Cloud Messaging (FCM) |
| Database | SQLite (iniziale) o PostgreSQL (VPS) |
| Deploy | VPS Linux personale |

### Stato credenziali
| Credenziale | Stato | Posizione |
|---|---|---|
| TWAK Access ID + HMAC Secret | ✅ Disponibile | `.env` backend |
| CMC API Key (Startup) | ✅ Disponibile | `.env` backend |
| Anthropic API Key | ⏳ Da inserire all'ultimo | `.env` backend |
| Wallet BSC (private key) | ❓ Da preparare | `.env` cifrato |
| BNB per gas | ❓ Da preparare | Wallet BSC |
| USDC per x402 | ❓ Da predisporre | Wallet (BSC, eventuale Base) |

> **Sicurezza credenziali:** mai in chiaro nel repo. `.env` con `chmod 600`, sempre in `.gitignore`. Chiave privata cifrata a riposo, decifrata solo in memoria con passphrase all'avvio. Anthropic key: per l'hackathon modello single-user (chiave sul backend); architettura predisposta per chiave per-utente cifrata (modello multi-user futuro).

---

## F. STRATEGIA SPOT (sintesi — documento dedicato: Strategia_Spot.md v2.1)

Motore **momentum + struttura di prezzo**. *"Trovare i cavalli migliori e cavalcare il momentum."*

**Trigger**: volatilità + volume spike + struttura (su coin nei preferiti con flag AI).

**Motore segnale (pesi V1):**
- Trend/struttura (VWAP primario + EMA 20/50 di supporto) — 30%
- Volume relativo — 30%
- BTC context — 15%
- RSI (filtro) — 15%
- Sentiment/Fear&Greed (filtro macro) — 10%

**Entry quality (il "dove"):** VWAP (no long se prezzo > VWAP + X·ATR, anti-pump) + market structure (breakout/retest) + estensione ATR.

**Entrata:** una sola (no media in perdita; aggiunta solo se in profitto + breakout confermato).

**Uscite:** stop ATR adattivo (con cap rischio 1.5% capitale per trade — se stop troppo largo, size ridotta o trade saltato), take profit parziale + trailing, stop temporale, cooldown.

**V2:** relative strength (ranking sovraperformance), market structure completa, candle exhaustion, RSI 4h.

---

## G. STRATEGIA PERPETUAL (sintesi — documento dedicato: Strategia_Perpetual.md v3)

Motore **Volume Profile + mean reversion**. *"Precisione e microstruttura."*

**Mappa:** Rolling Volume Profile 24h su candele 5m → POC, VAH, VAL (Value Area 68%). Ricalcolo a chiusura candela (anti-overtrading).

**Strategia:** rientro in value dopo eccesso (mean reversion). Long sotto VAL / Short sopra VAH, su trigger di rientro.

**Gerarchia segnali (non pesi):**
1. Volume Profile → la mappa (dove)
2. Delta → conferma (price action in V1; delta reale Binance aggTrades futures in V2)
3. Trend/regime → filtro, **calcolato con VWAP** (non medie mobili classiche, che sono ritardate — confermato da tre revisori indipendenti)
4. Funding/OI → contesto
5. Agent (LLM) → esecuzione

**Leva:** preset 2x/3x/5x + personalizzata (cap DEX), dinamica via ATR.

**Entrata:** una sola (no DCA, no scaglionamento in V1).

**Stop (v3 — strutturale anticipato da V2):** estremo candela pre-segnale + ATR×coeff (default 0.5), con cap rischio per trade (max 1.5% capitale a stop colpito). Vincolo assoluto: stop sempre prima della liquidazione.

**Take Profit (v3 — schema a tre livelli):**
- TP1 = 50% posizione al bordo value → sposta stop a breakeven+
- TP2 = 25% posizione al POC
- TP3 = 25% trailing

**LLM poteri limitati:** valuta/riduce/blocca; NON aumenta leva, NON inverte, NON cambia parametri.

**V2:** delta reale (`orderflow_delta.py`, endpoint futures `/fapi`), HVN/LVN, filtro regime multi-timeframe su VWAP, profili multipli, entrate scaglionate (con backtest), whale/liquidity flow.

> **Nota execution:** Spot → TWAK. Perp → BNB AI Agent SDK / EIP-712 (NON TWAK). Due percorsi separati.

---

## H. RISK MANAGEMENT + GUARDRAIL

| Parametro | Default | Note |
|---|---|---|
| Capitale per trade (size) | 6% | Configurabile — size nominale allocata |
| **Rischio massimo per trade** | **1.5%** | **Perdita max a stop colpito (% capitale) — v3** |
| Max posizioni aperte | 3 | Configurabile |
| Esposizione massima totale | 30% | Tetto globale |
| Daily Loss Limit | −8% | Stop giornaliero (−5/−8/−10 per modalità) |
| Drawdown cap massimo | −15% | Prudenziale (valore gara da confermare) |
| Liquidità minima pool | $50.000 | Sotto → coin esclusa |
| Max slippage | 1% | Oltre → trade annullato |
| Correlation check | 0.8 | Evita posizioni correlate |
| Cooldown timer | 30 min | Configurabile |
| Riserva gas | 15% del BNB (+ floor minimo) | Mai tradabile |

> **Nota rischio per trade:** "6% capitale per trade" è la size massima nominale. "1.5% rischio per trade" è la perdita effettiva massima a stop colpito — se lo stop strutturale implica di più, la size viene ridotta automaticamente o il trade saltato. I due parametri operano insieme: size del 6% è il tetto, rischio dell'1.5% è il vincolo.

**Controlli aggiuntivi:**
- Check liquidità **in uscita** (poter uscire, non solo entrare)
- Stima costo/beneficio (skip se gas > profitto atteso)
- Filtro liquidità per attivazione Volume Profile (solo token liquidi)
- Daily Loss Limit come circuit breaker giornaliero
- Esposizione massima come tetto indipendente

---

## I. IMPOSTAZIONI CONFIGURABILI (lista completa)

```
GENERALI
├── Modalità agente: Conservativa / Semi-autonoma / Full autonoma
├── Mercato: Spot / Perpetual / Entrambi
├── Whitelist coin (auto da preferiti + flag AI)
└── Orario operativo (griglia 1-24h, tap per disabilitare)

MODALITÀ OPERATIVA
├── Network: Testnet / Mainnet
├── Esecuzione: Dry-Run / Live
├── Provider dati: CMC / CoinGecko (selettore globale, impostazioni sviluppatore)
├── Provider esecuzione: TWAK / PancakeSwap (selettore globale, impostazioni sviluppatore)
└── Test Scaling %: 10-100% (solo in Live)

RISCHIO
├── Capitale per trade % (size nominale)
├── Rischio massimo per trade % (perdita max a stop colpito)
├── Max posizioni aperte
├── Esposizione massima totale %
├── Daily Loss Limit %
├── Drawdown cap %
├── Liquidità minima pool
├── Max slippage %
├── Correlation check
├── Cooldown timer
└── Riserva gas %

SPOT
├── Soglia confidence / qualità
├── Parametri trigger (% variazione, N alert, finestra)
├── Moltiplicatore ATR stop
├── Trailing distance %
├── Take profit parziale %
└── Stop temporale (ore)

PERPETUAL
├── Direzione: Solo Long / Solo Short / Long e Short
├── Leva: preset 2x/3x/5x / personalizzata
├── Leva dinamica ATR: on/off
├── Value Area % (68/70)
├── Moltiplicatore ATR stop (coeff per stop strutturale)
├── TP1 % posizione (default 50%)
├── TP2 % posizione (default 25%)
├── Trailing % posizione residua (default 25%)
└── Stop temporale (ore)
```

---

## J. SICUREZZA, RESILIENZA, MODALITÀ DEGRADATA

### Sicurezza
- Chiave privata cifrata, mai in chiaro, mai nel repo
- API backend autenticata (token read-only / admin)
- HTTPS (reverse proxy + Let's Encrypt sul VPS)
- Token approvals: mirate non illimitate, whitelist contratti DEX ufficiali (verificare gestione TWAK in autonomous mode)
- Kill switch: **Soft Stop** (blocca nuovi trade) + **Hard Stop** (chiude tutto), con conferma, accessibile da mobile e web

### Resilienza
- Stato persistente nel DB (posizioni, trade, stato agente)
- Riconciliazione all'avvio: confronta DB vs blockchain, vince la blockchain
- Trade pending/falliti/parziali: verifica on-chain, retry intelligente limitato
- Auto-restart (systemd) dopo crash
- Backup automatico DB + export configurazione, runbook ripristino rapido

### Modalità degradata ("when in doubt, don't trade")
- Fonte dati giù → niente nuove posizioni, posizioni aperte protette dagli stop meccanici
- Claude giù → niente nuove posizioni, stop meccanici attivi, fallback inference x402 opzionale
- RPC BSC giù → RPC alternativi (multi endpoint), attesa condizioni migliori
- Carburante basso (gas/USDC/crediti) → modalità risparmio + alert
- Stato "DEGRADED" visibile + alert push
- **Principio:** le protezioni (stop) NON dipendono mai dai servizi esterni

---

## K. OBSERVABILITY

### Canali di notifica (multi-canale con preferenza utente)
L'utente sceglie dove ricevere le notifiche, per categoria di severità:
```
CANALI:
├── Telefono (FCM push) → notifiche anche ad app chiusa (Step 2, garanzia primaria gara)
├── Browser / dashboard web → notifiche quando la dashboard è APERTA (Livello A, V1)
└── Entrambi

PREFERENZA UTENTE (configurabile):
├── Dove notificare: solo telefono / solo browser / entrambi
└── Predisposta per granularità per-severità (critico/warning/info) in futuro

V2 (rinviato): Web Push reale → notifiche browser anche a dashboard CHIUSA
              (service worker web + VAPID/FCM web)
```
> **Principio gara:** gli alert critici (drawdown, trade falliti, portafoglio a rischio) hanno il telefono via FCM come canale primario garantito. Il browser (Livello A) è un canale aggiuntivo comodo da desktop, non sostituisce il telefono per la criticità.

### System Health (dashboard web)
```
SERVIZI: backend, DB, CMC, Claude, TWAK, BNB SDK/RPC, x402 (stato + latenza)
OPERATIVO: loop agente, heartbeat trade giornaliero ✓/✗, guardia $1,
           daily loss margin, trade falliti, errori decisionali, anomalie
RISORSE/CARBURANTE:
├── Crediti CMC (residui, consumo/giorno, giorni rimanenti, warning <30% / critico <10%)
├── Claude API (costo, token, warning soglia)
├── USDC x402 (saldo, spesa/giorno, warning/critico)
└── Gas BNB (saldo, trade stimati, critico sotto minimo)
ALERT: 🔴 critico (push FCM) / 🟡 warning (dashboard) / 🟢 info (log)
```

### Logging (dalle fondamenta)
- Strutturato: timestamp UTC, livello, componente, messaggio, contesto
- Cosa: ogni ciclo decisionale, ogni tx (+ hash), ogni chiamata API (+ esito/latenza), errori (+ stack), cambi stato, eventi sicurezza
- Filtrabile, consultabile in dashboard, esportabile, rotazione automatica
- Distinto dal log decisionale (narrativo, per giudici)

### Demo/Replay (dashboard web) — dettagliato
Per ogni trade, replay completo: contesto → trigger → dati letti (con fonte/costo) → ragionamento Claude (confidence + motivazione) → esecuzione (approval, firma, swap, tx hash → bsctrace, slippage, gas) → gestione posizione (timeline) → chiusura → prova on-chain (tutti i tx hash + indirizzo wallet). Riusabile per il video demo della submission.

### Export spiegazione strategia (per i giudici)
Report esportabile: logica agente in chiaro + performance sintetica + esempi di decisioni reali + prove on-chain. Generato dai dati reali.

### Viste dati (mobile + web)
```
SPOT: PnL spot · posizioni spot · storico · win rate
PERP: PnL perp · posizioni (long/short, leva, liquidazione) · funding · storico · win rate
GLOBALE: PnL totale · capitale vs iniziale · drawdown (vs cap) · esposizione · balance
WALLET multi-network: BSC (BNB gas+trading, token, stablecoin) + Base (USDC x402)
```
Mobile = essenziale. Web = completa con grafici, log, export.

---

## L. STEP DI SVILUPPO

> **Workflow:** ogni step viene completato dall'AI interna → genera un REPORT (vedi sez. M) → l'utente lo passa per revisione → approvazione o correzioni → step successivo. Non si procede allo step successivo senza approvazione.
>
> **Principio "crawl, walk, run":** prima le fondamenta solide e validate, poi la sofisticazione (V2). Non si passa alla complessità finché la base non è stabile.

### STEP 0 — Setup & Architettura
- Struttura cartelle backend (FastAPI)
- `.env` + gestione sicura credenziali (chiave privata cifrata, chmod 600, gitignore)
- Dipendenze, repo, struttura progetto
- Predisposizione: single-user ready-for-multi, i18n, signal engine modulare
- **Deliverable:** scheletro progetto + documento struttura

### STEP 1 — Backend FastAPI (fondamenta)
- Server + endpoint base
- Autenticazione API (token read-only / admin)
- HTTPS predisposto
- **Logging strutturato** (fondamenta observability)
- Health check + heartbeat interno
- Struttura cartelle agente
- **Deliverable:** backend avviabile, autenticato, con logging e health check

### STEP 2 — Migrazione Notifiche → Backend (FCM)

> **Stato al 13 giugno 2026: COMPLETATO.** Il deliverable è stato verificato dall'utente su dispositivo reale con app aperta, in background e chiusa.

- Da push frontend-only a notifiche server-side 24/7
- Firebase Cloud Messaging (canale telefono)
- Sistema alert (critico/warning/info)
- Checker backend ogni 60 secondi per alert soglia, range e movimenti percentuali dei preferiti
- Sincronizzazione configurazione alert app → backend e persistenza temporanea JSON fino allo Step 5
- Registrazione token FCM via Capacitor; visualizzazione garantita anche in foreground tramite notifica locale
- Backend come unica fonte degli eventi: disattivati beep, popup e notifiche generate dal polling frontend per evitare duplicati
- Rimosso il precedente `PriceCheckWorker`: FCM/backend è il percorso unico per le notifiche ad app chiusa
- Confine auth: token device limitato a registrazione/rimozione device; token alerts limitato alla sincronizzazione alert; stato richiede read, invio manuale richiede admin
- Predisposizione multi-canale tramite severity model e servizio notifiche centralizzato. Preferenza telefono/browser/entrambi e canale browser Livello A saranno completati nello Step 8, quando esisterà la dashboard.
- Dipendenza transitoria: il checker usa CoinGecko; viene sostituito dall'adapter CMC nello Step 3.
- **Deliverable:** notifiche funzionanti con app chiusa (telefono via FCM)

### STEP 3 — Migrazione CoinGecko → CMC
- Frontend: sostituzione fonte dati
- CMC API Startup (OHLCV storico) + CMC MCP
- Rate limiting + caching crediti
- Traduzione testi IT → EN (i18n)
- **Test automatici obbligatori (gate per completamento):**
  - Chiamata reale CMC API → risposta con dati validi (richiede chiave CMC configurata)
  - Rate limiter: verifica che richieste oltre soglia vengano bloccate/accodate e non inoltrate
  - Cache crediti: verifica che il contatore scenda correttamente e che i warning soglia scattino
  - Endpoint dati backend: risposta con struttura attesa (symbol, price, volume, OHLCV)
  - Frontend: verifica che le viste mostrino dati CMC e non CoinGecko (nessuna chiamata a api.coingecko.com nei log di rete)
- **Deliverable:** app che gira su dati CMC, backend con accesso dati+MCP, suite test integrazione verde

### STEP 4 — Layer di Esecuzione (esteso: execution astratto multi-provider)

> **Filosofia (aggiornata 16 giugno):** l'obiettivo non è solo l'hackathon ma uno **strumento reale e funzionante** anche fuori dalla gara. L'esecuzione è quindi astratta come il market data (Step 3): interfacce con implementazioni intercambiabili. L'astrazione vale per **entrambi i mercati**, con due percorsi separati: lo **spot** dietro `ExecutionProvider` (TWAK + PancakeSwap), il **perp** dietro `PerpExecutionProvider` (BNB AI Agent SDK + futuri DEX perp). Per l'hackathon lo spot usa TWAK (obbligatorio lì); fuori, esecuzione DEX diretta che non dipende da Trust Wallet (nessun 403, nessuna fee TWAK). Il codice TWAK e BNB SDK già scritto NON si butta: diventa la prima implementazione dietro le rispettive interfacce.

**Parte già completata (Step 4 originale):**
- Spot → TWAK (signing + autonomous mode); approvals verificate
- Perp → BNB AI Agent SDK / EIP-712 (execution sdoppiato)
- BNB SDK (identità ERC-8004 + ERC-8183 + x402)
- x402 su BSC via SDK + servizio terzo (AgentData) con fallback
- Token approvals sicure (whitelist), gas management (riserva 15% + floor), multi RPC fallback
- Gestione trade falliti/parziali + conferma on-chain, logica registrazione competizione
- ⚠️ Blocco esterno: 403 su API swap TWAK (piano Free) — non di codice

**Estensione Step 4 (astrazione execution SPOT):**
- **Interfaccia astratta `ExecutionProvider`** con metodi comuni: quote, execute_swap, get_position, close_position, status. Tutto il resto (agente, risk engine) dipende dall'interfaccia, mai dal provider concreto.
- **`TWAKProvider`** — wrapping del codice TWAK esistente nell'interfaccia (refactor, non riscrittura). Provider per l'hackathon.
- **`PancakeSwapProvider`** — esecuzione DEX diretta via web3.py sul PancakeSwap Router. Nessuna dipendenza da Trust Wallet, nessun 403, nessuna fee TWAK. Usa il wallet keystore Web3 già esistente. Provider per uso reale fuori dall'hackathon e per TEST locali dell'agente subito (senza aspettare lo sblocco TWAK).
- **Selettore execution provider** globale (config + impostazioni sviluppatore): `twak` / `pancakeswap`. Stesso pattern del selettore dati.
- I guardrail (gas, approvals whitelist, slippage, cap rischio) restano nel layer comune, validi per entrambi i provider.
- **Deliverable esteso:** esecuzione funzionante via PancakeSwap diretto (testabile subito su BSC) + TWAK pronto per l'hackathon, dietro interfaccia comune con selettore.

**Estensione Step 4 (astrazione execution PERP — stesso pattern):**
- **Interfaccia astratta `PerpExecutionProvider`** di alto livello: open_position, close_position, get_position, status (ciò che l'agente userà a prescindere dal DEX perp). I dettagli di firma (EIP-712) restano interni al provider.
- **`BnbSdkPerpProvider`** — wrapping del boundary BNB AI Agent SDK / EIP-712 esistente (refactor, non riscrittura): status + path firma/submit. open/close/get position sono predisposti (fail-closed) finché non è configurata una venue perp / arriva l'agente (Step 6).
- **Selettore perp provider** globale e persistito (admin-only): `perp_execution_provider`. Stesso pattern dello spot, registry separato.
- **Predisposizione multi-DEX:** aggiungere un 2°/3°/4° DEX di perpetual = nuova classe `XxxPerpProvider(PerpExecutionProvider)` + voce nell'enum/registry, senza toccare agente/service.

> **Nota:** spot e perp restano percorsi separati con interfacce/registry distinti (mercati diversi, API diverse).
> **V2:** ulteriori execution provider sia spot (altri DEX/aggregatori) sia perp (altri DEX perpetual), eventuale fallback automatico tra provider.

### STEP 5 — Persistenza Dati
- DB con separazione esplicita Spot / Perp / Globale
- Schema: trade, decisioni, PnL snapshot orari, posizioni
- Tag `user_id` (predisposizione multi-user)
- Timestamp UTC + timestamp on-chain
- **Deliverable:** persistenza completa, query per le viste

### STEP 6 — Agente AI (Brain)
- Claude come meta-controller (poteri limitati)
- **Strategia Spot V1** (momentum + struttura + VWAP + EMA di supporto + ATR + relative volume)
- **Strategia Perp V1** (Volume Profile mean reversion + gerarchia segnali, trend via VWAP)
- **Feed Binance klines per Volume Profile 5m** (debito Step 3): `/fapi/v1/klines` (futures) o `/api/v3/klines` (spot), con volume. Feed specializzato nel signal engine, NON nel `MarketDataProvider` generico.
- Signal engine modulare (predisposto delta V2, relative strength V2)
- Risk management completo + guardrail
- Reattività due velocità (loop veloce/lento)
- Modalità degradata
- Kill switch (soft + hard)
- Regole hardcoded (heartbeat 1 trade/giorno, mai sotto $1)
- Modalità operative (dry-run / live / test scaling %, network)
- **L'agente usa l'interfaccia `ExecutionProvider` astratta (Step 4 esteso):** non sa né gli importa se sotto c'è TWAK o PancakeSwap. Questo permette di testare l'agente in esecuzione reale via PancakeSwap subito, senza dipendere dallo sblocco del 403 TWAK.
- **Deliverable:** agente completo funzionante in dry-run, testabile in esecuzione reale via PancakeSwap

### STEP 7 — Estensione App Mobile (SOLO ADDITIVO)

> **REGOLA ASSOLUTA — protezione app esistente:** l'app mobile CryptoSentinel esistente NON va stravolta. Le funzionalità attuali (monitoring prezzi, alert soglia/range/percentuali/preferiti, grafici, ricerca, notifiche, preferiti) sono **intoccabili** nel comportamento. Lo Step 7 è **solo additivo**: si aggiungono nuovi componenti, nuove tab/viste e nuove impostazioni per l'agente. Se serve estendere un componente esistente (es. icona AI sulla CoinCard), farlo in modo additivo (prop opzionali, nuovi elementi), MAI riscrivendo o cambiando la logica esistente. Nessun file esistente va rinominato o spostato.

Aggiunte all'app mobile (essenziali, mobile-first):
- 3 viste nuove: Spot / Perp / Globale
- Icone AI sulle card coin (⚪ inattiva / 🟡 analisi / 🟢 long / 🔴 short) — aggiunta additiva alla CoinCard
- Impostazioni Agente complete (modalità, mercati, rischio, spot, perp, test scaling, orari) — nuova tab/sezione
- Onboarding cross-platform + lock esclusivo (10 min) + validazione live credenziali
- Kill switch accessibile (soft + hard)
- Empty states curati per le nuove viste
- Wallet multi-network (BSC + Base)
- **Test automatici obbligatori (gate per completamento):**
  - Vista Spot: chiamata backend → dati posizioni/PnL spot ricevuti e renderizzati correttamente
  - Vista Perp: chiamata backend → dati posizioni/PnL perp (leva, liquidazione, funding) ricevuti e renderizzati correttamente
  - Vista Globale: chiamata backend → PnL totale, drawdown, esposizione ricevuti e renderizzati correttamente
  - Impostazioni Agente: modifica parametro → invio backend → conferma stato aggiornato
  - Kill switch: chiamata backend soft-stop → stato agente aggiornato nella UI
  - Credenziali onboarding: validazione live → risposta backend attesa (successo/errore) gestita correttamente nella UI
  - Empty states: mock risposta vuota dal backend → empty state corretto mostrato in ogni nuova vista
  - **Regressione funzioni esistenti:** verifica che monitoring, alert e grafici esistenti funzionino esattamente come prima (nessuna regressione introdotta dalle aggiunte)
- **Deliverable:** app mobile estesa con funzioni agente, funzioni esistenti intatte, suite test integrazione + regressione verde

### STEP 8 — Dashboard Web Unificata (Vite, browser)

> **Un'unica interfaccia web completa.** Non esistono due dashboard web: questa è l'unica. Contiene TUTTO ciò che serve da browser — monitoring completo, agente, System Health, log, replay, export. È un progetto Vite separato (porta 5176), distinto dall'app mobile, accessibile da qualsiasi browser desktop/Mac. L'app mobile resta sul telefono per l'uso essenziale; la dashboard web è l'interfaccia completa per desktop.

- Monitoring completo (prezzi, grafici, watchlist) — versione browser ricca
- 3 viste agente complete + grafici: Spot / Perp / Globale
- System Health (strutturale + operativo + risorse/carburante)
- Log viewer (filtrabile, esportabile)
- Demo/Replay dettagliato trade-by-trade (prove on-chain)
- Export spiegazione strategia (per i giudici)
- Impostazioni Agente complete
- **Notifiche browser (Livello A):** la dashboard mostra le notifiche push quando è aperta; preferenza utente per scegliere il canale (solo telefono / solo browser / entrambi). Web Push a dashboard chiusa = V2.
- Onboarding sincronizzato (stesso stato del mobile, stesso backend)
- Kill switch accessibile (soft + hard)
- Layout desktop-first (sfrutta lo schermo ampio: tabelle, grafici multipli, pannelli)
- **Deliverable:** dashboard web unica e completa, un solo URL da aprire

### STEP 9 — Testing
- Dry-run (dati mainnet reali, esecuzione simulata)
- Testnet (integrazioni TWAK/SDK su BSC testnet)
- Mainnet con Test Scaling % ridotto
- Verifica vincoli qualificazione
- Registrazione competizione on-chain (runbook + verifica on-chain)
- **Deliverable:** sistema validato end-to-end + agente registrato

### STEP 10 — Deploy VPS
- Backend + dashboard su VPS Linux
- Configurazione 24/7 (auto-restart / systemd)
- NTP (sincronizzazione tempo)
- Backup automatico DB + export config
- Monitoraggio attivo settimana gara
- Runbook ripristino rapido
- **TWAK in ambiente headless (dal Telegram BNB Hack):** sul VPS non c'è il keychain OS usato in locale. Pattern di deploy headless:
  - `TWAK_WALLET_PASSWORD` come variabile d'ambiente (nel `.env`, mai committato)
  - Creazione/uso wallet con flag `--no-keychain`
  - Volume/cartella persistente montata su `~/.twak` (contiene `wallet.json` e `credentials.json`) — deve sopravvivere ai restart del container/servizio
  - Il file `~/.twak/wallet.json` cifrato va preservato nei backup, mai nel repo
- **Deliverable:** sistema in produzione, operativo 24/7

---

## M. WORKFLOW REPORT PER OGNI STEP

Al termine di ogni step, l'AI interna produce un report contenente:
1. **Cosa è stato fatto** — elenco concreto delle implementazioni
2. **Come è stato fatto** — scelte tecniche e motivazioni
3. **Cosa è stato verificato** — test eseguiti ed esiti
4. **Scostamenti dal piano** — cosa è cambiato e perché
5. **Questioni aperte / decisioni necessarie** — punti che richiedono input
6. **Verifiche tecniche** — risultati delle verifiche delegate (vedi sez. N)
7. **Stato deliverable** — il deliverable dello step è raggiunto? sì/no/parziale

L'utente passa il report per revisione. Solo dopo approvazione si procede.

---

## N. QUESTIONI APERTE + VERIFICHE TECNICHE DELEGATE

### Da chiarire con organizzatori (Telegram/DoraHacks)
- ✅ **403 swap TWAK** — RISOLTO. Causa legata all'account/wallet specifico, non al piano Free. Soluzione verificata: nuova API key + nuovo wallet TWAK + reinizializzazione completa (`twak init` + `twak wallet create`). Quote-only mainnet confermato funzionante con il wallet `0xDF27d02a536F1AaAF16a25D5E76DA50d716EAfeB`.
- ⏳ **Spot vs Perp nel ranking** — determina la priorità strategica dello Step 6. In attesa di risposta.
- Valore esatto del **drawdown cap** della gara (default prudenziale -15% intanto)
- Dettagli scoring (raw vs risk-adjusted)
- Cosa conta come "trade valido" per il minimo giornaliero (size minima?)
- **Perp DEX** consigliato e via preferita perp (BNB SDK vs EIP-712)
- Data/ora esatta apertura trading window (per timing registrazione)
- ✅ **Esecuzione on-chain via TWAK** — CONFERMATO obbligatorio (16 giugno)
- ✅ **Fee TWAK** — ridotte a 0.077% durante la gara (16 giugno)

### Verifiche tecniche delegate all'AI interna (in fase di sviluppo)
- Come TWAK gestisce le **approvals** in autonomous mode (mirate/illimitate/policy propria)
- Quanto a fondo integrare il **BNB SDK** (priorità: moduli custody/memory/payment) — puntare al premio
- Quali dei 149 token sono coperti da **AgentData** (e altri servizi x402)
- Dove trovare **whale flow / smart money** su BSC (the402.ai, agentic.market)
- Gestione **Base vs BSC** per i pagamenti x402 (preferire BSC via BNB SDK)
- Mesi di **OHLCV storico** dello Startup sui timeframe brevi (5m, 15m, 1h)
- Configurare **multi RPC endpoint** BSC di fallback

---

## O. RUNBOOK GARA

### Registrazione (prima dell'apertura trading window)
1. Wallet agente pronto e finanziato (balance non-zero in-scope)
2. BNB per gas registrazione
3. Eseguire `twak compete register` o MCP `competition_register`
4. **Verificare** tx su bsctrace + presenza indirizzo nel contratto
5. Registrare indirizzo su DoraHacks
6. Preparare spiegazione strategia
7. Screenshot/log come prova
- **Timing:** quando l'agente è validato e stabile, con margine prima del 22 giugno. Mai all'ultimo.

### Trade giornaliero (heartbeat)
- Conteggio trade reali del giorno (UTC)
- Se ≥1 trade reale → heartbeat non serve
- Se nessun trade entro orario di sicurezza (es. 20:00 UTC) → heartbeat trade minimo su pair liquido eligible
- Verifica on-chain del successo; retry entro la finestra di sicurezza
- Monitoraggio in System Health (✓/✗ per ogni giorno)

### Monitoraggio settimana gara
- System Health sempre sotto controllo (servizi, carburante, drawdown)
- Alert push attivi (critico)
- Backup attivi, runbook ripristino pronto
- Drawdown monitorato vs cap (priorità: minimizzare drawdown)

---

## APPENDICE — Token eligible (149)

ETH, USDT, USDC, XRP, TRX, DOGE, ZEC, ADA, LINK, BCH, DAI, TON, USD1, USDe, M, LTC, AVAX, SHIB, XAUt, WLFI, H, DOT, UNI, ASTER, DEXE, USDD, ETC, AAVE, ATOM, U, STABLE, FIL, INJ, 币安人生, NIGHT, FET, TUSD, BONK, PENGU, CAKE, SIREN, LUNC, ZRO, KITE, FDUSD, BEAT, PIEVERSE, BTT, NFT, EDGE, FLOKI, LDO, B, FF, PENDLE, NEX, STG, AXS, TWT, HOME, RAY, COMP, GWEI, XCN, GENIUS, XPL, BAT, SKYAI, APE, IP, SFP, TAG, NXPC, AB, SAHARA, 1INCH, CHEEMS, BANANAS31, RIVER, MYX, RAVE, SNX, FORM, LAB, HTX, USDf, CTM, BDX, SLX, UB, DUCKY, FRAX, BILL, WFI, KOGE, ALE, FRXUSD, USDF, GOMINING, VCNT, GUA, DUSD, SMILEK, 0G, BEAM, MY, SLX, SOON, REAL, Q, AIOZ, ZIG, YFI, TAC, lisUSD, CYS, ZAMA, TRIA, HUMA, PLUME, ZIL, XPR, ZETA, BabyDoge, NILA, ROSE, VELO, UAI, BRETT, OPEN, BSB, TOSHI, BAS, ACH, AXL, LUR, ELF, KAVA, APR, IRYS, EURI, XUSD, BARD, DUSK, SUSHI, PEAQ, COAI, BDCA, XAUM

> Preferire i token a maggiore liquidità (BNB, ETH, e major). Evitare i token a bassa liquidità (slippage e manipolazione). Il Volume Profile (perp) si attiva solo su token sufficientemente liquidi.

---

## DEADLINE

- **Build phase:** fino al 21 giugno 2026
- **Trading window (gara live):** 22-28 giugno 2026
- **Judging:** 29 giugno - 5 luglio
- Priorità assoluta: fondamenta solide e qualificazione garantita prima della sofisticazione.

---

*Fine del piano. Documenti collegati: Strategia_Spot.md (v2), Strategia_Perpetual.md (v3). Questo piano va riletto e aggiornato man mano che le questioni aperte vengono chiarite.*
