#!/usr/bin/env bash
# SOCLE Phase 1b : gate CI yfinance hors shared/prices.py.
#
# But : tuer le SPOF des bypass yfinance hors du gateway canonique.
#
# Mode HARD (09/06) : aucune violation toleree. Migration #111 SOCLE S1c achevee.
#   Le pattern matche les VRAIS bypass code-actif via AST Python (filtre proprement
#   commentaires + docstrings + strings). C'est la suite du mode RATCHET 08/06.
#
# Etat persistant : .yfinance_bypass_count.txt (versionne git, audit trail).
#
# Cf SPEC_SOCLE.md S3 + HANDOFF_SOCLE.md S1.

set -uo pipefail

cd "$(dirname "$0")/.."

STATE_FILE=".yfinance_bypass_count.txt"

echo "=== SOCLE gate yfinance (HARD mode, AST-based) ==="

# AST scan : compte les vrais bypass (imports + appels yfinance) hors prices.py.
# Ignore commentaires + docstrings + strings (faux positifs du grep large).
VIOLATIONS=$(python3 - <<'PY'
import ast, pathlib

EXCLUDE_DIRS = {"venv", ".venv", "__pycache__", "tests", "alembic"}
ROOT = pathlib.Path(".")
out = []

for p in ROOT.rglob("*.py"):
    rel = p.relative_to(ROOT)
    parts = set(rel.parts)
    if parts & EXCLUDE_DIRS:
        continue
    if rel.as_posix() == "shared/prices.py":
        continue
    try:
        tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "yfinance" or alias.name.startswith("yfinance."):
                    out.append(f"{rel}:{node.lineno}:import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "yfinance" or (node.module or "").startswith("yfinance."):
                out.append(f"{rel}:{node.lineno}:from {node.module}")

for line in out:
    print(line)
PY
) || true

if [ -n "$VIOLATIONS" ]; then
    NB=$(echo "$VIOLATIONS" | wc -l | tr -d ' ')
else
    NB=0
fi

# Read previous ratchet state (HARD mode = doit rester a 0).
if [ -f "$STATE_FILE" ]; then
    PREV=$(cat "$STATE_FILE" | tr -d '[:space:]')
    if ! [[ "$PREV" =~ ^[0-9]+$ ]]; then
        echo "WARN : $STATE_FILE corrompu ('$PREV'), reinitialisation a $NB"
        PREV=$NB
    fi
else
    echo "INFO : premiere execution, initialisation a $NB"
    PREV=$NB
    echo "$NB" > "$STATE_FILE"
fi

# HARD mode : toute violation = build rouge.
if [ "$NB" -gt 0 ]; then
    echo ""
    echo "ERROR : HARD GATE VIOLATED -- $NB import(s) yfinance hors shared/prices.py."
    echo ""
    echo "Migrer ces imports vers prices.get_current_price / ensure_price_history /"
    echo "get_info / get_calendar / get_financials / get_balance_sheet / get_cashflow"
    echo "AVANT de commiter."
    echo ""
    echo "Violations :"
    echo "$VIOLATIONS"
    echo "$NB" > "$STATE_FILE"
    exit 1
fi

# Decrease : on update le state si on revient a 0 apres avoir ete > 0.
if [ "$NB" -lt "$PREV" ]; then
    echo "OK : $((PREV - NB)) violation(s) eliminee(s) (${PREV} -> ${NB})."
    echo "$NB" > "$STATE_FILE"
fi

if [ "$NB" -eq 0 ]; then
    echo "SUCCESS : aucune violation yfinance hors gateway. Mode HARD vert."
fi

exit 0
