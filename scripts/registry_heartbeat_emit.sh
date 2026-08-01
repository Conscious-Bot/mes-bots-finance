#!/bin/bash
# registry_heartbeat_emit.sh — planificateur du battement (jambe emitter).
# ============================================================
# Lance `assumption_graph.py --heartbeat`, qui touche data/.registry_heartbeat_ok
# (lu par le watcher) et imprime la ligne d'état du registre.
#
# Sur SUCCÈS (exit 0) : la ligne va au LOG (canal bas-bruit auditable), PAS de
# notification. Un push quotidien « OK » causerait l'habituation qui tue la
# détection d'absence — c'est le WATCHER (jambe séparée, mode de panne différent)
# qui rend l'absence bruyante, pas un beat positif que l'œil finit par ignorer.
#
# Sur ERREUR (exit != 0 : le moteur ne touche PAS le marqueur, un registre en
# faute ne doit pas produire de signe de vie) : push macOS LOUD immédiat — et le
# silence du marqueur sera de toute façon vu par le watcher. Deux jambes.
# ============================================================
set -uo pipefail
REPO="$HOME/mes-bots-finance"
ENGINE="$REPO/scripts/assumption_graph.py"
LOG="$REPO/logs/registry_heartbeat.log"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$REPO/logs"
cd "$REPO" || exit 1
[ -f .env ] && { set -a; . ./.env; set +a; }

LINE=$("$REPO/venv/bin/python" "$ENGINE" --heartbeat 2>>"$LOG")
RC=$?
echo "[$TS] rc=$RC $LINE" >> "$LOG"

if [ "$RC" -ne 0 ]; then
    osascript -e "display notification \"Registre EN ERREUR — aucun battement émis. ${LINE:-voir log}\" with title \"PRESAGE : registre en erreur\"" 2>/dev/null || true
fi
exit "$RC"
