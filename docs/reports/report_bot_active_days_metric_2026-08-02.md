# Report Bot Active Days Metric - 2026-08-02

## 1. COSA È STATO FATTO

È stata aggiunta una metrica separata `bot_active_days` nelle viste Spot e Perp per indicare da quanti giorni è attivo il bot.

Il conteggio `trade_count_today` è rimasto invariato e continua a rappresentare i trade chiusi oggi per il singolo mercato.

## 2. COME È STATO FATTO

I repository Spot/Perp ora espongono il primo timestamp trade registrato per utente. La `ViewService` calcola il minimo tra Spot e Perp e restituisce un conteggio inclusivo dei giorni UTC trascorsi dal primo ordine.

La nuova metrica è stata aggiunta ai contratti backend, ai tipi TypeScript dell'app e della dashboard, e alle metriche visibili nelle viste Spot e Perp.

## 3. COSA È STATO VERIFICATO

È stata aggiunta una regressione backend che verifica che Spot e Perp mostrino lo stesso `bot_active_days` e che `trade_count_today` resti separato per mercato.

## 4. SCOSTAMENTI DAL PIANO

Nessuno. Il valore precedente "Trade Day" non è stato modificato.

## 5. QUESTIONI APERTE

Nessuna questione aperta a livello codice. Il backend va riavviato per esporre il nuovo campo API.

## 6. STATO DELIVERABLE

Implementato e pronto per verifica runtime.
