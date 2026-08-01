#!/bin/bash
# registry_heartbeat_watch.sh — dead man's switch du moteur-registre.
# ============================================================
# Le moteur (assumption_graph.py --heartbeat) émet un signal POSITIF quotidien
# et rafraîchit un marqueur horodaté. Ce watcher n'alerte PAS quand une règle
# échoue — il alerte quand le SIGNAL SE TAIT. Inversion volontaire (récursion
# des gardes) : un watchdog qui "alerte sur échec" repose la question "qui garde
# le watchdog ?" à l'infini ; le dead man's switch la termine — le silence EST
# l'alarme.
#
# Ce watcher est UNE jambe indépendante (mode de panne = son propre launchd), pas
# le fond de la pile. Il compense la faiblesse psychologique de "l'humain remarque
# l'absence d'un signal routinier" (habituation). Emitter + watcher + attention
# humaine (H10) = trois jambes de modes de panne différents ; aucune n'est
# parfaite, leur panne SIMULTANÉE et silencieuse est le plancher. On n'ajoute PAS
# de watcher-du-watcher : ce serait la régression qu'on refuse.
#
# Interface avec le moteur (à faire respecter côté --heartbeat) :
#   OK_MARKER touché à chaque battement réussi. Marqueur absent = pas encore armé
#   (on ne hurle jamais sur un battement qui n'a jamais commencé, seulement sur
#   un qui s'arrête).
# ============================================================
set -uo pipefail
REPO="$HOME/mes-bots-finance"
OK_MARKER="$REPO/data/.registry_heartbeat_ok"       # touché par assumption_graph.py --heartbeat
STALE_MARKER="$REPO/data/.registry_heartbeat_alerted"
LOG="$REPO/logs/registry_heartbeat_watch.log"
STALE_HOURS=30                                       # battement quotidien + grâce ; >30h = silence
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$REPO/logs"
log() { echo "[$TS] $*" | tee -a "$LOG"; }

# Marqueur absent = moteur pas encore armé. On ne hurle que sur un signal qui
# S'ARRÊTE, jamais sur un qui n'a jamais commencé.
[ -f "$OK_MARKER" ] || { log "dormant : pas encore de battement (marqueur absent)"; exit 0; }

now=$(date +%s)
age_h=$(( (now - $(stat -f %m "$OK_MARKER")) / 3600 ))
if [ "$age_h" -ge "$STALE_HOURS" ]; then
    # Dedup : ne re-notifie pas plus d'une fois par fenêtre STALE_HOURS.
    if [ ! -f "$STALE_MARKER" ] || [ $(( now - $(stat -f %m "$STALE_MARKER") )) -ge $((STALE_HOURS*3600)) ]; then
        osascript -e "display notification \"Moteur-registre MUET depuis ${age_h}h — le gardien des gardes ne bat plus. Lancer assumption_graph.py --heartbeat.\" with title \"PRESAGE : registre silencieux\"" 2>/dev/null || true
        log "ALERT dead-man : dernier battement il y a ${age_h}h (seuil ${STALE_HOURS}h)"
        touch "$STALE_MARKER"
    fi
else
    rm -f "$STALE_MARKER"
    log "OK : dernier battement il y a ${age_h}h"
fi
