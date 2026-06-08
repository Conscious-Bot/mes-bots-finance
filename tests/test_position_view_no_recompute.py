"""Grep gate verrouillant : aucun calcul de ratio/asym hors compute_position.

Discipline Olivier #113 : "Le test qui le verrouille : grep que le chemin de
rendu ligne/card n'a aucun calcul de ratio/value hors compute_position".

Si ce test est rouge, le 0,5x vs 1,80x peut revenir par la porte de derriere
(une autre derivation locale recree une source divergente).

Phase actuelle (tranche fine) : verrouille uniquement _position_card.
Phase suivante (#114) : etendra a _broker_one (book row).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_RENDER_PY = Path(__file__).parent.parent / "dashboard" / "render.py"


@pytest.fixture(scope="module")
def render_source() -> str:
    return _RENDER_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def position_card_source(render_source: str) -> str:
    """Extrait le bloc _position_card (entre 'def _position_card' et le def suivant)."""
    m = re.search(r"^def _position_card\b.*?(?=^def \w)", render_source, re.MULTILINE | re.DOTALL)
    assert m is not None, "_position_card introuvable"
    return m.group(0)


def test_position_card_does_not_recompute_ratio_from_entry(position_card_source: str) -> None:
    """LE TEST QUI TUE LE BUG : aucun "ratio = (full - entry) / (entry - stop)"
    dans _position_card (ou variante). compute_position est la source unique.
    """
    # Patterns interdits : assignment direct du ratio depuis formule literal
    forbidden_patterns = [
        r"ratio\s*=\s*\(\s*full\s*-\s*entry\s*\)",
        r"ratio\s*=\s*\(\s*entry\s*-\s*full\s*\)",
        r"ratio\s*=\s*\(\s*target",  # ratio = (target...
    ]
    for pat in forbidden_patterns:
        matches = re.findall(pat, position_card_source)
        # Filtre les occurrences dans les commentaires/docstrings (ligne debut #)
        actual_violations = [
            m for m in matches
            if not any(
                line.lstrip().startswith("#") or '"""' in line
                for line in position_card_source.splitlines()
                if pat[:15].replace("\\", "") in line
            )
        ]
        assert not actual_violations or all(
            "Test verrouillant" in line or "grep" in line.lower()
            for line in position_card_source.splitlines()
            if any(m in line for m in matches)
        ), f"Pattern interdit trouve dans _position_card : {pat} -- compute_position est la source unique"


def test_position_card_uses_view_asym_ratio(position_card_source: str) -> None:
    """_position_card DOIT consommer view.asym_ratio (preuve positive du wiring)."""
    assert (
        "_view.asym_ratio" in position_card_source
        or "view.asym_ratio" in position_card_source
    ), "_position_card ne consomme PAS view.asym_ratio -- le wiring SPEC Phase 3 n'est pas applique"


def test_position_card_imports_compute_position(position_card_source: str) -> None:
    """_position_card DOIT importer compute_position depuis shared.position_view."""
    assert (
        "from shared.position_view import compute_position" in position_card_source
        or "shared.position_view" in position_card_source
    ), "_position_card n'importe PAS shared.position_view -- le wiring n'est pas applique"


def test_no_local_up_pct_dn_pct_calc_in_card(position_card_source: str) -> None:
    """Aucun up_pct = (full / entry - 1) * 100 dans _position_card.

    view.upside_pct / view.downside_pct sont la source unique.
    """
    forbidden = [
        r"up_pct\s*=\s*\(\s*full\s*/\s*entry",
        r"dn_pct\s*=\s*\(\s*stop\s*/\s*entry",
    ]
    for pat in forbidden:
        m = re.search(pat, position_card_source)
        assert m is None, f"Recompute locale interdite : {pat} -- consomme view.upside_pct / view.downside_pct"


# === #114 etendu : grep gate sur _theses (panneau theses) ================


@pytest.fixture(scope="module")
def theses_panel_source(render_source: str) -> str:
    """Extrait le bloc _theses entre 'def _theses' et le def suivant."""
    m = re.search(r"^def _theses\b.*?(?=^def \w)", render_source, re.MULTILINE | re.DOTALL)
    assert m is not None, "_theses introuvable"
    return m.group(0)


def test_theses_panel_does_not_recompute_perf_locally(theses_panel_source: str) -> None:
    """LE TEST QUI TUE le bug "panneau theses recompute pnl_e localement".

    Aucun "(current - entry) / entry * 100" dans _theses -- la primitive
    canonique compute_perf_thesis_pct est la source unique.
    """
    # Pattern interdit : assignment direct depuis formule literal
    forbidden_patterns = [
        r"pnl_e\s*=\s*\(\s*current\s*-\s*entry\s*\)\s*/\s*entry",
        r"=\s*\(\s*current\s*-\s*entry\s*\)\s*/\s*entry\s*\*\s*100",
    ]
    for pat in forbidden_patterns:
        m = re.search(pat, theses_panel_source)
        assert m is None, (
            f"Calc local interdit dans _theses : {pat} -- "
            "consomme compute_perf_thesis_pct(entry, current) depuis shared.position_view"
        )


def test_theses_panel_uses_compute_perf_thesis_pct(theses_panel_source: str) -> None:
    """_theses DOIT consommer compute_perf_thesis_pct (preuve positive du wiring)."""
    assert "compute_perf_thesis_pct" in theses_panel_source, (
        "_theses ne consomme PAS compute_perf_thesis_pct -- "
        "le wiring #114 (primitive canonique perf these) n'est pas applique"
    )
