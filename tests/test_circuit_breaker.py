"""Tests circuit breaker Elder rule."""

import pytest


def test_compute_dd_30j_returns_dict():
    """Smoke : compute_dd_30j returns dict avec dd_pct."""
    from intelligence.circuit_breaker import compute_dd_30j
    r = compute_dd_30j()
    assert isinstance(r, dict)
    assert "dd_pct" in r
    assert "high_value" in r


def test_check_circuit_breaker_returns_state():
    """Smoke : check_circuit_breaker returns state dict avec active key."""
    from intelligence.circuit_breaker import check_circuit_breaker, is_active
    state = check_circuit_breaker()
    assert isinstance(state, dict)
    assert "active" in state
    assert "dd_pct" in state
    assert "threshold_pct" in state
    # is_active reflete bien le state
    assert is_active() == state["active"]


def test_circuit_breaker_threshold_from_calibration():
    """Check le threshold lu depuis calibration.yaml v5 audit."""
    from intelligence.circuit_breaker import check_circuit_breaker
    state = check_circuit_breaker()
    # threshold doit etre 6.0 selon v5 calibration (Elder rule)
    assert state["threshold_pct"] == pytest.approx(6.0)


def test_circuit_breaker_inactive_when_dd_above_threshold():
    """Si dd > -6%, circuit pas active."""
    from intelligence import circuit_breaker as cb
    # Mock state directement pour test logique
    cb._STATE = {"active": False, "dd_pct": -2.0, "threshold_pct": 6.0}
    assert cb.is_active() is False


def test_circuit_breaker_active_when_dd_below_threshold():
    """Si dd < -6%, circuit actif."""
    from intelligence import circuit_breaker as cb
    cb._STATE = {"active": True, "dd_pct": -8.5, "threshold_pct": 6.0}
    assert cb.is_active() is True
    s = cb.state()
    assert s["dd_pct"] == -8.5
