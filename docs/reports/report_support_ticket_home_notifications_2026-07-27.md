# Report - Notifiche ticket in Home

## 1. COSA È STATO FATTO

- Aggiunto lo stato di lettura persistente dei ticket per utente e admin.
- Aggiunti endpoint backend per contare i messaggi supporto non letti e marcare un ticket come letto.
- Aggiunta nell'app una icona flottante in Home, con stile coerente con quella degli update, che appare solo quando ci sono messaggi ticket non letti.
- Spostata l'icona flottante ticket sul lato sinistro per non confonderla con l'icona aggiornamenti.
- La notifica mobile conta i messaggi utente e, se e' configurato il token admin, aggiunge anche i messaggi/ticket non letti per admin.
- Il caricamento della sezione Support marca letti tutti i ticket visibili, cosi' il badge scompare quando l'utente/admin ha controllato la coda.
- Aggiornata la dashboard: mostra il conteggio unread admin nella sezione Support e marca letto quando l'admin apre un ticket.

## 2. COME È STATO FATTO

- `support_tickets` ora ha `user_last_seen_at` e `admin_last_seen_at`, con migrazione idempotente.
- Il repository support calcola unread contando solo i messaggi inviati dall'altra parte dopo il relativo timestamp di lettura.
- L'app interroga `/api/v1/support/notifications` ogni 60 secondi e, se esiste `adminToken`, anche `/api/v1/support/admin/notifications`.
- `SettingsTab` chiama il mark-read quando apre un ticket, sia in modalita' user sia in modalita' admin.
- `SettingsTab` chiama anche il mark-read globale dopo il caricamento della lista ticket, per azzerare i falsi unread su thread gia' letti.
- La dashboard chiama il mark-read admin quando apre il dettaglio ticket e mark-read globale quando carica la coda attiva.

## 3. COSA È STATO VERIFICATO

- Test integrazione support API aggiornato e passato.
- Compile Python backend passato.
- TypeScript app mobile passato.
- TypeScript dashboard passato.

## 4. SCOSTAMENTI DAL PIANO

- Non e' stata usata una logica solo localStorage per i non letti: e' stato scelto uno stato persistente DB per evitare badge incoerenti tra app, dashboard e device diversi.

## 5. QUESTIONI APERTE

- Il badge e' in-app/polling; le notifiche push FCM gia' esistenti restano separate.
- La dashboard mostra il conteggio dentro Support, non un floating badge globale.

## 6. STATO DELIVERABLE

- Deliverable implementato e verificato con test mirati.
