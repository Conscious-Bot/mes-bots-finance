"""Garde mecanisee de la barriere §0 chantier #150 (couche redevabilite).

Cure session 13/06 : la barriere §0 ("Claude Code NE COMMENCE AUCUNE unite
de ce chantier tant que G1-G5 ne sont pas verts ET observation post-Couche 0
n'a pas eu lieu plusieurs semaines") etait une RÈGLE DECRETEE par Olivier
mais pas MECANISEE par un check automatique. Si Olivier (ou Claude futur)
oublie la barriere, rien ne l'arretait.

Ce test materialise la barriere : il echoue si l'un des 4 modules Unit A/B/C/D
est cree avant que les conditions soient remplies. La discipline n'est plus
"Claude se rappelle" mais "le test te frappe a chaque commit".

Conditions de levee de la barriere (a editer manuellement quand vrai) :
1. G1 batch Brier resolu (>=40 predictions resolues)
2. G2 sentinelles loggees (>=10 event/data avec target_date Dec 2026-Dec 2027)
3. G3 18+ triggers _no_delete
4. G4 cure add_sell.realized_pnl_event verifiee
5. G5 baseline pytest exit 0 (= 1888/1888 tests)
6. ✱ Observation post-Couche 0 (nulle paresseuse) parle plusieurs semaines

Le critere ✱ est volontairement non-mecanique : il exige un acte conscient
d'Olivier. Quand pret, editer BARRIERE_LEVEE = True dans ce fichier ET
commit. Le commit lui-meme devient le marqueur audit-able.

Lien : docs/CHANTIER_REDEVABILITY_LAYER.md §0, docs/adrs/010-decision-accountability-layer.md
"""
from __future__ import annotations

from pathlib import Path

import pytest

# ─── Levee manuelle de la barriere ────────────────────────────────────────────
# Editer cette constante a True UNIQUEMENT quand TOUTES les conditions sont
# rencontrees ET qu'Olivier confirme explicitement "go Unit A". Le commit de
# levee devient le marqueur d'audit traçable dans git log.
BARRIERE_LEVEE: bool = False


# Modules d'Unit A/B/C/D que la barriere protege.
# Si l'un d'eux existe et BARRIERE_LEVEE=False, ce test echoue.
PROTECTED_MODULES = {
    "intelligence/null_benchmark.py": "Unit A — Couche 0 (juge, kill-switch)",
    "intelligence/thesis_registry.py": "Unit B — Couche 1 (registre unifié)",
    "intelligence/narrative_drift.py": "Unit C — Couche 2a (canari)",
    "intelligence/bias_pnl.py": "Unit D — Couche 2b (prix indiscipline)",
}

REPO = Path(__file__).resolve().parent.parent


def test_chantier_150_barriere_enforced():
    """Barriere §0 chantier #150 : tant que BARRIERE_LEVEE=False, aucun module
    d'Unit A/B/C/D ne doit exister dans le repo. La barriere se leve par un
    EDIT EXPLICITE de ce test (BARRIERE_LEVEE=True) + commit, pas par
    inadvertance.

    Si tu vois ce test fail, deux possibilites :
    (a) tu (ou Claude futur) as cree un module d'Unit A/B/C/D sans lever la
        barriere → ROLLBACK. Relire docs/CHANTIER_REDEVABILITY_LAYER.md §0.
    (b) tu es PRÊT a lancer Unit A et toutes les conditions G1-G5 + observation
        sont remplies → edit BARRIERE_LEVEE=True dans CE fichier ET commit en
        meme temps que le module Unit A.
    """
    if BARRIERE_LEVEE:
        pytest.skip("Barriere levee explicitement (BARRIERE_LEVEE=True)")

    violations = []
    for rel_path, description in PROTECTED_MODULES.items():
        if (REPO / rel_path).exists():
            violations.append(f"{rel_path} ({description})")

    assert not violations, (
        f"BARRIERE §0 chantier #150 violée : module(s) Unit A/B/C/D créé(s) "
        f"avant levée explicite.\n"
        f"Violations : {violations}\n\n"
        f"Si la création est intentionnelle après G1-G5 verts + observation "
        f"post-Couche 0 parlée plusieurs semaines : éditer "
        f"BARRIERE_LEVEE=True dans tests/test_chantier_150_barrier_enforced.py "
        f"ET commit en même temps.\n"
        f"Sinon : ROLLBACK. Cf docs/CHANTIER_REDEVABILITY_LAYER.md §0."
    )


def test_barriere_levee_constant_is_boolean():
    """Garde meta : BARRIERE_LEVEE doit etre un bool, pas truthy/falsy."""
    assert isinstance(BARRIERE_LEVEE, bool), (
        f"BARRIERE_LEVEE doit etre exactement True ou False, got {type(BARRIERE_LEVEE).__name__}"
    )
