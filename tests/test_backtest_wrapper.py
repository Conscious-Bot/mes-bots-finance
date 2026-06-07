"""Tests shared/backtest.py wrapper bt 1.2.0.

Smoke verrouille :
- import bt, lazy ensure_bt
- WalkForwardWindow dataclass
- build_walk_forward_windows logique deterministe
- aggregate_walk_forward stats par metric

PAS de network test ici (yfinance batch live = flaky). Le yfinance loader
est teste manuellement smoke + production usage.
"""

from __future__ import annotations

from datetime import date

import pytest

from shared.backtest import (
    BacktestResult,
    WalkForwardWindow,
    _ensure_bt,
    aggregate_walk_forward,
    build_walk_forward_windows,
)


def test_ensure_bt_returns_module():
    bt = _ensure_bt()
    assert hasattr(bt, "Strategy")
    assert hasattr(bt, "Backtest")
    assert hasattr(bt, "run")


def test_walk_forward_window_label():
    w = WalkForwardWindow(
        train_start=date(2020, 1, 1), train_end=date(2021, 12, 31),
        test_start=date(2022, 1, 1), test_end=date(2022, 6, 30),
    )
    assert w.label() == "WF_2022_01"


def test_build_walk_forward_5_splits():
    windows = build_walk_forward_windows(
        overall_start=date(2020, 1, 1),
        overall_end=date(2026, 1, 1),
        n_splits=5,
        train_years=2,
    )
    assert len(windows) == 5
    # Chaque fenetre : train avant test
    for w in windows:
        assert w.train_end < w.test_start
        assert w.train_start < w.train_end
    # Pas de chevauchement test entre fenetres consecutives
    for i in range(1, len(windows)):
        assert windows[i].test_start >= windows[i - 1].test_end


def test_build_walk_forward_periode_trop_courte_raise():
    """Period < 2y train + 90j = ValueError explicit."""
    with pytest.raises(ValueError, match="trop courte"):
        build_walk_forward_windows(
            overall_start=date(2025, 1, 1),
            overall_end=date(2025, 6, 30),  # < 2y + 90j
            n_splits=5,
            train_years=2,
        )


def test_aggregate_walk_forward_empty():
    """0 results -> {}."""
    assert aggregate_walk_forward([]) == {}


def test_aggregate_walk_forward_with_results():
    """Aggregate sur quelques results : mean/std/min/max/n."""
    results = [
        BacktestResult(
            window_label="WF1", strategy_name="test",
            sharpe=1.5, sortino=2.0, max_drawdown=-0.10,
            total_return=0.20, cagr=0.18, n_days=120,
        ),
        BacktestResult(
            window_label="WF2", strategy_name="test",
            sharpe=0.8, sortino=1.2, max_drawdown=-0.15,
            total_return=0.10, cagr=0.10, n_days=120,
        ),
        BacktestResult(
            window_label="WF3", strategy_name="test",
            sharpe=None,  # missing -> skip
            sortino=1.5, max_drawdown=-0.12,
            total_return=0.15, cagr=0.13, n_days=120,
        ),
    ]
    agg = aggregate_walk_forward(results)
    assert agg["sharpe"]["n"] == 2  # WF3 sharpe None skip
    assert agg["sharpe"]["mean"] == pytest.approx(1.15, abs=0.01)
    assert agg["sortino"]["n"] == 3
    assert agg["max_drawdown"]["min"] == -0.15
    assert agg["cagr"]["max"] == 0.18


def test_aggregate_all_none_metric_returns_n_zero():
    results = [
        BacktestResult(
            window_label="WF1", strategy_name="test",
            sharpe=None, sortino=None, max_drawdown=None,
            total_return=None, cagr=None, n_days=120,
        ),
    ]
    agg = aggregate_walk_forward(results)
    assert agg["sharpe"]["n"] == 0
    assert "mean" not in agg["sharpe"]


def test_run_walk_forward_basic_smoke():
    """Smoke test : strategy equi-weight sur prix synthetiques sur 2 fenetres."""
    import bt
    import numpy as np
    import pandas as pd

    from shared.backtest import run_walk_forward

    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=400, freq="B")
    prices = pd.DataFrame({
        "A": 100 * np.exp(np.cumsum(np.random.randn(400) * 0.01)),
        "B": 100 * np.exp(np.cumsum(np.random.randn(400) * 0.012)),
    }, index=dates)

    def factory(label: str):
        return bt.Strategy(f"eq_weight_{label}", [
            bt.algos.RunMonthly(),
            bt.algos.SelectAll(),
            bt.algos.WeighEqually(),
            bt.algos.Rebalance(),
        ])

    windows = [
        WalkForwardWindow(
            train_start=date(2023, 1, 1), train_end=date(2024, 6, 30),
            test_start=date(2024, 7, 1), test_end=date(2025, 1, 1),
        ),
        WalkForwardWindow(
            train_start=date(2023, 6, 1), train_end=date(2024, 12, 31),
            test_start=date(2025, 1, 1), test_end=date(2025, 6, 30),
        ),
    ]
    results = run_walk_forward(factory, prices, windows)
    # Au moins 1 fenetre devrait reussir
    assert len(results) >= 1
    for r in results:
        assert r.strategy_name.startswith("eq_weight_")
        assert r.n_days > 0
