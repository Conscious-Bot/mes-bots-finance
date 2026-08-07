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


def test_position_card_delegue_a_v3(position_card_source: str) -> None:
    """V3 (07/08/2026) : _position_card est un wrapper — le rendu vit dans
    dashboard/position_card.py. L'asymétrie n'est plus affichée sur la carte
    (P2/P6 : exclue par la doctrine), donc plus de wiring asym à prouver ICI ;
    la pureté de la V3 est verrouillée par le test suivant."""
    assert "from dashboard.position_card import render_position_card" in position_card_source


def test_position_card_v3_est_pure() -> None:
    """La carte LIT (CardInputs + SteerOutput), ne recalcule JAMAIS (P7, L1/L4).

    Plus fort que l'ancien test d'import : ZÉRO accès données dans le module —
    ni storage, ni sqlite3, ni position_view, ni book_performance. La seule
    exception tolérée : ticker_names (cosmétique, sous try)."""
    src = (Path(__file__).resolve().parent.parent / "dashboard" / "position_card.py"
           ).read_text(encoding="utf-8")
    for forbidden in ("import sqlite3", "from shared import storage",
                      "from shared.storage", "shared.position_view",
                      "book_performance", "yfinance"):
        assert forbidden not in src, (
            f"V3 impure : « {forbidden} » — la carte est une fonction de "
            "(inputs, steer), toute donnée se calcule en amont"
        )


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
