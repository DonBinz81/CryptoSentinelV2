# Path Verifica Backend In AGENTS

## 1. COSA È STATO FATTO

- Aggiornato `AGENTS.md` con il percorso corretto dell'interprete Python per le verifiche backend su Windows.
- Aggiornato `docs/PROJECT_STRUCTURE.md` per riflettere la nuova regola operativa.

## 2. COME È STATO FATTO

- Aggiunta una regola in `Verification Expectations`:
  `backend\.venv\Scripts\python.exe`
- Specificato di non assumere l'esistenza di `.venv\Scripts\python.exe` nella root del repository.

## 3. COSA È STATO VERIFICATO

- Verificato che `backend\.venv\Scripts\python.exe` esiste nel workspace.
- Verificato che lo script `backend/scripts/run_backend.ps1` usa proprio il virtualenv sotto `backend\.venv`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno.

## 5. QUESTIONI APERTE

- Nessuna.

## 6. STATO DELIVERABLE

- Implementato.
