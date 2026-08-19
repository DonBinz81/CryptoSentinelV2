# Report - Un canale d'allarme che non dipende da ciò che si rompe

Data: 2026-08-19
Branch: `chat-infra/telegram-alerts`

---

## COSA È STATO FATTO

Gli allarmi operativi (backup fallito, database illeggibile, anomalia rilevata dal watchdog)
viaggiavano **solo su FCM**, che ha bisogno di due cose: il backend in piedi e la tabella
`device_tokens` leggibile.

Sono esattamente le due cose che si rompono negli incidenti per cui quegli allarmi esistono.
Il 18/08 la tabella corrotta era proprio `device_tokens`: il guasto sarebbe stato **rilevato
in un minuto e non consegnato a nessuno** (`NOTE/54`).

Aggiunto **Telegram** come canale d'emergenza: parla direttamente con `api.telegram.org`,
senza passare né dal backend né dal database.

## COME È STATO FATTO

Nuovo `deploy/scripts/notify_alert.sh <titolo> <corpo> [fonte]`, unico punto di consegna:

- **FCM** se `API_ADMIN_TOKEN` è presente (canale normale, notifiche sul telefono);
- **Telegram** se `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` sono presenti (canale
  d'emergenza);
- esce **0 se almeno un canale ha accettato** il messaggio. L'obiettivo è che l'allarme
  raggiunga una persona, non che tutti i canali riescano. Esce 1 solo se non è uscito nulla,
  così systemd continua a vedere un fallimento vero.

`backup_alert.sh` e `db_watchdog.sh` ora producono titolo e corpo e delegano a lui: la logica
di consegna sta in un posto solo, e aggiungere un terzo canale domani non tocca gli allarmi.

**Sui segreti**: le due variabili sono state inserite direttamente nel `.env` di produzione
dal proprietario, senza passare dall'assistente. `curl` gira **senza `--show-error`** sulla
chiamata Telegram: un messaggio d'errore potrebbe riportare l'URL, che contiene il token del
bot. Verificato che in caso di fallimento venga stampato solo `Telegram delivery failed`.

## COSA È STATO VERIFICATO

| prova | atteso | esito |
|---|---|---|
| Nessun canale configurato | esce 1 spiegando perché | ✅ `no channel configured, alert not delivered` |
| Solo Telegram, token finto | tenta, fallisce, **non stampa il token** | ✅ solo `Telegram delivery failed` |
| `backup_alert` con `integrity_failed` | titolo «Database illeggibile» + esito completo | ✅ |
| `backup_alert` con `db_missing` | titolo «Backup fallito» + stato | ✅ |
| `backup_alert` senza file di stato | messaggio di ripiego | ✅ |
| Sintassi (`bash -n`) dei tre script | pulita | ✅ in locale e sulla VPS |

Le prove sui messaggi sono state fatte sostituendo l'helper con un finto, così da leggere
titolo e corpo **senza inviare notifiche reali**.

## SCOSTAMENTI DAL PIANO

Invece di aggiungere una chiamata Telegram dentro i due script esistenti (dieci righe
duplicate), la consegna è stata estratta in un helper condiviso. Costa una riscrittura di
`backup_alert.sh`, ma evita che i due allarmi divergano.

## QUESTIONI APERTE

1. **Prova end-to-end da fare**: serve il bot Telegram del proprietario. Finché le due
   variabili non sono nel `.env`, il canale è inerte e gli allarmi continuano su FCM come
   prima — nessuna regressione.
2. Resta scoperto il caso «il timer smette di partire del tutto»: nessun fallimento da
   segnalare, quindi nessun allarme. Serve un controllo di freschezza, perimetro strategia.
3. Il canale Android silenzioso (le push arrivano in «Notifiche silenziose») è perimetro app
   e non è toccato qui — ma è una ragione in più per avere Telegram, che suona sempre.

## STATO DELIVERABLE

- `deploy/scripts/notify_alert.sh` — nuovo, provato.
- `deploy/scripts/backup_alert.sh` — riscritto per delegare la consegna.
- `deploy/scripts/db_watchdog.sh` — delega la consegna; aggiornato il commento che
  dichiarava il limite ora chiuso.
- Non deployato: in attesa delle credenziali del bot e della prova end-to-end.
