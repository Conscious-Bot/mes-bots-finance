"""Tests M-B Pydantic gates : M1 Buffett quality + M2 Taleb asymmetry.

Verrouille la logique deterministe des gates de creation thèse :
- M1 fire seulement si conviction >= 4 ET solidité tagged Incertain/Fragile
- M2 fire seulement si conviction >= 4 ET asymmetry_ratio < 2.0 calculable
- Watch direction -> M2 ne fire pas
- Conviction faible (<4) -> aucun gate ne fire

Si ces tests regressent, on a perdu la doctrine mentor heuristique
(L14 anti-pattern #1 : pas de persona LLM, gates determinist a la place).
"""

from __future__ import annotations

import pytest

from intelligence.thesis_creation_gates import (
    check_m1_buffett_quality,
    check_m2_taleb_asymmetry,
    run_creation_gates,
)

# --- M1 Buffett quality ----------------------------------------------------


@pytest.mark.parametrize("solidite", ["Incontournable", "Solide"])
def test_m1_high_conviction_acceptable_solidite_passes(solidite):
    """conviction 4-5 + solidité Incontournable/Solide -> pass."""
    for conv in (4, 5):
        r = check_m1_buffett_quality("NVDA", conv, solidite)
        assert r.passed, f"conv={conv} sol={solidite} doit passer : {r.message}"
        assert r.gate_name == "M1_buffett_quality"


@pytest.mark.parametrize("solidite", ["Incertain", "Fragile"])
def test_m1_high_conviction_bad_solidite_fails(solidite):
    """conviction >= 4 + solidité Incertain/Fragile -> FAIL."""
    for conv in (4, 5):
        r = check_m1_buffett_quality("TSLA", conv, solidite)
        assert not r.passed, f"conv={conv} sol={solidite} doit fail"
        assert "M1 Buffett FAIL" in r.message


def test_m1_low_conviction_never_fires():
    """conviction 1-3 : gate ne fire pas, quel que soit solidité."""
    for conv in (1, 2, 3):
        for sol in ("Incontournable", "Solide", "Incertain", "Fragile", None):
            r = check_m1_buffett_quality("ANY", conv, sol)
            assert r.passed, f"conv={conv} sol={sol} doit passer (gate not fired)"


def test_m1_no_solidite_warns_not_blocks():
    """Ticker hors canonical (solidité=None) -> pass avec warning, pas block."""
    r = check_m1_buffett_quality("UNKNOWN", 5, None)
    assert r.passed
    assert "warning" in r.message.lower()


# --- M2 Taleb asymmetry ---------------------------------------------------


def test_m2_long_acceptable_ratio_passes():
    """Long, conv 4, upside=15 / downside=5 -> ratio=3 >= 2 -> pass."""
    r = check_m2_taleb_asymmetry(
        ticker="NVDA", conviction=4, direction="long",
        entry=100.0, target_full=115.0, stop_price=95.0,
    )
    assert r.passed
    assert "3.00" in r.message or "asymmetry_ratio=3" in r.message


def test_m2_long_low_ratio_fails():
    """Long, conv 4, upside=8 / downside=5 -> ratio=1.6 < 2 -> FAIL."""
    r = check_m2_taleb_asymmetry(
        ticker="TSLA", conviction=4, direction="long",
        entry=100.0, target_full=108.0, stop_price=95.0,
    )
    assert not r.passed
    assert "M2 Taleb FAIL" in r.message
    assert "1.60" in r.message


def test_m2_short_acceptable_ratio_passes():
    """Short, conv 4, upside=20 / downside=10 -> ratio=2 -> pass."""
    r = check_m2_taleb_asymmetry(
        ticker="ZM", conviction=4, direction="short",
        entry=100.0, target_full=80.0, stop_price=110.0,
    )
    assert r.passed
    assert "2.00" in r.message


def test_m2_short_low_ratio_fails():
    """Short, conv 5, upside=5 / downside=10 -> ratio=0.5 -> FAIL."""
    r = check_m2_taleb_asymmetry(
        ticker="ANY", conviction=5, direction="short",
        entry=100.0, target_full=95.0, stop_price=110.0,
    )
    assert not r.passed
    assert "M2 Taleb FAIL" in r.message


def test_m2_watch_direction_does_not_fire():
    """direction=watch -> ne fire pas (pas de target/stop normalement)."""
    r = check_m2_taleb_asymmetry(
        ticker="ANY", conviction=5, direction="watch",
        entry=None, target_full=None, stop_price=None,
    )
    assert r.passed
    assert "watch" in r.message.lower()


def test_m2_low_conviction_does_not_fire():
    """conviction 1-3 : pas applicable."""
    for conv in (1, 2, 3):
        r = check_m2_taleb_asymmetry(
            ticker="ANY", conviction=conv, direction="long",
            entry=100.0, target_full=101.0, stop_price=95.0,  # ratio=0.2 mais skip
        )
        assert r.passed


def test_m2_missing_stop_warns_not_blocks():
    """stop_price=None : gate ne peut pas calculer -> warning, pas block."""
    r = check_m2_taleb_asymmetry(
        ticker="ANY", conviction=4, direction="long",
        entry=100.0, target_full=120.0, stop_price=None,
    )
    assert r.passed
    assert "non calculable" in r.message


def test_m2_invalid_geometry_warns_not_blocks():
    """Long avec stop > entry (geometrie cassée) -> warning, pas block."""
    r = check_m2_taleb_asymmetry(
        ticker="ANY", conviction=4, direction="long",
        entry=100.0, target_full=120.0, stop_price=105.0,  # stop > entry pour long
    )
    assert r.passed  # downside <= 0 -> ratio None -> warn


# --- Aggregator ------------------------------------------------------------


def test_run_creation_gates_returns_both():
    """run_creation_gates lance les 2 gates et retourne les 2 results."""
    results = run_creation_gates(
        ticker="NVDA", direction="long", conviction=4,
        solidite="Solide",
        entry=100.0, target_full=120.0, stop_price=95.0,
    )
    assert len(results) == 2
    names = {r.gate_name for r in results}
    assert names == {"M1_buffett_quality", "M2_taleb_asymmetry"}
    assert all(r.passed for r in results)


def test_run_creation_gates_low_conviction_all_pass():
    """conviction 2 : tout passe trivialement."""
    results = run_creation_gates(
        ticker="ANY", direction="long", conviction=2,
        solidite="Fragile",
        entry=100.0, target_full=101.0, stop_price=95.0,  # ratio=0.2, would fail M2 si conv>=4
    )
    assert all(r.passed for r in results)


def test_run_creation_gates_high_conviction_mixed_fail():
    """conviction 5 + Fragile + low ratio -> deux gates fail simultanement."""
    results = run_creation_gates(
        ticker="ANY", direction="long", conviction=5,
        solidite="Fragile",
        entry=100.0, target_full=105.0, stop_price=90.0,  # ratio=0.5
    )
    failed = [r for r in results if not r.passed]
    assert len(failed) == 2
    assert {r.gate_name for r in failed} == {"M1_buffett_quality", "M2_taleb_asymmetry"}
