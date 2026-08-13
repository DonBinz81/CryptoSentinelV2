# Report - Buffer SL strutturale e marker grafico

## 1. COSA È STATO FATTO

- Verificato il caso TRX perp long aperto: `stop_loss` salvato = `stop_reference_price * 0.989`, quindi il buffer 1.10% era applicato correttamente.
- Aggiunti nella dashboard i campi impostazione `spot_structural_stop_buffer_pct` e `perp_structural_stop_buffer_pct`, gia' supportati da backend e app mobile.
- Aggiornato il marker viola dei grafici trade in dashboard e app mobile: resta allineato alla candela di riferimento sull'asse X, ma il pallino viene disegnato sul prezzo effettivo dello stop loss.

## 2. COME È STATO FATTO

- Estesa la lista `settingFields` della dashboard con i due buffer percentuali strutturali.
- Nei componenti grafico trade e' stato preferito `chart.stop_loss` come prezzo del pallino SL ref, con fallback al prezzo grezzo della candela di riferimento se lo stop non e' disponibile.
- Nessuna modifica al calcolo backend dello stop, perche' la verifica locale ha confermato la formula esistente.

## 3. COSA È STATO VERIFICATO

- Verificata la posizione TRX perp long aperta nel DB locale.
- Verificata la presenza del buffer nel setup mobile.
- Verificata la presenza dei nuovi riferimenti UI con ricerca testuale.

## 4. SCOSTAMENTI DAL PIANO

- Non e' stato cambiato il signal engine: il problema osservato era la lettura visiva del marker e l'ampiezza configurata del buffer, non la formula applicata.

## 5. QUESTIONI APERTE

- Serve provare operativamente quale buffer percentuale sia piu' adatto in base al comportamento live/dry-run.
- Non e' stato eseguito un test visuale browser/mobile in questa fase.

## 6. STATO DELIVERABLE

- Modifica implementata e pronta per verifica locale.
