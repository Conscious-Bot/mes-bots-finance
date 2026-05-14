#!/bin/bash
# Check if bot process is alive. Runs every 5min via cron.
# Sends Telegram alert if down (rate-limited to 1/h).

PROJECT_DIR="/Users/olivierlegendre/mes-bots-finance"
LOG="$PROJECT_DIR/uptime.log"
ALERT_MARKER="$PROJECT_DIR/.last_alert"

if pgrep -fi "python.*bot\.main" > /dev/null; then
    echo "$(date +'%Y-%m-%d %H:%M:%S') OK alive" >> "$LOG"
    rm -f "$ALERT_MARKER"
    exit 0
fi

echo "$(date +'%Y-%m-%d %H:%M:%S') FAIL bot down" >> "$LOG"

# Rate limit: only alert if last alert > 1h ago
NOW=$(date +%s)
if [ -f "$ALERT_MARKER" ]; then
    LAST_ALERT=$(cat "$ALERT_MARKER")
    DIFF=$((NOW - LAST_ALERT))
    if [ $DIFF -lt 3600 ]; then
        exit 0
    fi
fi

# Read credentials from .env
if [ -f "$PROJECT_DIR/.env" ]; then
    TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' "$PROJECT_DIR/.env" | cut -d'=' -f2-)
    CHAT=$(grep '^TELEGRAM_CHAT_ID=' "$PROJECT_DIR/.env" | cut -d'=' -f2-)
    if [ -n "$TOKEN" ] && [ -n "$CHAT" ]; then
        curl -s -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" \
             -d "chat_id=$CHAT" \
             -d "text=ALERT bot finance down at $(date +'%H:%M')" > /dev/null
        echo "$NOW" > "$ALERT_MARKER"
    fi
fi
