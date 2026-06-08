"""Levier #4 : tests target_edge_pct sizing asymetrie-first.

Spec user 07/06 : "downside-to-target -30%, upside +40%, tu es a 11.6% du book
= 3.5% NAV au downside, au-dessus de ton budget-ruine par nom. Logique de
sizing hedge-fund-grade, honnete sur l'edge."

target_edge_pct = ruin_budget / |downside_pct|
- Downside large -> target_edge plus restrictif que cap conviction
- Downside etroit -> target_edge plus large (cap conv prime in fine)
- Structural (stop=None) -> target_edge=None
"""

from __future__ import annotations

import pytest

from shared.sizing_caps import target_edge_pct

# ─── Test 1 : long position downside calculation ─────────────────────────


def test_long_position_downside_20pct() -> None:
    """entry 100, stop 80, current 100 -> downside 20% -> target_edge=ruin/20."""
    out = target_edge_pct(entry=100.0, stop=80.0, current=100.0, ruin_budget_pct=1.5)
    # downside = (100-80)/100 = 20% -> target_edge = 1.5 / 20 * 100 = 7.5%
    assert out == pytest.approx(7.5, abs=0.01)


def test_long_position_downside_10pct() -> None:
    out = target_edge_pct(entry=100.0, stop=90.0, current=100.0, ruin_budget_pct=1.5)
    # downside 10% -> target_edge 15%
    assert out == pytest.approx(15.0, abs=0.01)


def test_long_position_downside_40pct_tight_target_edge() -> None:
    """Downside large -> target_edge plus restrictif (asymetrie defavorable)."""
    out = target_edge_pct(entry=100.0, stop=60.0, current=100.0, ruin_budget_pct=1.5)
    # downside 40% -> target_edge 3.75% (< typique cap conv 6%) -> binding edge
    assert out == pytest.approx(3.75, abs=0.01)


# ─── Test 2 : current > entry (position en plus-value) ────────────────────


def test_long_position_in_gain_uses_current_for_downside() -> None:
    """entry 100, stop 80, current 120 -> downside = (120-80)/120 = 33.33%."""
    out = target_edge_pct(entry=100.0, stop=80.0, current=120.0, ruin_budget_pct=1.5)
    # downside 33.33% -> target_edge 4.5%
    assert out == pytest.approx(4.5, abs=0.05)


# ─── Test 3 : stop None (structural) -> None ─────────────────────────────


def test_no_stop_returns_none() -> None:
    """Structural type (stop=None) -> target_edge n/a."""
    out = target_edge_pct(entry=100.0, stop=None, current=100.0, ruin_budget_pct=1.5)
    assert out is None


def test_missing_entry_returns_none() -> None:
    out = target_edge_pct(entry=None, stop=80.0, current=100.0, ruin_budget_pct=1.5)
    assert out is None


def test_missing_current_returns_none() -> None:
    out = target_edge_pct(entry=100.0, stop=80.0, current=None, ruin_budget_pct=1.5)
    assert out is None


# ─── Test 4 : stop-breached (current <= stop) ───────────────────────────


def test_current_at_stop_returns_none() -> None:
    """current = stop -> downside = 0 -> degenere."""
    out = target_edge_pct(entry=100.0, stop=80.0, current=80.0, ruin_budget_pct=1.5)
    assert out is None


def test_current_below_stop_returns_none() -> None:
    """current < stop -> downside < 0 -> degenere."""
    out = target_edge_pct(entry=100.0, stop=80.0, current=70.0, ruin_budget_pct=1.5)
    assert out is None


# ─── Test 5 : short direction ───────────────────────────────────────────


def test_short_position_inverted_calculation() -> None:
    """Short : downside = (stop - current) / current."""
    out = target_edge_pct(
        entry=100.0, stop=120.0, current=100.0,
        ruin_budget_pct=1.5, direction="short",
    )
    # downside short = (120-100)/100 = 20% -> target_edge 7.5%
    assert out == pytest.approx(7.5, abs=0.01)


# ─── Test 6 : sensibilite au ruin_budget ─────────────────────────────────


def test_target_edge_proportional_to_ruin_budget() -> None:
    """Doubler ruin_budget -> doubler target_edge."""
    out_1 = target_edge_pct(100.0, 80.0, 100.0, ruin_budget_pct=1.0)
    out_2 = target_edge_pct(100.0, 80.0, 100.0, ruin_budget_pct=2.0)
    assert out_2 == pytest.approx(out_1 * 2, abs=0.01)
