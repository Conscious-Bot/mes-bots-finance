#!/bin/bash
# registry_heartbeat_watch.sh — dead man's switch des JOBS PLANIFIÉS Mac.
# ============================================================
# Chaque job émet un signal POSITIF (marqueur horodaté, touché sur SUCCÈS
# seulement). Ce watcher n'alerte PAS quand une règle échoue — il alerte quand
# le SIGNAL SE TAIT. Inversion volontaire (récursion des gardes) : un watchdog
# qui "alerte sur échec" repose la question "qui garde le watchdog ?" à l'infini ;
# le dead man's switch la termine — le silence EST l'alarme.
#
# Contrat (arbitrage gérant 07/08, classe RÉPARATION — promesse Heimdall déjà
# faite) : « tout job planifié doit s'auto-signaler en cas d'échec ». Le watcher
# ne connaît pas weekly-audit — il connaît une TABLE (nom|marqueur|SLA heures).
# Ajouter un job = une ligne ; il entre automatiquement dans le contrat
# d'observabilité. Pas de nouveau sous-système : la même mécanique
# marqueur-positif / silence-alarme, × N. Origine : runs weekly des 26-27/07
# échoués en silence (DNS down, [FAIL] dans un log que personne ne lit).
# Jobs VM (weekly_synthesis dim. 18h, crons bot) = périmètre de
# health_deadman.sh côté VM, hors de cette table.
#
# Ce watcher est UNE jambe indépendante (mode de panne = son propre launchd), pas
# le fond de la pile. Emitter + watcher + attention humaine (H10) = trois jambes
# de modes de panne différents ; leur panne SIMULTANÉE et silencieuse est le
# plancher. On n'ajoute PAS de watcher-du-watcher : ce serait la régression
# qu'on refuse.
#
# Interface job : OK_MARKER touché à chaque exécution RÉUSSIE. Marqueur absent =
# pas encore armé (on ne hurle jamais sur un battement qui n'a jamais commencé,
# seulement sur un qui s'arrête).
# ============================================================
set -uo pipefail
REPO="$HOME/mes-bots-finance"
LOG="$REPO/logs/registry_heartbeat_watch.log"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$REPO/logs"
log() { echo "[$TS] $*" | tee -a "$LOG"; }

# TABLE DES JOBS PLANIFIÉS — nom | marqueur (relatif au repo) | SLA heures.
# SLA = cadence + grâce (registre quotidien : 24h+6 ; weekly : 7j+24h = 192h).
JOBS_TABLE="registre|data/.registry_heartbeat_ok|30
weekly_audit|data/.job_ok_weekly_audit|192
weekly_triggers|data/.job_ok_weekly_triggers|192"

now=$(date +%s)
while IFS='|' read -r name marker sla_h; do
    [ -n "$name" ] || continue
    ok_f="$REPO/$marker"
    alerted_f="${ok_f}_alerted"
    # Marqueur absent = job pas encore armé — dormant, jamais d'alerte.
    if [ ! -f "$ok_f" ]; then
        log "dormant [$name] : pas encore de battement (marqueur absent)"
        continue
    fi
    age_h=$(( (now - $(stat -f %m "$ok_f")) / 3600 ))
    if [ "$age_h" -ge "$sla_h" ]; then
        # Dedup : ne re-notifie pas plus d'une fois par fenêtre SLA.
        if [ ! -f "$alerted_f" ] || [ $(( now - $(stat -f %m "$alerted_f") )) -ge $((sla_h*3600)) ]; then
            osascript -e "display notification \"Job planifié ${name} MUET depuis ${age_h}h (SLA ${sla_h}h) — dernier succès trop ancien.\" with title \"PRESAGE : silence d'un job planifié\"" 2>/dev/null || true
            log "ALERT dead-man [$name] : dernier battement il y a ${age_h}h (seuil ${sla_h}h)"
            touch "$alerted_f"
        fi
    else
        rm -f "$alerted_f"
        log "OK [$name] : dernier battement il y a ${age_h}h (SLA ${sla_h}h)"
    fi
done <<< "$JOBS_TABLE"
