# Report - Trade detail post-close cache

## 1. COSA È STATO FATTO

- Corretto il criterio con cui la mobile app considera completo il grafico del dettaglio trade.
- Un trade chiuso ora richiede anche `post_close_candles` per essere considerato completamente arricchito.
- Il dettaglio base continua a essere mostrato subito dalla cache, ma l'app prova ancora a caricare le candele successive alla chiusura quando mancano.

## 2. COME È STATO FATTO

- In `src/components/AgentTab.tsx` è stata separata la verifica del grafico base (`candles`) dalla verifica del grafico completo (`post_close_candles`).
- La cache protegge ancora i dettagli già arricchiti e non li sovrascrive con payload più poveri.
- La logica di enrichment viene riattivata per i trade chiusi che hanno snapshot base ma non hanno ancora candele successive alla chiusura.

## 3. COSA È STATO VERIFICATO

- Eseguito `npm run build` con esito positivo.
- Verificato che la modifica è confinata al frontend mobile agente e alla documentazione.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno: non sono state modificate strategia, risk management, backend execution o configurazione.

## 5. QUESTIONI APERTE

- Se Binance/fallback non restituisce ancora candele post-close perché il trade è troppo recente o il simbolo non è coperto, il backend continuerà a restituire il grafico base senza post-close.
- Una cache server-side degli enrichment post-close resta il passo successivo se la latenza backend rimane alta.

## 6. STATO DELIVERABLE

- Deliverable completato lato codice e build.
- Da verificare su app reale che i dettagli già aperti vengano arricchiti appena le candele post-close sono disponibili.
