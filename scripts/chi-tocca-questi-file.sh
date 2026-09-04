#!/usr/bin/env bash
# Chi altro sta lavorando sui file che sto per toccare?
#
# Nasce dal 4 settembre 2026: un altro agente (branch `codex/...`) aveva risolto
# lo stesso problema sul grafico tre ore prima, su un branch mai pubblicato.
# Nessuno se n'e' accorto e sono finite in produzione due soluzioni concorrenti.
#
# Il presidio funziona anche quando l'altro agente NON collabora e non e'
# raggiungibile: guarda git, che e' l'unica cosa che tutti condividono.
#
# Uso:
#   scripts/chi-tocca-questi-file.sh src/components/AgentTab.tsx backend/app/...
#   scripts/chi-tocca-questi-file.sh            # senza argomenti: i file che ho gia' modificato
#
# Quando eseguirlo:
#   - PRIMA di iniziare un lavoro, sui file che prevedi di toccare;
#   - PRIMA di un merge su main, che e' l'ultimo momento utile per accorgersene.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

GIORNI=${GIORNI:-7}

FILE=("$@")
if [ ${#FILE[@]} -eq 0 ]; then
  mapfile -t FILE < <(git diff --name-only HEAD; git diff --name-only --cached)
  if [ ${#FILE[@]} -eq 0 ]; then
    echo "Nessun file indicato e nessuna modifica in corso."
    echo "Uso: $0 <file> [file...]"
    exit 0
  fi
  echo "File presi dalle modifiche in corso:"
  printf '  %s\n' "${FILE[@]}"
  echo
fi

git fetch origin --quiet 2>/dev/null

echo "== BRANCH NON MERGIATI IN main =="
trovato=0
while read -r b; do
  [ -z "$b" ] && continue
  n=$(git rev-list --count "main..$b" 2>/dev/null) || continue
  [ "${n:-0}" -eq 0 ] && continue
  # Tocca qualcuno dei file che mi interessano?
  toccati=$(git diff --name-only "main...$b" -- "${FILE[@]}" 2>/dev/null)
  if [ -n "$toccati" ]; then
    trovato=1
    echo
    echo "  🔴 $b  ($n commit non in main)"
    git log -1 --format='     ultimo: %ad  %s' --date=format:'%d/%m %H:%M' "$b"
    echo "     file in comune:"
    printf '       %s\n' $toccati
  fi
done < <(git branch -a --format='%(refname:short)' | grep -v HEAD | sed 's|^origin/||' | sort -u | grep -v '^main$')

[ "$trovato" -eq 0 ] && echo "  nessuno tocca questi file."

echo
echo "== COMMIT RECENTI SU QUESTI FILE (ultimi $GIORNI giorni, TUTTI i branch) =="
recenti=$(git log --all --since="$GIORNI days ago" \
  --format='  %h %ad %<(22,trunc)%an %s' --date=format:'%d/%m %H:%M' \
  -- "${FILE[@]}" 2>/dev/null | head -20)
if [ -n "$recenti" ]; then
  echo "$recenti"
else
  echo "  nessuno."
fi

echo
echo "Se compare un branch in rosso: guardalo PRIMA di scrivere codice."
echo "Due soluzioni allo stesso problema costano piu' di cinque minuti di lettura."
