"""Tests for compute_kpi6 — portfolio vs SPY/QQQ/SMH benchmarks (EUR).

Uses monkeypatch to mock compute_portfolio_return_eur + fetch_benchmark_return_eur
since these depend on yfinance + live DB. Tests status logic across all 4 quadrants
(GREEN/YELLOW/RED/INSUFFICIENT) + benchmark fetch failure handling.
"""

import pytest

from shared import portfolio_metrics as pm


def _mock_pf(days: int, pct: float, priced: int = 5, total: int = 5) -> dict:
    return {
        "days": days,
        "return_pct": pct,
        "positions_priced": priced,
        "positions_total": total,
    }


def test_compute_kpi6_no_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm, "compute_portfolio_return_usd", lambda: None)
    r = pm.compute_kpi6()
    assert "no open positions" in r["current"]
    assert "🔍" in r["status"]
    assert "SPY/QQQ/SMH" in r["title"]


def test_compute_kpi6_benchmark_fetch_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm, "compute_portfolio_return_usd", lambda: _mock_pf(400, 10.0))
    monkeypatch.setattr(pm, "fetch_benchmark_return_usd", lambda tk, days: None)
    r = pm.compute_kpi6()
    assert "INSUFFICIENT_BENCHMARK" in r["status"]


def test_compute_kpi6_green_all_above(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm, "compute_portfolio_return_usd", lambda: _mock_pf(400, 15.0))
    monkeypatch.setattr(pm, "fetch_benchmark_return_usd", lambda tk, days: 10.0)
    r = pm.compute_kpi6()
    assert "✅" in r["status"]
    assert "all 3" in r["status"]
    for tk in ("SPY", "QQQ", "SMH"):
        assert f"{tk}-usd" in r["current"]


def test_compute_kpi6_yellow_one_breach_smh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm, "compute_portfolio_return_usd", lambda: _mock_pf(400, 5.0))
    returns = {"SPY": 5.0, "QQQ": 5.0, "SMH": 11.0}
    monkeypatch.setattr(pm, "fetch_benchmark_return_usd", lambda tk, days: returns[tk])
    r = pm.compute_kpi6()
    assert "⚠️" in r["status"]
    assert "SMH" in r["status"]


def test_compute_kpi6_red_majority_breach(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm, "compute_portfolio_return_usd", lambda: _mock_pf(400, 0.0))
    monkeypatch.setattr(pm, "fetch_benchmark_return_usd", lambda tk, days: 10.0)
    r = pm.compute_kpi6()
    assert "🚨" in r["status"]
    assert "3/3" in r["status"]


def test_compute_kpi6_insufficient_days(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm, "compute_portfolio_return_usd", lambda: _mock_pf(100, 5.0))
    monkeypatch.setattr(pm, "fetch_benchmark_return_usd", lambda tk, days: 5.0)
    r = pm.compute_kpi6()
    assert "INSUFFICIENT" in r["status"]
    assert "100d" in r["status"]


def test_compute_kpi6_benchmarks_constant() -> None:
    """Lock the benchmark set — change requires test update + commit message rationale."""
    assert pm._BENCHMARKS == ("SPY", "QQQ", "SMH")
