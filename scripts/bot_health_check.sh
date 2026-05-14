#!/usr/bin/env bash
# scripts/bot_health_check.sh
#
# Multi-signal health check for mes-bots-finance bot.
# Replaces single-pgrep monitoring (which gave false negatives — see
# uptime case-bug postmortem 2026-05-14) with independent observability vectors.
#
# Usage:
#   ./scripts/bot_health_check.sh           # human-readable output
#   ./scripts/bot_health_check.sh --quiet   # only print verdict line
#
# Exit codes:
#   0 = GREEN   (all critical OK)
#   1 = RED     (one+ critical FAIL, bot still alive)
#   2 = ORANGE  (one+ critical WARN, action recommended)
#   3 = CRITICAL_BOT_DOWN (process not found — page now)
#
# Signals are split into:
#   CRITICAL — must be OK for bot to be functional
#   INFO     — observational, surface drift before it becomes critical
#
# Defensive: pure bash + sqlite3 + python3 (stdlib only). No jq dependency.

set -u  # error on unset variables
# NOT set -e — we want to continue past failed checks so we can report all

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="$REPO_ROOT/data/bot.db"
STATE_JSON="$REPO_ROOT/data/bot_state.json"
BOT_LOG="$REPO_ROOT/bot.log"
BACKUPS_DIR="$HOME/backups/mes-bots-finance"

# Thresholds (tunable)
HEARTBEAT_MAX_MIN=60          # heartbeat older than this = FAIL critical
DB_ACTIVITY_MIN_24H=1         # < this rows in 24h = WARN (bot may be silent)
ERROR_TAIL_LINES=5000         # how much of bot.log to scan for ERRORs
ERROR_COUNT_WARN=5            # > this many ERRORs in tail = WARN
SIGNAL_INGEST_MAX_MIN=180     # gmail cron is hourly, allow 3h slop = WARN
BACKUP_DISK_WARN_MB=2000      # backups dir > this = WARN
PROCESS_PATTERN="python.*bot.main"

# --- Args ---
QUIET=0
for arg in "$@"; do
    case "$arg" in
        --quiet) QUIET=1 ;;
        --help|-h)
            sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
    esac
done

# --- ANSI colors (skip if NO_COLOR set or not a TTY) ---
if [ -z "${NO_COLOR:-}" ] && [ -t 1 ]; then
    C_OK=$'\033[32m'
    C_WARN=$'\033[33m'
    C_FAIL=$'\033[31m'
    C_DIM=$'\033[2m'
    C_RESET=$'\033[0m'
else
    C_OK=""; C_WARN=""; C_FAIL=""; C_DIM=""; C_RESET=""
fi

# --- Results accumulator (TSV in temp file, parsed at end) ---
TMPF=$(mktemp -t bot_health.XXXXXX)
# Trap must preserve the script's intended exit code. If the trap's last command
# (rm) succeeds, bash would otherwise override exit code with 0.
trap 'rc=$?; rm -f "$TMPF"; exit "$rc"' EXIT

record() {
    # record STATUS SECTION NAME DETAIL
    # STATUS in {OK, WARN, FAIL, SKIP}
    # SECTION in {CRITICAL, INFO}
    printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" >> "$TMPF"
}

# --- Helpers ---

# age_minutes_since "<iso8601_timestamp>" -> echoes int minutes (negative if future), or -999 on parse fail
age_minutes_since() {
    local ts="$1"
    python3 - "$ts" <<'PYEOF'
import sys
from datetime import datetime, timezone
ts = sys.argv[1]
try:
    if ts.endswith('Z'):
        ts = ts[:-1] + '+00:00'
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        try:
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo("Europe/Paris"))
        except Exception:
            dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    print(int((now - dt).total_seconds() / 60))
except Exception:
    print(-999)
PYEOF
}

# --- Checks ---

check_process_alive() {
    local pids count etime
    pids=$(pgrep -fi "$PROCESS_PATTERN" 2>/dev/null || true)
    if [ -z "$pids" ]; then
        record FAIL CRITICAL process_alive "no process matching '$PROCESS_PATTERN'"
        return
    fi
    count=$(echo "$pids" | wc -l | tr -d ' ')
    if [ "$count" -eq 1 ]; then
        etime=$(ps -o etime= -p "$pids" 2>/dev/null | tr -d ' ' || echo "?")
        record OK CRITICAL process_alive "PID $pids, etime $etime"
    else
        local pids_csv
        pids_csv=$(echo "$pids" | tr '\n' ',' | sed 's/,$//')
        record WARN CRITICAL process_alive "$count processes (PIDs: $pids_csv) — expected 1"
    fi
}

check_heartbeat_fresh() {
    if [ ! -f "$STATE_JSON" ]; then
        record FAIL CRITICAL heartbeat_fresh "state file missing: $STATE_JSON"
        return
    fi
    local hb
    hb=$(python3 -c "import json; print(json.load(open('$STATE_JSON')).get('last_heartbeat_ts',''))" 2>/dev/null || echo "")
    if [ -z "$hb" ]; then
        record FAIL CRITICAL heartbeat_fresh "last_heartbeat_ts missing in state file"
        return
    fi
    local age
    age=$(age_minutes_since "$hb")
    if [ "$age" -eq -999 ]; then
        record FAIL CRITICAL heartbeat_fresh "parse failed for '$hb'"
    elif [ "$age" -lt 0 ]; then
        record WARN CRITICAL heartbeat_fresh "future timestamp ($hb) — clock skew?"
    elif [ "$age" -le 5 ]; then
        record OK CRITICAL heartbeat_fresh "${age}min ago"
    elif [ "$age" -le "$HEARTBEAT_MAX_MIN" ]; then
        record OK CRITICAL heartbeat_fresh "${age}min ago (≤${HEARTBEAT_MAX_MIN}min threshold)"
    else
        record FAIL CRITICAL heartbeat_fresh "${age}min ago > ${HEARTBEAT_MAX_MIN}min threshold"
    fi
}

check_db_accessible() {
    if [ ! -f "$DB_PATH" ]; then
        record FAIL CRITICAL db_accessible "DB missing: $DB_PATH"
        return
    fi
    local out rc
    out=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table'" 2>&1)
    rc=$?
    if [ "$rc" -eq 0 ] && echo "$out" | grep -qE '^[0-9]+$'; then
        record OK CRITICAL db_accessible "$out tables"
    else
        record FAIL CRITICAL db_accessible "sqlite error (rc=$rc): $out"
    fi
}

check_db_recent_activity() {
    if [ ! -f "$DB_PATH" ]; then
        record SKIP CRITICAL db_recent_activity "DB missing"
        return
    fi
    local hc sg total
    hc=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM handler_calls WHERE timestamp >= datetime('now','-1 day')" 2>/dev/null || echo 0)
    sg=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM signals WHERE timestamp >= datetime('now','-1 day')" 2>/dev/null || echo 0)
    total=$((hc + sg))
    if [ "$total" -ge "$DB_ACTIVITY_MIN_24H" ]; then
        record OK CRITICAL db_recent_activity "${hc} handler_calls + ${sg} signals in 24h"
    else
        record WARN CRITICAL db_recent_activity "${total} rows in 24h (handler_calls=${hc}, signals=${sg}) — bot may be silent"
    fi
}

check_error_rate() {
    if [ ! -f "$BOT_LOG" ]; then
        record SKIP CRITICAL error_rate "bot.log missing"
        return
    fi
    local cnt
    # grep -c prints "0" to stdout AND returns rc=1 when zero matches. The bare
    # `|| echo 0` would concat a second "0" line. Use `|| true` to keep grep's
    # stdout (always the count) and ignore rc.
    cnt=$(tail -"$ERROR_TAIL_LINES" "$BOT_LOG" 2>/dev/null | grep -c "ERROR" || true)
    if [ "$cnt" -le "$ERROR_COUNT_WARN" ]; then
        record OK CRITICAL error_rate "${cnt} ERROR in last ${ERROR_TAIL_LINES} log lines (≤${ERROR_COUNT_WARN})"
    else
        record WARN CRITICAL error_rate "${cnt} ERROR in last ${ERROR_TAIL_LINES} log lines (>${ERROR_COUNT_WARN})"
    fi
}

check_signal_ingest_freshness() {
    if [ ! -f "$DB_PATH" ]; then
        record SKIP INFO signal_ingest_freshness "DB missing"
        return
    fi
    local latest
    latest=$(sqlite3 "$DB_PATH" "SELECT MAX(timestamp) FROM signals" 2>/dev/null || echo "")
    if [ -z "$latest" ] || [ "$latest" = "" ]; then
        record WARN INFO signal_ingest_freshness "no signals in DB yet"
        return
    fi
    local age
    age=$(age_minutes_since "$latest")
    if [ "$age" -eq -999 ]; then
        record WARN INFO signal_ingest_freshness "parse failed for '$latest'"
    elif [ "$age" -le 60 ]; then
        record OK INFO signal_ingest_freshness "last signal ${age}min ago"
    elif [ "$age" -le "$SIGNAL_INGEST_MAX_MIN" ]; then
        record OK INFO signal_ingest_freshness "last signal ${age}min ago (within ${SIGNAL_INGEST_MAX_MIN}min slop)"
    else
        record WARN INFO signal_ingest_freshness "last signal ${age}min ago > ${SIGNAL_INGEST_MAX_MIN}min — gmail cron may be stuck"
    fi
}

check_disk_space() {
    local data_mb backup_mb
    if [ -d "$REPO_ROOT/data" ]; then
        data_mb=$(du -sm "$REPO_ROOT/data" 2>/dev/null | awk '{print $1}')
    else
        data_mb=0
    fi
    if [ -d "$BACKUPS_DIR" ]; then
        backup_mb=$(du -sm "$BACKUPS_DIR" 2>/dev/null | awk '{print $1}')
    else
        backup_mb=0
    fi
    local detail="data/=${data_mb}MB, backups=${backup_mb}MB"
    if [ "$backup_mb" -gt "$BACKUP_DISK_WARN_MB" ]; then
        record WARN INFO disk_space "$detail (backups > ${BACKUP_DISK_WARN_MB}MB — prune?)"
    else
        record OK INFO disk_space "$detail"
    fi
}

check_predictions_pile() {
    if [ ! -f "$DB_PATH" ]; then
        record SKIP INFO predictions_pile "DB missing"
        return
    fi
    local open_count oldest_target
    open_count=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM predictions WHERE resolved_at IS NULL" 2>/dev/null || echo 0)
    oldest_target=$(sqlite3 "$DB_PATH" "SELECT MIN(target_date) FROM predictions WHERE resolved_at IS NULL" 2>/dev/null || echo "")
    if [ -z "$oldest_target" ]; then
        oldest_target="(none)"
    fi
    record OK INFO predictions_pile "${open_count} open, oldest target_date ${oldest_target}"
}

# --- Run all checks ---
check_process_alive
check_heartbeat_fresh
check_db_accessible
check_db_recent_activity
check_error_rate
check_signal_ingest_freshness
check_disk_space
check_predictions_pile

# --- Verdict ---
PROCESS_DOWN=$(awk -F'\t' '$1=="FAIL" && $3=="process_alive" {print 1}' "$TMPF")
N_FAIL_CRIT=$(awk -F'\t' '$1=="FAIL" && $2=="CRITICAL"' "$TMPF" | wc -l | tr -d ' ')
N_WARN_CRIT=$(awk -F'\t' '$1=="WARN" && $2=="CRITICAL"' "$TMPF" | wc -l | tr -d ' ')
N_FAIL_INFO=$(awk -F'\t' '$1=="FAIL" && $2=="INFO"' "$TMPF" | wc -l | tr -d ' ')
N_WARN_INFO=$(awk -F'\t' '$1=="WARN" && $2=="INFO"' "$TMPF" | wc -l | tr -d ' ')

if [ "${PROCESS_DOWN:-0}" = "1" ]; then
    VERDICT="CRITICAL_BOT_DOWN"
    EXIT_CODE=3
elif [ "$N_FAIL_CRIT" -gt 0 ]; then
    VERDICT="RED"
    EXIT_CODE=1
elif [ "$N_WARN_CRIT" -gt 0 ]; then
    VERDICT="ORANGE"
    EXIT_CODE=2
else
    VERDICT="GREEN"
    EXIT_CODE=0
fi

# --- Output ---

color_for() {
    case "$1" in
        OK)   printf '%s' "$C_OK" ;;
        WARN) printf '%s' "$C_WARN" ;;
        FAIL) printf '%s' "$C_FAIL" ;;
        SKIP) printf '%s' "$C_DIM" ;;
        *)    printf '' ;;
    esac
}

print_section() {
    local section_filter="$1" header="$2"
    local found=0
    while IFS=$'\t' read -r status section name detail; do
        if [ "$section" = "$section_filter" ]; then
            if [ "$found" -eq 0 ]; then
                printf '\n%s:\n' "$header"
                found=1
            fi
            local c
            c=$(color_for "$status")
            printf '  %s%-4s%s  %-26s  %s\n' "$c" "$status" "$C_RESET" "$name" "$detail"
        fi
    done < "$TMPF"
}

if [ "$QUIET" -eq 0 ]; then
    printf '=== bot health check %s ===\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
    print_section CRITICAL "CRITICAL signals"
    print_section INFO "INFO signals"
    printf '\n'
fi

case "$VERDICT" in
    GREEN)
        printf 'VERDICT: %sGREEN%s\n' "$C_OK" "$C_RESET"
        ;;
    ORANGE)
        printf 'VERDICT: %sORANGE%s  (%s critical-WARN, %s info-issues)\n' \
            "$C_WARN" "$C_RESET" "$N_WARN_CRIT" "$((N_FAIL_INFO + N_WARN_INFO))"
        ;;
    RED)
        printf 'VERDICT: %sRED%s  (%s critical-FAIL, %s critical-WARN)\n' \
            "$C_FAIL" "$C_RESET" "$N_FAIL_CRIT" "$N_WARN_CRIT"
        ;;
    CRITICAL_BOT_DOWN)
        printf 'VERDICT: %sCRITICAL — bot process not found%s\n' "$C_FAIL" "$C_RESET"
        ;;
esac

exit "$EXIT_CODE"
