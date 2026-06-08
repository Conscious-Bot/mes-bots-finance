#!/usr/bin/env bash
# SOCLE Phase 1b : gate CI yfinance hors shared/prices.py.
#
# But : tuer le SPOF des bypass yfinance hors du gateway canonique.
#
# Mode RATCHET (08/06) : le compteur ne peut que DECROITRE. Build rouge si
#   un 20e bypass apparait alors qu'on en avait 19. Permet migration progressive
#   sans sweep tout-en-une-fois (la doctrine "type-quand-tu-touches" de GLOSSARY).
#
# Mode HARD (automatique quand count atteint 0) : build rouge sur toute violation.
#
# Etat persistant : .yfinance_bypass_count.txt (versionne git, audit trail).
#
# Cf SPEC_SOCLE.md S3 + HANDOFF_SOCLE.md S1.

set -uo pipefail

cd "$(dirname "$0")/.."

STATE_FILE=".yfinance_bypass_count.txt"

echo "=== SOCLE gate yfinance (Phase 1b, RATCHET mode) ==="

# Count current violations
VIOLATIONS=$(grep -rn -E 'import yfinance|from yfinance|yfinance\.|\byf\.' \
    --include="*.py" \
    --exclude-dir=venv --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=tests \
    --exclude=prices.py \
    bot shared intelligence dashboard scripts 2>/dev/null) || true

if [ -n "$VIOLATIONS" ]; then
    NB=$(echo "$VIOLATIONS" | wc -l | tr -d ' ')
else
    NB=0
fi

# Read previous ratchet state (or initialize if missing)
if [ -f "$STATE_FILE" ]; then
    PREV=$(cat "$STATE_FILE" | tr -d '[:space:]')
    # Sanity check : valid integer
    if ! [[ "$PREV" =~ ^[0-9]+$ ]]; then
        echo "WARN : $STATE_FILE corrompu ('$PREV'), reinitialisation a $NB"
        PREV=$NB
    fi
else
    echo "INFO : premiere execution, initialisation ratchet a $NB"
    PREV=$NB
    echo "$NB" > "$STATE_FILE"
fi

# Ratchet : le count ne peut que decroitre. Si NB > PREV -> regression = build rouge.
if [ "$NB" -gt "$PREV" ]; then
    DELTA=$((NB - PREV))
    echo ""
    echo "ERROR : RATCHET BROKEN -- $DELTA nouvelle(s) violation(s) yfinance apparue(s)."
    echo "  Count precedent : $PREV"
    echo "  Count actuel    : $NB"
    echo ""
    echo "Le ratchet decroissant-only interdit la regression. Migrer les nouveaux"
    echo "bypass vers prices.get() / prices.fx() AVANT de commiter."
    echo ""
    echo "Echantillon des violations (head 20) :"
    echo "$VIOLATIONS" | head -20
    exit 1
fi

# Count <= PREV : on accepte. Update state si decroissance.
if [ "$NB" -lt "$PREV" ]; then
    echo "OK : $((PREV - NB)) violation(s) eliminee(s) depuis dernier run (${PREV} -> ${NB})."
    echo "$NB" > "$STATE_FILE"
fi

if [ "$NB" -eq 0 ]; then
    echo "SUCCESS : aucune violation. Gate peut basculer en HARD definitif."
    exit 0
fi

# Compte stable
if [ "$NB" -eq "$PREV" ]; then
    echo "INFO : $NB violations (stable depuis dernier run)."
    if [ "$NB" -gt 0 ]; then
        echo "      $NB bypass yfinance hors prices.py a migrer (type-quand-tu-touches)."
    fi
fi

# Mode HARD automatique si count = 0 (deja exit 0 ci-dessus).
# Mode RATCHET : exit 0 tant que NB <= PREV.
exit 0
