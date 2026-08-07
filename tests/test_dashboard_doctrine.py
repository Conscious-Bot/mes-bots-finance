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
    """Toute grandeur affichée déclare sa nature : LLM affirmé vs calculé.

    07/08/2026 : les labels (calc)/(LLM) vivaient dans la card legacy, morte
    avec la V3. Le porteur A8 de la carte est désormais la provenance de
    l'anti-thèse (copilot/LLM vs thèse écrite) dans dashboard/position_card.py.
    """
    assert "éval LLM" in src, "A8 : la nature de l'évaluation (LLM) n'est plus affichée"
    card_src = (RENDER.parent / "position_card.py").read_text(encoding="utf-8")
    assert "copilot, LLM" in card_src and '"thèse"' in card_src, (
        "A8 : l'anti-thèse de la carte doit nommer sa base (copilot/LLM vs thèse)"
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


# ── PQ-007 : bande OBLIGATIONS — invariant de rareté ────────────────────────

def test_obligations_band_existe_et_est_cablee(src: str):
    """Le registre produit des obligations bloquantes ; l'interface doit les montrer.

    Doctrine invisible = doctrine non appliquée (H11).
    """
    assert "def _obligations_band(" in src, "PQ-007 : la bande d'obligations a disparu"
    assert re.search(r"\{_oband\}\{_dband\}", src), (
        "PQ-007 : la bande doit être câblée EN TÊTE de <main>, avant la bande discipline"
    )


def test_obligations_band_invariant_de_rarete(src: str):
    """Registre serein → chaîne VIDE. Une bande toujours pleine devient invisible
    (fatigue d'alarme) : la rareté est un critère de CONCEPTION, pas d'affichage."""
    body = re.search(r"def _obligations_band\(.*?\n(?=\n\ndef )", src, re.S)
    assert body, "corps de _obligations_band introuvable"
    assert re.search(r"if not obs and not failed and not imminent:\s*\n\s*return \"\"",
                     body.group(0)), (
        "PQ-007 : la bande doit rendre une chaîne VIDE quand rien n'est dû — "
        "sinon elle devient du bruit quotidien et cesse d'être lue"
    )


def test_obligations_band_fail_loud(src: str):
    """Registre illisible → bandeau INCIDENT visible, JAMAIS un silence.

    Un silence ne doit jamais pouvoir se lire comme « calme » (L15 + never-fail-silent).
    """
    body = re.search(r"def _obligations_band\(.*?\n(?=\n\ndef )", src, re.S)
    assert body, "corps de _obligations_band introuvable"
    b = body.group(0)
    assert "REGISTRE INJOIGNABLE" in b and "REGISTRE EN ÉCHEC" in b, (
        "PQ-007 : les deux chemins d'échec (exception, erreur moteur) doivent être "
        "visibles à l'écran, pas avalés"
    )
    assert b.count("return \"\"") == 1, (
        "PQ-007 : un seul chemin peut rendre du vide — celui du registre serein"
    )


def test_obligations_band_source_unique(src: str):
    """La bande LIT le moteur, elle ne réimplémente pas le filtre (L1)."""
    body = re.search(r"def _obligations_band\(.*?\n(?=\n\ndef )", src, re.S)
    assert body and "blocking_obligations()" in body.group(0), (
        "PQ-007 : la bande doit appeler assumption_graph.blocking_obligations() — "
        "toute réimplémentation du filtre créerait une seconde vérité"
    )


# ── Fin dashboard 04/08 : 3 pages retirées, organes vitaux migrés ───────────

def test_les_trois_pages_ne_sont_plus_emises(src: str):
    """User 03/08 : « pas besoin d'afficher — tout doit continuer à exister ».

    Le body assembly n'émet plus strategie/methode/cerebro. Les FONCTIONS
    restent (code vivant non affiché) — seul l'appel disparaît."""
    body = re.search(r"    body = \(\n(?:.*\n)*?    \)\n", src)
    assert body, "body assembly introuvable"
    b = body.group(0)
    for dead in ("strategie_html", "_signaux()", "_vault()"):
        assert dead not in b, f"{dead} encore émis — la page devait disparaître du DOM"
    for alive in ("def _vault(", "def _signaux(", "def _user_strategy_panel("):
        assert alive in src, f"{alive} supprimée — l'instruction était de GARDER les fonctions"


def test_organes_vitaux_migres_pas_perdus(src: str):
    """Les monitors (déclencheurs) vivent dans Alerts ; track record + data
    health (organes de preuve, axe 5 QUALITY_BAR) vivent sur Overview.
    Sans cette migration, retirer les pages aurait retiré la substance."""
    assert "def _monitors_live_panel(" in src, "le panneau monitors extrait a disparu"
    urg = re.search(r"def _urgence\(.*?\n(?=\ndef )", src, re.S)
    assert urg and "_monitors_live_panel()" in urg.group(0), (
        "les monitors doivent être émis par Alerts (_urgence)"
    )
    vig = re.search(r"    vigie = \(\n(?:.*\n)*?    \)\n", src)
    assert vig, "bloc vigie introuvable"
    v = vig.group(0)
    assert "_track_record_panel()" in v and "_data_health_panel()" in v, (
        "track record et data health doivent être émis par Overview (vigie)"
    )


def test_aucun_lien_vers_page_morte(src: str):
    """Un presageNav vers une page sans data-page = clic mort silencieux."""
    for dead in ("presageNav(&#39;strategie&#39;)", "presageNav(&#39;cerebro&#39;)",
                 "presageNav(&#39;methode&#39;)"):
        assert dead not in src, f"lien mort : {dead}"
