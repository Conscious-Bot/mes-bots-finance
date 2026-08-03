#!/bin/bash
# health_deadman.sh — dead-man's-switch UNIQUE de PRESAGE (tourne sur la VM).
# ============================================================
# UN battement, pas un framework Heimdall (conseil 03/08 : « pas un 13e gardien,
# un cron unique »). Le disque plein du 02-03/08 a prouvé le besoin : UNE racine
# physique (disque 100%) -> writes tronqués -> token.json à 0 (Gmail mort 34h),
# sync muet, backup mort. Ce cron aurait crié TOUTE la cascade en amont, d'un coup.
#
# Vérifie les organes vitaux ; ping Telegram LOUD sur toute anomalie. Fail-safe :
# un check qui échoue = un check en moins, jamais un crash (le dead-man ne doit
# pas mourir en silence lui-même).
# ============================================================
set -uo pipefail
REPO="$HOME/mes-bots-finance"
BK="$HOME/backups/mes-bots-finance"
NOW=$(date +%s)
ALERTS=()

# 1. DISQUE — la racine du 03/08. Seuil 85% (marge avant troncature des writes).
USE=$(df / 2>/dev/null | awk 'NR==2{gsub("%","",$5); print $5}')
if [ -n "$USE" ] && [ "$USE" -ge 85 ]; then
    ALERTS+=("disque / à ${USE}% (>85%) — writes bientôt tronqués")
fi

# 2. BACKUP DB frais < 26h (H9).
LAST=$(ls -t "$BK"/bot.db.20* 2>/dev/null | grep -v journal | head -1)
if [ -n "$LAST" ]; then
    AGE=$(( (NOW - $(stat -c %Y "$LAST")) / 3600 ))
    [ "$AGE" -ge 26 ] && ALERTS+=("backup DB muet depuis ${AGE}h")
else
    ALERTS+=("aucun backup DB trouvé")
fi

# 3. token.json Gmail non-vide (l'incident EXACT du 02/08 : 0 octet = auth cassée).
[ -s "$REPO/token.json" ] || ALERTS+=("token.json vide/absent — auth Gmail cassée")

# 4. Bot vivant (sinon zéro ingestion -> digest vide, comme le 02/08).
pgrep -f 'bot.main' >/dev/null || ALERTS+=("bot.main ABSENT — ingestion morte")

# Émission : Telegram LOUD sur anomalie, log OK sinon (battement positif auditable).
if [ ${#ALERTS[@]} -gt 0 ]; then
    MSG="⚠️ PRESAGE dead-man ($(hostname -s)) : $(printf '%s · ' "${ALERTS[@]}")"
    if [ -f "$REPO/.env" ]; then
        ( cd "$REPO" && set -a && . ./.env && set +a \
          && venv/bin/python -c "import sys; from shared import notify; notify.send_text(sys.argv[1])" "$MSG" ) 2>/dev/null
    fi
    echo "$(date -u +%FT%TZ) ALERT: $MSG"
else
    echo "$(date -u +%FT%TZ) OK: disque ${USE}% · backup frais · token OK · bot vivant"
fi
