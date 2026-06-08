#!/bin/bash
# Gate ratchet SPEC_MONEY_INVARIANT §4 + L27 — decreasing-only.
#
# Bloque toute augmentation du compteur de violations. Chaque commit qui
# migre un site fait baisser le ratchet ; aucun ne peut le remonter.
#
# Deux gates :
#   (1) Multiplication × fx hors shared/money.py (le SEUL converter autorise)
#   (2) Arithmétique ad-hoc sur baselines monétaires (entry_price, avg_cost,
#       stop_price, target_full, target_partial) hors shared/money.pct_change
#
# Le compteur courant vit dans scripts/check_money_invariant.baseline ;
# il est mis à jour DECREASING-ONLY (ratchet) — toute violation supplémentaire
# casse le build, toute migration réussie baisse le compteur.
#
# Usage :
#   ./scripts/check_money_invariant.sh            # check (build rouge si counter monte)
#   ./scripts/check_money_invariant.sh --update   # met à jour le baseline (si counter baisse)

set -euo pipefail

BASELINE_FILE="scripts/check_money_invariant.baseline"
ROOTS="bot shared intelligence dashboard"

# Gate 1 : × fx ad-hoc
count_fx() {
    grep -rnE "\* fx_rate_to_eur|fx_rate_to_eur \*|\* fx_at_purchase|fx_at_purchase \*" \
        --include="*.py" -- $ROOTS 2>/dev/null \
        | grep -v __pycache__ \
        | grep -v "shared/money.py" \
        | wc -l | awk '{print $1}'
}

# Gate 2 : arithmétique ad-hoc sur baselines monétaires
count_baselines() {
    grep -rnE "\b(entry_price|avg_cost|stop_price|target_full|target_partial)\b[[:space:]]*[*/+-]" \
        --include="*.py" -- $ROOTS 2>/dev/null \
        | grep -v __pycache__ \
        | grep -v "shared/money.py" \
        | grep -v "pct_change" \
        | wc -l | awk '{print $1}'
}

FX=$(count_fx)
BASELINES=$(count_baselines)
CURRENT="fx=$FX baselines=$BASELINES"

if [[ ! -f "$BASELINE_FILE" ]]; then
    echo "First run — creating baseline at $CURRENT"
    echo "$CURRENT" > "$BASELINE_FILE"
    exit 0
fi

EXPECTED=$(cat "$BASELINE_FILE")
EXPECTED_FX=$(echo "$EXPECTED" | grep -oE "fx=[0-9]+" | cut -d= -f2)
EXPECTED_BASELINES=$(echo "$EXPECTED" | grep -oE "baselines=[0-9]+" | cut -d= -f2)

if [[ "${1:-}" == "--update" ]]; then
    if (( FX <= EXPECTED_FX )) && (( BASELINES <= EXPECTED_BASELINES )); then
        echo "Counter DECREASED — updating baseline: $EXPECTED -> $CURRENT"
        echo "$CURRENT" > "$BASELINE_FILE"
        exit 0
    fi
    echo "ERROR: counter went UP — refusing to update baseline."
    echo "  expected: $EXPECTED"
    echo "  current : $CURRENT"
    echo "  Fix the violations BEFORE updating baseline."
    exit 1
fi

# Check mode
if (( FX > EXPECTED_FX )) || (( BASELINES > EXPECTED_BASELINES )); then
    echo "L27 RATCHET VIOLATION: money_invariant counter increased"
    echo "  expected (baseline): $EXPECTED"
    echo "  current            : $CURRENT"
    echo ""
    echo "Some new violation(s) were introduced. SPEC_MONEY_INVARIANT §4 — every"
    echo "money baseline must be a Datum[Monetary], every ratio must go through"
    echo "shared.money.pct_change, every conversion through shared.money.in_eur."
    echo ""
    echo "If you intentionally added a violation (rare — temporary scaffolding"
    echo "during migration), update the baseline manually after explaining why."
    echo ""
    echo "Locations (gate 1 — × fx) :"
    grep -rnE "\* fx_rate_to_eur|fx_rate_to_eur \*|\* fx_at_purchase|fx_at_purchase \*" \
        --include="*.py" -- $ROOTS 2>/dev/null \
        | grep -v __pycache__ \
        | grep -v "shared/money.py" | head -10
    echo ""
    echo "Locations (gate 2 — baselines ad-hoc) :"
    grep -rnE "\b(entry_price|avg_cost|stop_price|target_full|target_partial)\b[[:space:]]*[*/+-]" \
        --include="*.py" -- $ROOTS 2>/dev/null \
        | grep -v __pycache__ \
        | grep -v "shared/money.py" \
        | grep -v "pct_change" | head -10
    exit 1
fi

if (( FX < EXPECTED_FX )) || (( BASELINES < EXPECTED_BASELINES )); then
    echo "L27 RATCHET: counter decreased — run with --update to ratchet baseline"
    echo "  expected: $EXPECTED"
    echo "  current : $CURRENT"
    exit 0  # pas un échec, juste un rappel
fi

echo "OK money_invariant: $CURRENT (unchanged vs baseline)"
exit 0
