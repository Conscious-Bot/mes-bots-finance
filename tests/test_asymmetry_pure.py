"""Pure-function tests pour intelligence.asymmetry (chemins critiques #36).

Tests sans DB : monkeypatch `_get_current_price` pour controler le prix
courant. Couvre les 8 chemins de `compute_thesis_asymmetry` :
1. Empty/None thesis
2. Missing ticker
3. Missing entry/target/stop
4. direction != "long"
5. Price fetch failed
6. STOP_BREACHED (current <= stop)
7. TARGET_HIT (current >= target_full)
8. Degenerate downside ~0
9-13. 5 verdicts : STRONG_RUN, FAVORABLE, BALANCED, UNFAVORABLE, FLIPPED

Couverture cible : >85% sur asymmetry.py (vs ~41% pre-test).
"""
from __future__ import annotations

import pytest

from intelligence import asymmetry as asym_mod


@pytest.fixture
def patch_price(monkeypatch):
    """Helper : set current price retournee par _get_current_price."""
    def _set(price: float | None):
        monkeypatch.setattr(asym_mod, "_get_current_price", lambda tk: price)
    return _set


# ─── Chemins de sortie precoce ────────────────────────────────────────────


def test_none_thesis_returns_none():
    assert asym_mod.compute_thesis_asymmetry(None) is None


def test_empty_dict_returns_none():
    assert asym_mod.compute_thesis_asymmetry({}) is None


def test_missing_ticker_returns_none():
    assert asym_mod.compute_thesis_asymmetry({"entry_price": 100}) is None


def test_price_fetch_failed(patch_price):
    patch_price(None)
    r = asym_mod.compute_thesis_asymmetry({"ticker": "X"})
    assert r == {"ticker": "X", "error": "price fetch failed"}


def test_short_direction_noted(patch_price):
    patch_price(50.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "direction": "short",
        "entry_price": 100, "target_full": 50, "stop_price": 110,
    })
    assert r["note"].startswith("asymmetry not computed for direction=short")
    assert r["current_price"] == 50.0


def test_missing_entry_returns_incomplete(patch_price):
    patch_price(100.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "target_full": 150, "stop_price": 80,
    })
    assert "entry" in r["note"]


def test_missing_target_and_stop_returns_combined_missing(patch_price):
    patch_price(100.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 90,
    })
    assert "target_full" in r["note"] and "stop" in r["note"]


# ─── Edge cases breach + target hit ───────────────────────────────────────


def test_stop_breached_when_current_at_stop(patch_price):
    patch_price(80.0)  # = stop
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 100,
        "target_full": 150, "stop_price": 80,
    })
    assert r["verdict"] == "STOP_BREACHED"
    assert r["asymmetry_ratio"] == 0.0
    assert r["downside_pct"] == 0.0


def test_stop_breached_when_current_below_stop(patch_price):
    patch_price(70.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 100,
        "target_full": 150, "stop_price": 80,
    })
    assert r["verdict"] == "STOP_BREACHED"
    assert r["upside_pct"] == pytest.approx((150 - 70) / 70 * 100)


def test_target_hit_when_current_at_target(patch_price):
    patch_price(150.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 100,
        "target_full": 150, "stop_price": 80,
    })
    assert r["verdict"] == "TARGET_HIT"
    assert r["asymmetry_ratio"] == 999.0  # sentinel canonique (cf LESSONS L12)
    assert r["upside_pct"] == 0.0


def test_target_hit_when_current_above_target(patch_price):
    patch_price(180.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 100,
        "target_full": 150, "stop_price": 80,
    })
    assert r["verdict"] == "TARGET_HIT"
    assert r["asymmetry_ratio"] == 999.0


def test_degenerate_downside_near_zero(patch_price):
    """Si current ~= stop (juste au-dessus), downside_pct quasi nul ->
    rapport explose. Le code retourne {"error": "degenerate..."}."""
    patch_price(80.0001)  # juste au-dessus de stop=80, downside_pct ~ 0.0001%
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 100,
        "target_full": 150, "stop_price": 80,
    })
    assert "degenerate" in r["error"]


# ─── 5 verdicts du cas nominal ────────────────────────────────────────────


def test_verdict_strong_run(patch_price):
    """ratio > 3 -> STRONG_RUN. Current=85, target=150, stop=80.
    upside = (150-85)/85*100 = 76.5% ; downside = (85-80)/85*100 = 5.9%
    ratio = 13 → STRONG_RUN."""
    patch_price(85.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 100,
        "target_full": 150, "stop_price": 80,
    })
    assert r["verdict"] == "STRONG_RUN"
    assert r["asymmetry_ratio"] > 3.0


def test_verdict_favorable(patch_price):
    """1.5 < ratio <= 3 -> FAVORABLE. Current=100, target=130, stop=80.
    upside 30% ; downside 20% ; ratio 1.5. Boundary +0.01 -> FAVORABLE."""
    patch_price(100.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 100,
        "target_full": 131, "stop_price": 80,
    })
    assert r["verdict"] == "FAVORABLE"


def test_verdict_balanced(patch_price):
    """0.7 < ratio <= 1.5 -> BALANCED."""
    patch_price(100.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 100,
        "target_full": 120, "stop_price": 80,
    })
    # upside 20, downside 20, ratio 1.0 -> BALANCED
    assert r["verdict"] == "BALANCED"


def test_verdict_unfavorable(patch_price):
    """0.3 < ratio <= 0.7 -> UNFAVORABLE."""
    patch_price(100.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 100,
        "target_full": 110, "stop_price": 80,
    })
    # upside 10, downside 20, ratio 0.5 -> UNFAVORABLE
    assert r["verdict"] == "UNFAVORABLE"


def test_verdict_flipped(patch_price):
    """ratio <= 0.3 -> FLIPPED. upside < 6% pour downside 20%."""
    patch_price(100.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 100,
        "target_full": 105, "stop_price": 80,
    })
    # upside 5, downside 20, ratio 0.25 -> FLIPPED
    assert r["verdict"] == "FLIPPED"


# ─── Fields preserved + format ────────────────────────────────────────────


def test_result_includes_all_expected_fields(patch_price):
    patch_price(120.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "ABC", "entry_price": 100,
        "target_full": 150, "target_partial": 130, "stop_price": 80,
    })
    for f in ("ticker", "current_price", "entry", "target_full",
              "target_partial", "stop", "asymmetry_ratio", "verdict",
              "upside_pct", "downside_pct"):
        assert f in r, f"field {f!r} missing"
    assert r["target_partial"] == 130


def test_target_price_alias_to_target_full(patch_price):
    """thesis avec `target_price` (legacy name) fallback sur `target_full`."""
    patch_price(120.0)
    r = asym_mod.compute_thesis_asymmetry({
        "ticker": "X", "entry_price": 100,
        "target_price": 150, "stop_price": 80,
    })
    assert r["target_full"] == 150  # fallback applique
