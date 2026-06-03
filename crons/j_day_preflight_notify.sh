#!/bin/bash
# J-day pre-flight Telegram reminder.
#
# Fires UNE FOIS sur 2026-06-09 09:00 (J-1 matin) via cron entry :
#   0 9 9 6 * /Users/olivierlegendre/mes-bots-finance/crons/j_day_preflight_notify.sh
#
# Pourquoi : la pre-flight verification (j_day_watcher.sh smoke test +
# scheduler verification + .env consistency) ne peut pas etre auto-triggered
# par un humain qui oublie. Cron envoie un push Telegram, l'humain fait la
# verif manuelle. Mecanisme identique au j_day watcher : la realite garantit
# le rappel, pas la memoire.
#
# Guard date : fire seulement le 09 juin 2026 (le cron entry annuel * * 9 6 *
# fired aussi sur les futurs 9 juin -- le guard ici limite a 2026 strict).

set -u

PROJECT_DIR="/Users/olivierlegendre/mes-bots-finance"
PREFLIGHT_DAY="2026-06-09"
TODAY="$(date +%Y-%m-%d)"
NOTIFY_LOG="$PROJECT_DIR/j_day_preflight.log"

if [ "$TODAY" != "$PREFLIGHT_DAY" ]; then
    echo "$(date +'%Y-%m-%d %H:%M:%S') skip: today=$TODAY != preflight=$PREFLIGHT_DAY" >> "$NOTIFY_LOG"
    exit 0
fi

# Read Telegram creds
if [ -f "$PROJECT_DIR/.env" ]; then
    TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' "$PROJECT_DIR/.env" | cut -d'=' -f2-)
    CHAT=$(grep '^TELEGRAM_CHAT_ID=' "$PROJECT_DIR/.env" | cut -d'=' -f2-)
    if [ -n "$TOKEN" ] && [ -n "$CHAT" ]; then
        MSG="J-1 PREFLIGHT (J-day demain 2026-06-10). Verifier maintenant : (1) Mac sera awake demain 09:30 et 14:00 (laptop branche + lid ouvert OU caffeinate). (2) HEALTHCHECKS_J_DAY_URL configure dans .env, check createe sur healthchecks.io avec cron 30 9 10 6 *, grace 4h. (2b) ALARM ARMING TEST : source .env puis curl \$HEALTHCHECKS_J_DAY_URL maintenant, ouvrir healthchecks dashboard, CONFIRMER que le ping atterrit + next-expected timestamp aligne 2026-06-10 09:30 + grace 4h. Un dead-man-s-switch ne compte que si l'alarme s'arme et se desarme correctement sur l'horloge reelle. (3) Smoke test : bash crons/j_day_watcher.sh en simulant J_DAY=today + creer fake snapshot data/track_record/snapshots/2026-06.json (cleanup apres). (4) Verifier j_day_batch_close_job registered : grep j_day_batch bot.log OU /jobs Telegram. (5) Brier reading contract : 2 lignes [YOUR CALL] revisees et committed dans docs/j_day_reading_contract.md."
        curl -s -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" \
             -d "chat_id=$CHAT" \
             --data-urlencode "text=$MSG" > /dev/null
        echo "$(date +'%Y-%m-%d %H:%M:%S') preflight notification sent" >> "$NOTIFY_LOG"
        exit 0
    fi
fi

echo "$(date +'%Y-%m-%d %H:%M:%S') ERROR: could not send (creds missing)" >> "$NOTIFY_LOG"
exit 1
