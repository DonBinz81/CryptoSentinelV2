# Banco di anteprima

Serve a **guardare un pezzo dell'interfaccia nel browser** con dati finti, prima di
compilare un APK. Non è una build di produzione e non parla con il backend.

Esiste perché ogni modifica all'interfaccia va **vista** prima di essere consegnata:
sul grafico della posizione, sette difetti reali sono emersi guardando l'anteprima e
nessuno sarebbe uscito da una descrizione a parole.

## Come si usa

1. Apri `main.tsx` e monta il componente che vuoi guardare, passandogli dati scritti a
   mano (nessuna chiamata al backend).
2. Avvia:

```bash
npx vite --config dev-preview/vite.config.mts
```

3. Apri l'indirizzo che stampa il terminale (di norma `http://localhost:5199`, ma se la
   porta è occupata Vite ne sceglie un'altra: **leggi l'indirizzo vero nel log**).
4. A lavoro finito **riporta `main.tsx` com'era**: il banco resta in repo, il contenuto
   di prova no.

## Perché il `.env` reale non viene letto

`vite.config.mts` imposta `envDir` sulla cartella `env-vuoto/`, che è vuota di
proposito. Vite cerca lì i file `.env` e non li trova, quindi **non legge mai** quello
di produzione nella root del progetto. È la ragione per cui questo banco è ammesso
mentre la build frontend in locale non lo è (`AGENTS.md`).

⚠️ Non cambiare `envDir` e non cancellare `env-vuoto/.gitkeep`: senza quella cartella
Vite ricadrebbe sulla root e leggerebbe i segreti veri.

## Cosa NON mettere qui

- dati reali, chiavi, indirizzi di wallet;
- chiamate al backend, anche in sola lettura;
- fixture di lavori già chiusi: quando una schermata è approvata e in produzione, il
  suo `main.tsx` di prova non serve più.
