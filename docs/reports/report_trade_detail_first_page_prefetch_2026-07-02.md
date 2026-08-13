# Report - Trade detail first-page prefetch

## 1. COSA È STATO FATTO

- Rafforzato il precaricamento dei dettagli trade nella tab mobile agente.
- Le posizioni aperte e la prima pagina della history Spot/Perp vengono ora precaricate appena le viste sono disponibili.
- La cache dettaglio trade è stata ampliata per evitare nuovi download quando il dettaglio completo è già disponibile.

## 2. COME È STATO FATTO

- In `src/components/AgentTab.tsx` il prefetch non dipende più dal sotto-pane attivo: lavora su Spot e Perp appena i dati arrivano.
- Il prefetch scarica prima il dettaglio base, poi prova a completare il grafico con le candele mancanti in background.
- È stata aggiunta una concorrenza limitata a due worker e un retry throttle di 60 secondi per evitare raffiche ripetute verso il backend quando un dettaglio fallisce.

## 3. COSA È STATO VERIFICATO

- Eseguito `npm run build` con esito positivo.
- Verificato che la modifica è confinata al frontend mobile agente e alla documentazione.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno: non sono state modificate strategie, backend execution, risk management o configurazioni operative.

## 5. QUESTIONI APERTE

- La verifica più importante resta su app reale: i dettagli cliccati subito dopo l'apertura scheda devono arrivare dalla cache se il prefetch ha già completato il caricamento.
- Se il backend non riesce a produrre le candele post-chiusura per un trade recente o non coperto, il dettaglio base resta comunque disponibile e il completamento viene ritentato dopo il throttle.

## 6. STATO DELIVERABLE

- Deliverable completato lato codice e build.
