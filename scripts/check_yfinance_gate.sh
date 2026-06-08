#!/usr/bin/env bash
# SOCLE Phase 1b : gate CI yfinance hors shared/prices.py.
#
# But : tuer le SPOF des 14+ bypass yfinance hors du gateway canonique.
# Mode CURRENT (08/06) : SOFT. Report les violations sans build rouge,
# tant que la migration progressive des consumers n'est pas achevee.
# Mode FINAL (post-migration) : HARD. Build rouge sur violation.
#
# Pour basculer en hard : changer `exit 0` -> `exit 1` ligne finale.
#
# Cf SPEC_SOCLE.md S3 + HANDOFF_SOCLE.md S1 :
# "yfinance / yf. hors shared/prices.py = build rouge"
#
# Note : grep POSIX au lieu de rg pour portabilite CI/headless shell.

set -uo pipefail

cd "$(dirname "$0")/.."

echo "=== SOCLE gate yfinance (Phase 1b, SOFT mode) ==="

# grep recursif avec excludes -- les chemins legitimes sont prices.py + tests.
# --include="*.py" : restrict aux python files
# --exclude-dir : skip venv / .venv / __pycache__
# --exclude : skip shared/prices.py (gateway canonique)
VIOLATIONS=$(grep -rn -E 'import yfinance|from yfinance|yfinance\.|\byf\.' \
    --include="*.py" \
    --exclude-dir=venv --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=tests \
    --exclude=prices.py \
    bot shared intelligence dashboard scripts 2>/dev/null) || true

if [ -n "$VIOLATIONS" ]; then
    NB=$(echo "$VIOLATIONS" | wc -l | tr -d ' ')
    echo ""
    echo "WARNING ($NB violations) -- yfinance directement importe hors shared/prices.py."
    echo "Cible (HARD mode post-migration) : 0 violation."
    echo ""
    echo "$VIOLATIONS" | head -20
    if [ "$NB" -gt 20 ]; then
        echo "..."
        echo "(+ $((NB - 20)) violations supplementaires non affichees)"
    fi
    echo ""
    echo "Migration progressive : remplacer par prices.get() / prices.fx() qui retournent Datum."
    echo "Le gate restera SOFT (warning) jusqu'a migration finie -- puis HARD (build rouge)."
else
    echo "OK : aucune violation. Tu peux basculer en HARD mode (exit 1)."
fi

# Mode SOFT : exit 0 meme avec violations. A basculer en exit 1 post-migration.
exit 0
