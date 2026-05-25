"""Tests for risk.sizing.position_size — Quarter Kelly formula.

These tests exist even though risk/ module is not yet wired into runtime
(see risk/sizing.py header). Ensures the math is correct when integration
happens post-observation.
"""

from risk.sizing import position_size


def test_zero_edge_returns_zero():
    """No edge -> no position."""
    assert position_size(0.0, 0.25, 10000) == 0.0


def test_negative_edge_returns_zero():
    """Negative edge -> no position."""
    assert position_size(-0.1, 0.25, 10000) == 0.0


def test_zero_variance_returns_zero():
    """Zero variance -> no position (degenerate)."""
    assert position_size(0.10, 0.0, 10000) == 0.0


def test_positive_edge_returns_positive_size():
    """Positive edge + variance -> positive position."""
    s = position_size(0.30, 0.25, 10000, 1.0)
    assert s > 0


def test_hard_cap_respected():
    """Even with huge edge, size capped at position_max_pct (lu depuis config, pas hardcode)."""
    from shared import config
    max_pct = config.load()["style"]["position_max_pct"]
    s = position_size(10.0, 0.01, 10000, 1.0)  # Massive Kelly
    assert s <= 10000 * max_pct + 1e-6, f"Sizing {s} viole le cap {max_pct:.0%}"


def test_regime_factor_scales_linearly():
    """Regime factor scales position proportionally (test below cap to verify scaling)."""
    # edge=0.05, var=0.50 -> raw_kelly=0.1 -> sized=250 (below 500 cap)
    base = position_size(0.05, 0.50, 10000, 1.0)
    half = position_size(0.05, 0.50, 10000, 0.5)
    assert base > 0 and base < 500, f"Base {base} should be below 500 cap"
    assert abs(half - base * 0.5) < 0.01, f"Regime scaling broken: {half} vs {base/2}"


def test_quarter_kelly_formula():
    """Verify quarter Kelly: size = capital * (edge/var) * 0.25 * regime, capped."""
    # edge=0.10, var=0.50 -> raw_kelly=0.2 -> sized = 10000 * 0.2 * 0.25 * 1.0 = 500
    # Cap = 10000 * 0.05 = 500 (right at cap)
    s = position_size(0.10, 0.50, 10000, 1.0)
    assert 499 < s <= 500, f"Expected ~500, got {s}"
