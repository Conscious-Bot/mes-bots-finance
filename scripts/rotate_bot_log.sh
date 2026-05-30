#!/bin/bash
# Rotate bot.log -- a lancer MANUELLEMENT, JAMAIS automatiquement.
#
# Pourquoi pas automatique : le bot ecrit dans bot.log en append continu (via
# `nohup ... > bot.log 2>&1`). Tronquer un fichier ouvert par un autre process
# en write est subtle (offset write reste a la position pre-truncate, futurs
# writes creent un fichier sparse). Pour rotation propre = arret bot, rotate,
# restart bot.
#
# Discipline : NE PAS lancer ce script proche d'un moment de verite (10/06).
# Tip : a lancer le weekend, apres avoir verifie qu'aucun cron critique ne
# tourne dans les 2 prochaines minutes.
#
# Usage :
#   bash scripts/rotate_bot_log.sh
#
# Effet :
#   1. Verifie bot.log > 10MB (sinon skip)
#   2. Demande confirmation
#   3. Tue le bot (pkill -f bot.main)
#   4. Renomme bot.log -> bot.log.YYYY-MM-DD_HHMMSS
#   5. Gzip l'archive
#   6. Redemarre le bot avec caffeinate
#   7. Verifie nouveau PID
#   8. Rotation 14j : supprime les archives bot.log.*.gz > 14j

set -e

cd ~/mes-bots-finance

SIZE_MB=$(du -m bot.log 2>/dev/null | awk '{print $1}')
if [ -z "$SIZE_MB" ]; then
    echo "bot.log inexistant -- rien a rotate."
    exit 0
fi

echo "=== bot.log : ${SIZE_MB}MB ==="
if [ "$SIZE_MB" -lt 10 ]; then
    echo "Sous le seuil 10MB -- skip rotation."
    exit 0
fi

echo "Au-dessus du seuil. Procedure :"
echo "  1. kill bot"
echo "  2. archive bot.log -> bot.log.\$TS.gz"
echo "  3. restart bot avec caffeinate"
read -p "Confirmer (y/N) ? " ans
if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then
    echo "Annule."
    exit 0
fi

TS=$(date +%Y-%m-%d_%H%M%S)
echo "Tag rotation = $TS"

OLD_PID=$(pgrep -f "python.*bot\.main" | head -1)
if [ -n "$OLD_PID" ]; then
    echo "Kill bot PID $OLD_PID..."
    kill -9 "$OLD_PID" 2>/dev/null || true
    sleep 3
fi

mv bot.log "bot.log.$TS"
gzip "bot.log.$TS"
echo "Archive : bot.log.$TS.gz ($(du -h "bot.log.$TS.gz" | awk '{print $1}'))"

echo "Restart bot..."
caffeinate -dimsu nohup python -m bot.main > bot.log 2>&1 &
disown
sleep 5
NEW_PID=$(pgrep -f "python.*bot\.main" | head -1)
echo "Bot redemarre PID $NEW_PID"

# Rotation 14j
echo "Cleanup archives > 14j..."
find . -maxdepth 1 -name "bot.log.*.gz" -mtime +14 -delete -print

echo "Done. Verif bot.log frais :"
tail -5 bot.log
