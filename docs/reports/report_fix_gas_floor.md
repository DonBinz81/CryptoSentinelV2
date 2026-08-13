# Report fix gas floor

## 1. COSA È STATO FATTO

- Abbassato il floor minimo gas BNB da `0.005` a `0.000005`.
- Aggiornata la documentazione backend che citava il valore precedente.

## 2. COME È STATO FATTO

- Modificato il default funzionale in `configs/risk.yaml`.
- Il guardrail in `Settings` resta invariato: il floor deve essere positivo.

## 3. COSA È STATO VERIFICATO

- Verifica configurazione mirata.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Nessuna.

## 6. STATO DELIVERABLE

Floor gas aggiornato.
