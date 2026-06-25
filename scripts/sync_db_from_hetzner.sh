#!/bin/bash
# sync_db_from_hetzner.sh — Mac pull DB from VM hourly.
# ============================================================
# Mac = view-only client. VM = production source of truth.
# Avant 23/06 : Mac diverged silently (LIVING_GRAPH forks daily
# = symptom rendered visible). Cure : sync horaire automatique.
#
# Strategy : SQLite .backup on VM (consistent snapshot) -> rsync to
# Mac tmp -> backup current Mac -> atomic mv. WAL-safe.
#
# Failure mode : silent skip + log warn. NE casse JAMAIS la prod VM.
#
# Cron via launchd : ~/Library/LaunchAgents/com.olivier.presage-sync-from-vm.plist
# ============================================================
set -euo pipefail

REPO="$HOME/mes-bots-finance"
VM_HOST="presage@37.27.247.126"
VM_DB="~/mes-bots-finance/data/bot.db"
VM_SNAPSHOT="/tmp/bot.db.sync_snapshot"
LOCAL_DB="$REPO/data/bot.db"
LOCAL_TMP="$REPO/data/bot.db.sync_tmp"
LOG="$REPO/logs/sync_from_vm.log"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log() { echo "[$TS] $*" | tee -a "$LOG"; }

mkdir -p "$REPO/logs"

# 1. Reachability check (TCP probe, 3s timeout)
if ! ssh -o ConnectTimeout=3 -o BatchMode=yes "$VM_HOST" "echo ok" >/dev/null 2>&1; then
    log "SKIP : VM unreachable"
    exit 0
fi

# 2. VM-side snapshot (SQLite .backup = WAL-consistent)
if ! ssh "$VM_HOST" "sqlite3 $VM_DB \".backup $VM_SNAPSHOT\"" 2>>"$LOG"; then
    log "ABORT : VM sqlite .backup failed"
    exit 1
fi

# 3. Transfer
if ! rsync -az --timeout=30 "$VM_HOST:$VM_SNAPSHOT" "$LOCAL_TMP" 2>>"$LOG"; then
    log "ABORT : rsync failed"
    exit 1
fi

# 4. Sanity check transferred file
if ! sqlite3 "$LOCAL_TMP" "PRAGMA integrity_check" 2>/dev/null | grep -q "^ok$"; then
    log "ABORT : transferred DB integrity_check failed"
    rm -f "$LOCAL_TMP"
    exit 1
fi

# 5. Backup current Mac DB (rotation : keep last 5)
if [ -f "$LOCAL_DB" ]; then
    BACKUP="$REPO/data/bot.db.backup_sync_$(date +%Y%m%d_%H%M%S)"
    cp "$LOCAL_DB" "$BACKUP"
    # Rotate : keep last 5 sync backups (delete oldest excess)
    ls -1t "$REPO/data/bot.db.backup_sync_"* 2>/dev/null | tail -n +6 | xargs -r rm -f
fi

# 6. Atomic swap
mv "$LOCAL_TMP" "$LOCAL_DB"

# 6b. Cleanup stale WAL/SHM siblings (3e corruption 25/06 root-caused ici)
# .backup on VM = single-file consistent snapshot (no WAL).
# Mac side : bot.db-wal/-shm pre-existants pointaient vers l'ancien inode.
# Si on les laisse, SQLite tente d'appliquer le WAL stale au nouveau DB
# = "Rowid out of order" + index B-tree corrompu. Cleanup force fresh open.
rm -f "$LOCAL_DB-wal" "$LOCAL_DB-shm" "$LOCAL_TMP-wal" "$LOCAL_TMP-shm"

# 7. Cleanup VM snapshot
ssh "$VM_HOST" "rm -f $VM_SNAPSHOT" 2>/dev/null || true

SIZE_KB=$(du -k "$LOCAL_DB" | cut -f1)
log "OK : $SIZE_KB KB synced from $VM_HOST"
