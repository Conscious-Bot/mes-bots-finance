#!/bin/bash
# Daily backup: tarball + DB snapshot + configs to ~/backups/mes-bots-finance/
# Rotation: keep 14 days, delete older. Logs to backup.log.

set -e

PROJECT_DIR="/Users/olivierlegendre/mes-bots-finance"
BACKUP_DIR="$HOME/backups/mes-bots-finance"
TS=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$BACKUP_DIR/backup.log"

mkdir -p "$BACKUP_DIR"

log() {
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $1" | tee -a "$LOG_FILE"
}

log "=== Backup start TS=$TS"

# Tarball (project sans venv/git/cache)
tar czf "$BACKUP_DIR/snapshot_${TS}.tar.gz" \
    --exclude='venv' --exclude='.backups' --exclude='__pycache__' \
    --exclude='.git' --exclude='*.pyc' --exclude='bot.log' --exclude='.pytest_cache' \
    -C "$(dirname "$PROJECT_DIR")" "$(basename "$PROJECT_DIR")" 2>>"$LOG_FILE"
TARBALL_SIZE=$(stat -f%z "$BACKUP_DIR/snapshot_${TS}.tar.gz" 2>/dev/null || stat -c%s "$BACKUP_DIR/snapshot_${TS}.tar.gz")
log "Tarball: snapshot_${TS}.tar.gz (${TARBALL_SIZE} bytes)"

# DB snapshot atomique (via SQLite backup API si possible, sinon cp)
if command -v sqlite3 >/dev/null; then
    sqlite3 "$PROJECT_DIR/data/bot.db" ".backup '$BACKUP_DIR/bot.db.${TS}'" 2>>"$LOG_FILE"
else
    cp "$PROJECT_DIR/data/bot.db" "$BACKUP_DIR/bot.db.${TS}" 2>>"$LOG_FILE"
fi
DB_SIZE=$(stat -f%z "$BACKUP_DIR/bot.db.${TS}" 2>/dev/null || stat -c%s "$BACKUP_DIR/bot.db.${TS}")
log "DB snapshot: bot.db.${TS} (${DB_SIZE} bytes)"

# Integrity check
if sqlite3 "$BACKUP_DIR/bot.db.${TS}" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
    log "DB integrity: OK"
else
    log "DB integrity: FAIL — investigation needed"
    exit 2
fi

# Rotation: delete > 14 days
find "$BACKUP_DIR" -name "snapshot_*.tar.gz" -mtime +14 -delete 2>>"$LOG_FILE" || true
find "$BACKUP_DIR" -name "bot.db.*" -mtime +14 -delete 2>>"$LOG_FILE" || true
log "Rotation done (kept last 14 days)"

log "=== Backup complete"
