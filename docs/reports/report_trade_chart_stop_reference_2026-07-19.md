# Grafici Trade Con Reference Stop Loss

## 1. COSA È STATO FATTO

- Aggiunta la tracciatura della candela usata come riferimento per lo stop loss strutturale.
- Estesi gli snapshot dei grafici trade per includere fino a 10 candele prima della candela di riferimento SL.
- Resi i grafici trade scrollabili orizzontalmente su app e dashboard quando il numero di candele supera la larghezza disponibile.
- Aggiunto marker `SL ref` nei grafici trade.

## 2. COME È STATO FATTO

- `SpotMomentumSignal` salva nei componenti del segnale timestamp, prezzo e campo (`low`) della candela minima usata in modalita' `lowest`.
- `VolumeProfileSignal` salva nei componenti del segnale timestamp, prezzo e campo (`low` per long, `high` per short) della candela usata in modalita' `lowest`.
- `SpotPosition` e `PerpPosition` persistono `stop_reference_time`, `stop_reference_price` e `stop_reference_field`.
- Lo snapshot di chiusura in `AgentService` usa `start_time = stop_reference_time - 10*candele` quando la reference e' disponibile, con fallback al fetch precedente se il feed non risponde.
- Il trade detail live in `views.py` espone lo stesso metadata e non usa la cache klines quando deve includere candele pre-reference.
- `AgentTab.tsx` e `dashboard/src/App.tsx` calcolano larghezza dinamica del grafico, abilitano scroll orizzontale e disegnano la linea/marker `SL ref`.

## 3. COSA È STATO VERIFICATO

- Test backend mirati:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_signal_stop_loss_modes.py backend/tests/unit/test_agent_step6.py -q`
  - Esito: 66 passed.
- Compile backend mirato con `compileall`.
- Typecheck app mobile: `npx tsc -b`.
- Typecheck dashboard: `npx tsc -p dashboard/tsconfig.json`.

## 4. SCOSTAMENTI DAL PIANO

- Non e' stato eseguito un build Vite locale per evitare build frontend che possono caricare `.env`; e' stato usato typecheck TypeScript.
- Un primo comando build con argomento errato ha fallito per `development/index.html`, senza cambiare file.

## 5. QUESTIONI APERTE

- I trade gia' presenti nel DB prima di questa modifica non hanno `stop_reference_time`; mostreranno il grafico precedente senza marker SL ref.
- Il marker e le 10 candele pre-reference saranno disponibili sui nuovi trade aperti dopo la migrazione schema.

## 6. STATO DELIVERABLE

- Implementato e verificato localmente.
