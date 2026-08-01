"""Conformité doctrinale du renderer — tests de SOURCE (aucune exécution requise).

Pourquoi lire le source plutôt que le HTML rendu : ces invariants doivent tenir
même quand aucun dashboard n'a été généré, sans base de données, et sur toute
version de Python. Le rendu, lui, se vérifie séparément à l'exécution.

Verrouille les corrections du 01/08/2026 (audit interface) :
  A8  — aucune grandeur dérivée affichée en scalaire nu (elle nomme sa base)
  A3  — aucun seuil de politique codé en dur dans le renderer
  L15 — une valeur de politique absente devient « — », jamais un défaut fabriqué
  L31 — un composite calculé sur une couverture partielle le DÉCLARE

Ces tests sont des tests de NON-RÉGRESSION : ils échouent si quelqu'un
réintroduit un des quatre défauts, y compris par copier-coller.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RENDER = Path(__file__).resolve().parent.parent / "dashboard" / "render.py"


@pytest.fixture(scope="module")
def src() -> str:
    if not RENDER.is_file():
        pytest.skip("dashboard/render.py absent")
    return RENDER.read_text(encoding="utf-8", errors="replace")


# ── A8 : pas de scalaire de confiance nu ─────────────────────────────────────

def test_a8_pas_de_confiance_scalaire_nue(src: str):
    """`(conf {conf})` affichait un nombre isolé, qui se lit comme une MESURE.

    Un scalaire de confiance doit nommer sa base (éval LLM, calculé, …) ou
    montrer ses primitives (nombre de preuves).
    """
    interdits = [
        r"\(conf \{conf\}",          # forme exacte du défaut corrigé
        r"conf \{conf\}\{ev_str\}",
    ]
    for pat in interdits:
        assert not re.search(pat, src), (
            f"A8 violé : scalaire de confiance nu réintroduit ({pat}). "
            "Afficher la base et les primitives (n preuves), pas un nombre isolé."
        )


def test_a8_la_base_est_nommee(src: str):
    """Toute grandeur affichée déclare sa nature : LLM affirmé vs calculé."""
    assert "éval LLM" in src, "A8 : la nature de l'évaluation (LLM) n'est plus affichée"
    assert "(calc)" in src and "(LLM)" in src, (
        "A8 : materialité (calculée) et confiance (LLM) doivent nommer leur base"
    )


# ── A3 + L15 : aucun seuil de politique en dur, aucun défaut fabriqué ────────

def test_a3_pas_de_seuil_politique_en_dur(src: str):
    """Le renderer REND la politique, il ne la définit pas.

    `us.get("target_cluster_cap_pct", 35)` inventait un seuil absent des
    politiques et l'affichait comme un fait.
    """
    fabriques = re.findall(
        r'\.get\(\s*["\'](target_\w*(?:cap|decorrelation)\w*)["\']\s*,\s*([0-9]+(?:\.[0-9]+)?)\s*\)',
        src,
    )
    assert not fabriques, (
        f"A3/L15 violé : défaut numérique fabriqué pour un seuil de politique {fabriques}. "
        "Une valeur absente doit devenir « — » (état honnête), pas un nombre inventé."
    )


def test_l15_valeur_absente_devient_tiret(src: str):
    """La politique manquante s'affiche en état honnête, pas en valeur plausible."""
    assert re.search(r"_cap_raw\s+if\s+_cap_raw\s+is\s+not\s+None\s+else\s+\"—\"", src), (
        "L15 : le repli « — » sur target_cluster_cap_pct a disparu"
    )


# ── L31 : un agrégat partiel se déclare ─────────────────────────────────────

def test_l31_couverture_declaree_sur_les_composites(src: str):
    """Une dimension exclue (data_insufficient) rend le /100 INCOMPLET.

    L31 : un agrégat à couverture incomplète est un faux, pas une approximation.
    Le composite doit donc afficher sa couverture quand elle est partielle.
    """
    assert "def _coverage_tag(" in src, "L31 : la déclaration de couverture a disparu"
    appels = len(re.findall(r"_coverage_tag\(\s*\w+_dims_used", src))
    assert appels >= 2, (
        f"L31 : la couverture n'est déclarée que sur {appels} composite(s) — "
        "Construction ET Fragility doivent la déclarer"
    )
    assert "partiel {used}/{total} dim." in src, (
        "L31 : le libellé de couverture partielle a changé de forme — "
        "vérifier qu'il reste explicite pour le lecteur"
    )


def test_l31_couverture_silencieuse_si_complete(src: str):
    """Couverture pleine → aucun bruit visuel (sinon l'utilisateur s'habitue)."""
    m = re.search(r"def _coverage_tag.*?return \"\"", src, re.S)
    assert m, "L31 : _coverage_tag doit retourner une chaîne vide quand la couverture est pleine"
