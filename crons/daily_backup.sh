#!/bin/bash
# Daily backup of bot data. Runs at 23:00 via cron.

PROJECT_DIR="/Users/olivierlegendre/mes-bots-finance"
BACKUP_DIR="$PROJECT_DIR/data/backups"
DATE=$(date +%Y%m%d_%H%M%S)
LOG="$BACKUP_DIR/backup.log"

mkdir -p "$BACKUP_DIR"

tar czf "$BACKUP_DIR/data_$DATE.tar.gz" \
    -C "$PROJECT_DIR" \
    data/bot.db data/bot_state.json 2>>"$LOG"

if [ $? -eq 0 ]; then
    SIZE=$(du -h "$BACKUP_DIR/data_$DATE.tar.gz" | cut -f1)
    echo "$(date +'%Y-%m-%d %H:%M:%S') OK backup $DATE ($SIZE)" >> "$LOG"
else
    echo "$(date +'%Y-%m-%d %H:%M:%S') FAIL backup $DATE" >> "$LOG"
fi

# Rotation: keep last 30 days
find "$BACKUP_DIR" -name "data_*.tar.gz" -mtime +30 -delete 2>>"$LOG"
