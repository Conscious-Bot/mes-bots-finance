#!/bin/bash
# Daily backup: tarball + DB snapshot + integrity check + 14d rotation locale,
# puis push offsite (rsync/SSH) si destination configuree.
#
# Config offsite via env (export dans launchd plist / systemd unit / .envrc) :
#   BACKUP_REMOTE_HOST    user@host de la destination (ex: u123456@u123456.your-storagebox.de)
#   BACKUP_REMOTE_PATH    chemin distant (ex: /home/backups/presage)
#   BACKUP_REMOTE_PORT    port SSH (defaut 22 ; Hetzner Storage Box = 23)
#   BACKUP_SSH_KEY        chemin cle privee (defaut ~/.ssh/id_ed25519)
#
# Si aucun BACKUP_REMOTE_HOST : log un WARN "LOCAL-ONLY" mais le backup local
# continue. Discipline (05/06) : ne JAMAIS rester local-only silencieusement
# sur une machine distante. Mac peut tolerer local-only pendant un temps tant
# qu'il n'y a pas migration.

set -e

# PROJECT_DIR portable : derive de la position du script (scripts/ -> ..)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/mes-bots-finance}"
TS=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$BACKUP_DIR/backup.log"

mkdir -p "$BACKUP_DIR"

log() {
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $1" | tee -a "$LOG_FILE"
}

log "=== Backup start TS=$TS host=$(hostname -s)"

# Tarball (project sans venv/git/cache)
TARBALL="$BACKUP_DIR/snapshot_${TS}.tar.gz"
tar czf "$TARBALL" \
    --exclude='venv' --exclude='.backups' --exclude='__pycache__' \
    --exclude='.git' --exclude='*.pyc' --exclude='bot.log' --exclude='.pytest_cache' \
    -C "$(dirname "$PROJECT_DIR")" "$(basename "$PROJECT_DIR")" 2>>"$LOG_FILE"
TARBALL_SIZE=$(stat -f%z "$TARBALL" 2>/dev/null || stat -c%s "$TARBALL")
log "Tarball: $(basename "$TARBALL") (${TARBALL_SIZE} bytes)"

# DB snapshot atomique (via SQLite backup API si possible, sinon cp)
DB_SNAP="$BACKUP_DIR/bot.db.${TS}"
if command -v sqlite3 >/dev/null; then
    sqlite3 "$PROJECT_DIR/data/bot.db" ".backup '$DB_SNAP'" 2>>"$LOG_FILE"
else
    cp "$PROJECT_DIR/data/bot.db" "$DB_SNAP" 2>>"$LOG_FILE"
fi
DB_SIZE=$(stat -f%z "$DB_SNAP" 2>/dev/null || stat -c%s "$DB_SNAP")
log "DB snapshot: $(basename "$DB_SNAP") (${DB_SIZE} bytes)"

# Integrity check
if sqlite3 "$DB_SNAP" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
    log "DB integrity: OK"
else
    log "DB integrity: FAIL — investigation needed"
    exit 2
fi

# Push offsite (rsync/SSH). Apres integrity check : on ne pousse jamais un
# snapshot corrompu. Echec non-fatal : le local reste, l'ops doit voir le WARN.
if [ -n "$BACKUP_REMOTE_HOST" ] && [ -n "$BACKUP_REMOTE_PATH" ]; then
    PORT="${BACKUP_REMOTE_PORT:-22}"
    KEY="${BACKUP_SSH_KEY:-$HOME/.ssh/id_ed25519}"
    SSH_OPTS="-p $PORT -i $KEY -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
    log "Push offsite: $BACKUP_REMOTE_HOST:$BACKUP_REMOTE_PATH (port=$PORT)"
    if rsync -az --partial -e "ssh $SSH_OPTS" \
            "$TARBALL" "$DB_SNAP" \
            "${BACKUP_REMOTE_HOST}:${BACKUP_REMOTE_PATH}/" 2>>"$LOG_FILE"; then
        log "Push offsite: OK ($(basename "$TARBALL") + $(basename "$DB_SNAP"))"
    else
        log "Push offsite: FAIL (rsync exit $?) — local backup conserve, ALERTE OPS"
    fi
else
    log "Push offsite: SKIP — BACKUP_REMOTE_HOST/PATH non configures (LOCAL-ONLY)"
    log "  -> Acceptable sur Mac dev ; INTERDIT sur serveur distant (cf doctrine 05/06)"
fi

# Rotation locale : delete > 14 days
find "$BACKUP_DIR" -name "snapshot_*.tar.gz" -mtime +14 -delete 2>>"$LOG_FILE" || true
find "$BACKUP_DIR" -name "bot.db.*" -mtime +14 -delete 2>>"$LOG_FILE" || true
log "Rotation locale: kept last 14 days"

log "=== Backup complete"
