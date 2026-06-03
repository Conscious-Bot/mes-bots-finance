#!/bin/bash
# J-day dead-man's-switch (#13 prerequisite).
#
# Fires twice on 2026-06-10 (10:30 + 13:00 backup) via cron entries :
#   30 10 10 6 * /Users/olivierlegendre/mes-bots-finance/crons/j_day_watcher.sh
#   0  13 10 6 * /Users/olivierlegendre/mes-bots-finance/crons/j_day_watcher.sh
#
# Le bot supervisor (uptime_monitor.sh) verifie la PROCESS-liveness toutes les
# 5 min. Ce watcher verifie le JOB-execution -- la difference cruciale : un bot
# alive mais dont APScheduler date trigger 2026-06-10 09:30 a silencieusement
# rate son j_day_batch_close_job passerait le test process-liveness et raterait
# pourtant l'evenement marquee.
#
# Marker canonique : `data/track_record/snapshots/2026-06.json` cree par
# `intelligence.monthly_track_record.run_monthly_track_record_job` qui est
# appele dans `bot/jobs/j_day.py:j_day_batch_close_job`. Si le snapshot existe
# AND son mtime est de today -> succes silencieux. Sinon -> ALERTE Telegram
# avec diagnostic (bot vivant ? cron loaded ? snapshot missing only ?).
#
# Idempotent : 2e run du jour confirme juste le marker.

set -u

PROJECT_DIR="/Users/olivierlegendre/mes-bots-finance"
J_DAY="2026-06-10"
TODAY="$(date +%Y-%m-%d)"
WATCHER_LOG="$PROJECT_DIR/j_day_watcher.log"
SNAPSHOT="$PROJECT_DIR/data/track_record/snapshots/2026-06.json"
BOT_LOG="$PROJECT_DIR/bot.log"
ALERT_MARKER="$PROJECT_DIR/.j_day_watcher_alert_fired"

# Guard 1 : ne tire QUE le 10 juin 2026 (eviter false fire les autres annees /
# tests manuels). Le cron entry annuel * * 10 6 * suffit pour le declenchement,
# le guard ici garantit la specificite.
if [ "$TODAY" != "$J_DAY" ]; then
    echo "$(date +'%Y-%m-%d %H:%M:%S') skip: today=$TODAY != j_day=$J_DAY" >> "$WATCHER_LOG"
    exit 0
fi

# Verification 1 : snapshot file existe ET mtime est de today.
if [ -f "$SNAPSHOT" ]; then
    SNAP_MTIME_DATE=$(stat -f %Sm -t '%Y-%m-%d' "$SNAPSHOT")
    if [ "$SNAP_MTIME_DATE" = "$J_DAY" ]; then
        echo "$(date +'%Y-%m-%d %H:%M:%S') OK: snapshot fresh ($SNAPSHOT, mtime=$SNAP_MTIME_DATE)" >> "$WATCHER_LOG"
        # Clear alert marker si premier OK apres alerte (recovery silencieuse)
        rm -f "$ALERT_MARKER"
        exit 0
    fi
    STATUS="snapshot exists but stale (mtime=$SNAP_MTIME_DATE, expected $J_DAY)"
else
    STATUS="snapshot MISSING ($SNAPSHOT)"
fi

# Verification 2 (diagnostic supplementaire) : bot alive ?
BOT_ALIVE="DOWN"
if pgrep -fi "python.*bot\.main" > /dev/null; then
    BOT_ALIVE="alive"
fi

# Verification 3 : bot.log contient le marker "J-day batch close starting" ?
BOT_LOG_MARKER="absent"
if grep -q "J-day batch close starting for $J_DAY" "$BOT_LOG" 2>/dev/null; then
    BOT_LOG_MARKER="present (job started but did not complete to snapshot)"
fi

# Throttle : ne pas spam si deja alerté ce run de la journee. Si re-fire
# du 2e cron (13:00) avec meme echec, on resend (l'utilisateur a peut-etre
# missed l'alerte de 10:30).
if [ -f "$ALERT_MARKER" ]; then
    LAST_ALERT=$(cat "$ALERT_MARKER" 2>/dev/null || echo "0")
    NOW=$(date +%s)
    SINCE=$((NOW - LAST_ALERT))
    # >2h gap -> resend. Sinon log et exit.
    if [ "$SINCE" -lt 7200 ]; then
        echo "$(date +'%Y-%m-%d %H:%M:%S') alert already fired ${SINCE}s ago, throttled" >> "$WATCHER_LOG"
        exit 1
    fi
fi

# Fire Telegram alert
if [ -f "$PROJECT_DIR/.env" ]; then
    TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' "$PROJECT_DIR/.env" | cut -d'=' -f2-)
    CHAT=$(grep '^TELEGRAM_CHAT_ID=' "$PROJECT_DIR/.env" | cut -d'=' -f2-)
    if [ -n "$TOKEN" ] && [ -n "$CHAT" ]; then
        # Newline-free message (curl encoding-safe)
        MSG="J-DAY DEAD-MAN-S-SWITCH FIRED at $(date +'%H:%M'). $STATUS. Bot process: $BOT_ALIVE. bot.log J-day marker: $BOT_LOG_MARKER. Action: ssh Mac, verify scheduler, run manually: python -c 'import asyncio; from bot.jobs.j_day import j_day_batch_close_job; asyncio.run(j_day_batch_close_job())'"
        curl -s -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" \
             -d "chat_id=$CHAT" \
             --data-urlencode "text=$MSG" > /dev/null
        date +%s > "$ALERT_MARKER"
    fi
fi

echo "$(date +'%Y-%m-%d %H:%M:%S') ALERT FIRED: $STATUS (bot=$BOT_ALIVE, log_marker=$BOT_LOG_MARKER)" >> "$WATCHER_LOG"
exit 1
