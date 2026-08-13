# Opacita Contesto Grafici Trade

## 1. COSA È STATO FATTO

- Le candele precedenti all'ingresso vengono ora mostrate semitrasparenti nei grafici trade.
- Il comportamento e' stato applicato sia all'app mobile sia alla dashboard.

## 2. COME È STATO FATTO

- In `src/components/AgentTab.tsx` il renderer del grafico calcola `isPreEntry` confrontando l'indice della candela con `entryIdx`.
- In `dashboard/src/App.tsx` e' stata applicata la stessa logica.
- Le candele pre-entry usano la stessa opacita' delle candele post-close.

## 3. COSA È STATO VERIFICATO

- `npx tsc -b`
  - Esito: ok.
- `npx tsc -p dashboard/tsconfig.json`
  - Esito: ok.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Nessuna.

## 6. STATO DELIVERABLE

- Implementato e verificato localmente.
