# Report — Telemetria di posizionamento (ingresso + in-trade)

Data: 2026-08-21 · Branch: `claude/telemetria-posizionamento` · Riferimenti: NOTE/76-78, NOTE/81

## 1. COSA È STATO FATTO
Archiviazione automatica dell'evidenza dietro i due indizi condizionali sopravvissuti
(OI del pair e confidence del Brain), prima che la retention di ~30 giorni degli
endpoint di posizionamento Binance la cancelli. Due tabelle nuove:
- `entry_telemetry`: a ogni apertura perp — OI Δ24h del pair, L/S ratio (valore+Δ24h),
  taker 4h, confidence del Brain (denormalizzata: prima non era joinabile).
- `position_telemetry`: a ogni slow tick (300 s), per ogni posizione aperta — OI
  corrente + profondità avversa.
Flag `perp_telemetry_enabled` (default true, YAML). Diagnostica pura: il trading non
legge mai queste tabelle.

## 2. COME È STATO FATTO
- `agent/telemetry.py`: fetcher httpx con timeout 6 s, iniettabili nei test; fallimento
  per-metrica → NULL + marcatore in `error` (assenza visibile, mai riga persa in
  silenzio); cattura d'ingresso fire-and-forget con sessione propria (sopravvive alla
  request); mai un'eccezione verso il trading.
- Hook: `_handle_signal` dopo il commit dell'esecuzione (con `position_id` ora incluso
  nel payload del simulate perp — prima non c'era); `slow_tick` per gli snapshot.
- Tabelle registrate in `models/__init__` → `create_all` le crea al primo avvio.

## 3. COSA È STATO VERIFICATO
4 test nuovi (riga con metriche; fallimento totale che non solleva; fallimento parziale
→ NULL + errore; snapshot con OI giù tollerato). Suite completa su VPS: **355 passed,
2 failed** (i 2 preesistenti). Primo giro post-deploy verificato nei log
(`entry_telemetry_captured` / righe snapshot) al primo trade utile.

## 4. SCOSTAMENTI DAL PIANO
`self.settings.<campo nuovo>` sostituito con `getattr(..., default)` dopo che 7 test
mock sono esplosi: pattern del file, ora rispettato.

## 5. QUESTIONI APERTE
La validazione degli indizi (confidence gate, scala OI) resta appuntata a fra 2-3
settimane, quando il campione archiviato sarà abbastanza grande.

## 6. STATO DELIVERABLE
Completo, testato, deployato, mergiato.
