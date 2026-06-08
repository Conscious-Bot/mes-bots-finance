#!/usr/bin/env bash
# SOCLE substrat sémantique : gate CI no-hardcoded-alerts.
#
# But : aucun panel ne hardcode une couleur d'alarme literale -- toute couleur
# d'alerte vient de shared.alert_vocabulary.render_token(get_word(name)).
#
# Cf SPEC_ALERT_VOCABULARY.md §7.
#
# Mode RATCHET (08/06) : meme principe que check_yfinance_gate.sh.
# Le compteur ne peut que DECROITRE. Build rouge si un littéral d'alarme
# apparaît alors qu'on en avait moins.
#
# Etat persistant : .alerts_hardcoded_count.txt (versionne git, audit trail).
#
# Patterns interdits : hex literal '#RRGGBB' ou color name dans panels render*
# associé à un mot d'alerte (warning, danger, alert, erosion, critical, fail).

set -uo pipefail

cd "$(dirname "$0")/.."

STATE_FILE=".alerts_hardcoded_count.txt"

echo "=== SOCLE gate no-hardcoded-alerts (RATCHET mode) ==="

# Patterns : couleurs CSS literal liees a un mot d'alerte semantique.
# On scan dashboard/render*.py uniquement (pas shared/ ni tests/ qui peuvent
# definir les tokens canoniques).
VIOLATIONS=$(grep -rn -E '"#[a-fA-F0-9]{6,8}"' dashboard/render.py 2>/dev/null \
    | grep -iE '(warning|danger|critical|erosion|invalidation|alert|fail-closed|stale)' \
    || true)

if [ -n "$VIOLATIONS" ]; then
    NB=$(echo "$VIOLATIONS" | wc -l | tr -d ' ')
else
    NB=0
fi

# Read previous ratchet state (or initialize if missing)
if [ -f "$STATE_FILE" ]; then
    PREV=$(cat "$STATE_FILE" | tr -d '[:space:]')
    if ! [[ "$PREV" =~ ^[0-9]+$ ]]; then
        echo "WARN : $STATE_FILE corrompu ('$PREV'), reinitialisation a $NB"
        PREV=$NB
    fi
else
    echo "INFO : premiere execution, initialisation ratchet a $NB"
    PREV=$NB
    echo "$NB" > "$STATE_FILE"
fi

# Ratchet : count ne peut que decroitre.
if [ "$NB" -gt "$PREV" ]; then
    DELTA=$((NB - PREV))
    echo ""
    echo "ERROR : RATCHET BROKEN -- $DELTA nouveau(x) littéral(aux) d'alarme hard-codé(s)."
    echo "  Count precedent : $PREV"
    echo "  Count actuel    : $NB"
    echo ""
    echo "Le ratchet décroissant-only interdit la régression. Migrer les nouveaux"
    echo "littéraux vers shared.alert_vocabulary.render_token(get_word(name)) AVANT"
    echo "de commiter."
    echo ""
    echo "Échantillon des violations (head 20) :"
    echo "$VIOLATIONS" | head -20
    exit 1
fi

# Decroissance : OK + update state
if [ "$NB" -lt "$PREV" ]; then
    echo "OK : $((PREV - NB)) littéral(aux) éliminé(s) depuis dernier run (${PREV} -> ${NB})."
    echo "$NB" > "$STATE_FILE"
fi

if [ "$NB" -eq 0 ]; then
    echo "SUCCESS : aucun littéral d'alarme hard-codé. Gate peut basculer HARD."
    exit 0
fi

# Stable
if [ "$NB" -eq "$PREV" ]; then
    echo "INFO : $NB littéral(aux) d'alarme hard-codé(s) (stable depuis dernier run)."
    if [ "$NB" -gt 0 ]; then
        echo "      Migration type-quand-tu-touches via render_token(get_word(name))."
    fi
fi

exit 0
