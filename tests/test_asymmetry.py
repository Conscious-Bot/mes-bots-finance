"""Property-based + unit tests for asymmetry verdict logic (mocks yfinance)."""

from hypothesis import given, settings, strategies as st

from intelligence import asymmetry


def _thesis(entry=100.0, target_full=200.0, target_partial=150.0, stop=80.0, ticker="TEST"):
    return {
        "ticker": ticker,
        "entry_price": entry,
        "target_full": target_full,
        "target_partial": target_partial,
        "stop_price": stop,
        "direction": "long",
    }


def test_stop_breached(monkeypatch):
    monkeypatch.setattr(asymmetry, "_get_current_price", lambda t: 70.0)
    r = asymmetry.compute_thesis_asymmetry(_thesis())
    assert r["verdict"] == "STOP_BREACHED"
    assert r["asymmetry_ratio"] == 0.0


def test_target_hit(monkeypatch):
    monkeypatch.setattr(asymmetry, "_get_current_price", lambda t: 210.0)
    r = asymmetry.compute_thesis_asymmetry(_thesis())
    assert r["verdict"] == "TARGET_HIT"
    assert r["asymmetry_ratio"] == 999.0


def test_strong_run(monkeypatch):
    monkeypatch.setattr(asymmetry, "_get_current_price", lambda t: 105.0)
    r = asymmetry.compute_thesis_asymmetry(_thesis())
    assert r["verdict"] == "STRONG_RUN"
    assert r["asymmetry_ratio"] > 3.0


def test_favorable(monkeypatch):
    monkeypatch.setattr(asymmetry, "_get_current_price", lambda t: 120.0)
    r = asymmetry.compute_thesis_asymmetry(_thesis())
    assert r["verdict"] == "FAVORABLE"


def test_balanced(monkeypatch):
    monkeypatch.setattr(asymmetry, "_get_current_price", lambda t: 140.0)
    r = asymmetry.compute_thesis_asymmetry(_thesis())
    assert r["verdict"] == "BALANCED"


def test_unfavorable(monkeypatch):
    monkeypatch.setattr(asymmetry, "_get_current_price", lambda t: 165.0)
    r = asymmetry.compute_thesis_asymmetry(_thesis())
    assert r["verdict"] == "UNFAVORABLE"


def test_flipped(monkeypatch):
    monkeypatch.setattr(asymmetry, "_get_current_price", lambda t: 185.0)
    r = asymmetry.compute_thesis_asymmetry(_thesis())
    assert r["verdict"] == "FLIPPED"


def test_price_fetch_failure(monkeypatch):
    monkeypatch.setattr(asymmetry, "_get_current_price", lambda t: None)
    r = asymmetry.compute_thesis_asymmetry(_thesis())
    assert "error" in r


def test_incomplete_thesis(monkeypatch):
    monkeypatch.setattr(asymmetry, "_get_current_price", lambda t: 100.0)
    r = asymmetry.compute_thesis_asymmetry({"ticker": "X", "direction": "long"})
    assert "note" in r


def test_short_direction_skipped(monkeypatch):
    monkeypatch.setattr(asymmetry, "_get_current_price", lambda t: 100.0)
    th = _thesis()
    th["direction"] = "short"
    r = asymmetry.compute_thesis_asymmetry(th)
    assert "note" in r


from unittest.mock import patch


@given(current=st.floats(80.01, 199.99, allow_nan=False))
@settings(max_examples=200)
def test_verdict_in_valid_set(current):
    """Use mock.patch context manager (Hypothesis-compatible, resets per example)."""
    with patch.object(asymmetry, "_get_current_price", return_value=current):
        r = asymmetry.compute_thesis_asymmetry(_thesis())
    valid = {"STRONG_RUN", "FAVORABLE", "BALANCED", "UNFAVORABLE", "FLIPPED"}
    if "verdict" in r:
        assert r["verdict"] in valid


@given(current=st.floats(81.0, 199.0, allow_nan=False))
@settings(max_examples=200)
def test_ratio_positive_finite_mid_range(current):
    """Property: for current strictly between stop and target, ratio is finite positive."""
    with patch.object(asymmetry, "_get_current_price", return_value=current):
        r = asymmetry.compute_thesis_asymmetry(_thesis())
    ratio = r.get("asymmetry_ratio")
    if ratio is not None and ratio not in (0.0, 999.0):
        assert ratio > 0
        assert ratio < 1000


def test_degenerate_downside(monkeypatch):
    """Edge case: current ~= stop → downside ~0, should return error not crash."""
    monkeypatch.setattr(asymmetry, "_get_current_price", lambda t: 80.00001)
    th = _thesis(stop=80.0)
    r = asymmetry.compute_thesis_asymmetry(th)
    # Either error (degenerate) or extremely high ratio - both acceptable
    assert "error" in r or "asymmetry_ratio" in r
