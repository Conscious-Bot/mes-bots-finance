#!/bin/bash
# backup_vault_offsite.sh — backup quotidien du vault Obsidian + push offsite VM.
# ============================================================
# Le vault est le SEUL actif mono-copie du système : la VM ne peut pas atteindre
# l'API REST Obsidian (127.0.0.1), donc seul le Mac peut le sauvegarder. C'est le
# cerveau NON-régénérable (doctrine, invalidations, logs tribunal). Ce job :
#   backup_vault.py -> tarball local -> rsync offsite VM -> preuve checksum.
#
# Fail-LOUD (condition H9, cf L27 : cohérence MÉCANIQUE, jamais vigilante) :
#   - échec TRANSIENT (Obsidian fermé, VM injoignable) = SKIP + log, PAS d'alarme
#     (une occurrence isolée n'est pas un incident) ;
#   - le heartbeat de STALENESS (trap EXIT, seuil 48h) est le mécanisme LOUD :
#     un backup muet >48h => notification macOS + log ALERT. Copie le pattern de
#     sync_db_from_hetzner.sh (mémoire mac-sync-launchd-silent-fail : 7 jours de
#     SKIP muet = le défaut à ne JAMAIS reproduire).
# ============================================================
set -uo pipefail  # PAS -e : on gère les erreurs en SKIP LOUD nous-mêmes

REPO="$HOME/mes-bots-finance"
VM_HOST="presage@37.27.247.126"
VM_DIR="vault_backups_from_mac"
VAULT_DIR="$HOME/presage_vault_backups"
LOG="$REPO/logs/backup_vault.log"
OK_MARKER="$REPO/data/.vault_backup_last_ok"
STALE_MARKER="$REPO/data/.vault_backup_stale_alerted"
STALE_HOURS=48
SSH_BASE="-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o BatchMode=yes"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

mkdir -p "$REPO/logs"
log() { echo "[$TS] $*" | tee -a "$LOG"; }

# Heartbeat de péremption : si le dernier backup OK est trop vieux, hurler. Couvre
# le cas "le job ne pousse plus" tant que launchd le déclenche. Dedup via marker.
check_staleness() {
    [ -f "$OK_MARKER" ] || return 0
    local now age_h
    now=$(date +%s)
    age_h=$(( (now - $(stat -f %m "$OK_MARKER")) / 3600 ))
    if [ "$age_h" -ge "$STALE_HOURS" ]; then
        if [ ! -f "$STALE_MARKER" ] || [ $(( now - $(stat -f %m "$STALE_MARKER") )) -ge $((STALE_HOURS*3600)) ]; then
            osascript -e "display notification \"Backup vault muet depuis ${age_h}h — le cerveau documentaire (mono-copie Mac) n'est plus protégé offsite\" with title \"PRESAGE : backup vault stale\"" 2>/dev/null || true
            log "ALERT staleness : dernier backup vault OK il y a ${age_h}h"
            touch "$STALE_MARKER"
        fi
    else
        rm -f "$STALE_MARKER"
    fi
}
trap 'check_staleness' EXIT

log "=== vault backup start"
if [ -f "$REPO/.env" ]; then set -a; . "$REPO/.env"; set +a; fi

# 1. Générer le tarball (backup_vault.py). Requiert Obsidian ouvert (API localhost).
if ! "$REPO/venv/bin/python3" "$REPO/scripts/backup_vault.py" >>"$LOG" 2>&1; then
    log "SKIP : backup_vault.py échoué (Obsidian fermé ? API muette) — staleness veillera"
    exit 0
fi
VAULT=$(ls -t "$VAULT_DIR"/*.tgz 2>/dev/null | head -1)
[ -n "$VAULT" ] || { log "SKIP : aucun tarball produit"; exit 0; }
B=$(basename "$VAULT")

# 2. Push offsite VM (config ssh réutilisée du sync). Reachability implicite.
if ! ssh $SSH_BASE "$VM_HOST" "mkdir -p ~/$VM_DIR" 2>>"$LOG"; then
    log "SKIP : VM injoignable — tarball local créé mais NON poussé (SPOF) — staleness veillera"
    exit 0
fi
if ! rsync -az --timeout=30 -e "ssh $SSH_BASE" "$VAULT" "$VM_HOST:$VM_DIR/" 2>>"$LOG"; then
    log "SKIP : rsync offsite échoué — staleness veillera"
    exit 0
fi

# 3. Preuve d'intégrité cross-wire (un backup non vérifié n'est pas un backup).
LOCAL_SUM=$(shasum -a 256 "$VAULT" | cut -d' ' -f1)
VM_SUM=$(ssh $SSH_BASE "$VM_HOST" "shasum -a 256 ~/$VM_DIR/$B | cut -d' ' -f1" 2>>"$LOG")
if [ "$LOCAL_SUM" != "$VM_SUM" ]; then
    log "SKIP : checksum mismatch offsite (local=$LOCAL_SUM vm=$VM_SUM) — staleness veillera"
    exit 0
fi

# 4. Rotation : garder les 14 derniers (local + offsite). Tarballs ~260 Ko.
ls -1t "$VAULT_DIR"/PRESAGE_vault_*.tgz 2>/dev/null | tail -n +15 | xargs -r rm -f
ssh $SSH_BASE "$VM_HOST" "ls -1t ~/$VM_DIR/PRESAGE_vault_*.tgz | tail -n +15 | xargs -r rm -f" 2>>"$LOG" || true

# 5. Succès : marker frais => staleness non déclenchée.
touch "$OK_MARKER"
rm -f "$STALE_MARKER"
log "OK : $B poussé offsite + vérifié (sha256 ${LOCAL_SUM:0:12}…)"
