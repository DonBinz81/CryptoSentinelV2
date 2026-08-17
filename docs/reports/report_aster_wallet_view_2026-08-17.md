# Report - Scheda wallet: visibilità del wallet Aster

## COSA È STATO FATTO

- Aggiunta la vista del wallet **Aster** nella scheda Wallet, che finora mostrava solo il
  wallet BSC dell'esecuzione spot: i due indirizzi Aster vivevano unicamente nel `.env` e
  si vedevano soltanto nel test di connessione.
- Nuovo endpoint di **sola lettura** `GET /api/v1/aster/wallet` con indirizzi, saldo e
  numero di posizioni aperte lette da Aster.
- Blocco Aster nella **dashboard** (pannello Wallet) e nell'**app** (scheda Wallet).

## COME È STATO FATTO

- `execution/venues/aster/wallet.py`: costruisce la vista riusando il client Aster
  esistente (solo GET). Nessun nuovo permesso, nessuna scrittura.
- **Cache di 30 secondi**: dashboard e app fanno polling, e la venue non va interrogata a
  ogni refresh.
- Regola di esposizione decisa dall'utente:
  - **sub-account per intero** — è l'indirizzo su cui vanno versati i fondi, quindi deve
    essere copiabile;
  - **wallet API abbreviato** (`0xC5AF...2401`) — firma soltanto, non riceve nulla;
  - **chiave privata mai esposta**, in nessuna forma.
- Nell'app l'indirizzo del sub-account usa il "tocca per copiare" già presente per il
  wallet BSC; nella dashboard c'è un pulsante di aggiornamento manuale.
- Quando il conto non è finanziato la UI lo dice esplicitamente, invece di mostrare uno
  zero muto.

## COSA È STATO VERIFICATO

- **Chiamata reale in produzione** all'endpoint, con token di lettura:
  ```
  configurato      True
  sub-account      CryptosentinelV2 | 0x295d008D148Cf3df3210c88278a6d5f1228187f9
  wallet API       0xC5AF...2401
  raggiungibile    True
  saldo USDT       0.00     (sub-account non ancora finanziato)
  posizioni        0
  ```
- Verifica automatica che la risposta **non contenga alcuna chiave privata**.
- Due test nuovi: assenza di credenziali (dice cosa manca) e regola di esposizione
  (sub-account intero, API abbreviato, chiave e indirizzo completo del signer assenti dal
  payload serializzato).
- Suite completa sulla VPS: **262 passed, 2 failed, 2 skipped**. Le 2 failure sono
  preesistenti (`test_meta_controller_reduce`,
  `test_support_ticket_thread_and_admin_status_flow`).
- `npx tsc --noEmit` pulito su app e dashboard. Nessuna build in locale.

## SCOSTAMENTI DAL PIANO

- **Errore di processo, corretto**: il primo commit era stato fatto con `git add -A`
  mentre una seconda sessione lavorava in parallelo sugli stessi file, e ha inglobato
  anche il lavoro sulla visibilità dei pair. Risolto con `reset --soft` e due commit
  separati: `7984dc5` (wallet Aster) e `74a731f` (visibilità pair). Nessuna riga persa.
  **Lezione**: con più sessioni sullo stesso repo, verificare `git status` prima di
  ogni `add`, e non usare mai `-A` alla cieca.
- Nella ricognizione avevo indicato la scheda wallet dell'app dentro Impostazioni: è
  invece `WalletPane` in `AgentTab.tsx`. Corretto prima di scrivere codice.

## QUESTIONI APERTE

- Il **sub-account non è finanziato**: il saldo mostrato è 0,00 USDT. È corretto, ma
  finché non arrivano fondi la vista resta vuota.
- Il saldo mostrato somma **USDT e USDC**; se in futuro si opererà con altri collaterali
  andrà rivista la logica del totale.
- Nessun deploy del frontend: il blocco nella **dashboard** compare dopo il deploy delle
  Pages, quello nell'**app** con il prossimo APK. Il backend è già deployato.

## STATO DELIVERABLE

- Completo e verificato in produzione lato backend. Commit `7984dc5`, non ancora pushato.
