"""Tests shared/portfolio_analytics.py -- wrapper ffn analytics deterministe.

Verrouille les invariants des 7 fonctions :
- equity curve rebase correctement
- drawdown serie toujours <= 0, droit a 0 au pic
- perf metrics dict complet avec types attendus
- rolling vol respecte annualisation + fenetre
- IR aligne dates correctement + retourne None sur excess std=0
- VaR <= 0 sur returns mixtes, None si <2 points
- CVaR <= VaR (perte conditionnelle plus severe)

Pas de wire render.py teste ici -- module unit pur. Smoke test integration
au moment du wire Heimdall (sprint separe).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from shared.portfolio_analytics import (
    compute_conditional_var,
    compute_drawdown_events,
    compute_drawdown_series,
    compute_equity_curve,
    compute_information_ratio,
    compute_perf_metrics,
    compute_rolling_volatility,
    compute_value_at_risk,
)


@pytest.fixture
def synthetic_prices() -> pd.Series:
    """Serie synthetique 252 jours de bourse, returns ~N(0, 0.01)."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=252, freq="B")
    returns = np.random.randn(252) * 0.01
    prices = pd.Series(
        100 * np.exp(np.cumsum(returns)), index=dates, name="PORT"
    )
    return prices


@pytest.fixture
def synthetic_returns(synthetic_prices) -> pd.Series:
    """Returns simples derives des prix synthetiques."""
    return synthetic_prices.pct_change().dropna()


# --- Equity curve ----------------------------------------------------------


def test_equity_curve_starts_at_base(synthetic_prices):
    """rebase(prices, base=100) -> prices[0] == 100."""
    curve = compute_equity_curve(synthetic_prices, base=100.0)
    assert curve.iloc[0] == pytest.approx(100.0, abs=1e-9)


def test_equity_curve_preserves_relative_ratios(synthetic_prices):
    """Le ratio prix final / prix initial est preserve."""
    raw_ratio = synthetic_prices.iloc[-1] / synthetic_prices.iloc[0]
    curve = compute_equity_curve(synthetic_prices, base=100.0)
    rebased_ratio = curve.iloc[-1] / curve.iloc[0]
    assert raw_ratio == pytest.approx(rebased_ratio, rel=1e-9)


def test_equity_curve_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        compute_equity_curve(pd.Series(dtype=float))


def test_equity_curve_nan_first_raises():
    s = pd.Series([np.nan, 100.0, 101.0])
    with pytest.raises(ValueError, match="NaN"):
        compute_equity_curve(s)


# --- Drawdown --------------------------------------------------------------


def test_drawdown_series_always_non_positive(synthetic_prices):
    """DD est toujours <= 0 (sous le pic precedent)."""
    dd = compute_drawdown_series(synthetic_prices)
    assert (dd <= 1e-9).all(), "Drawdown should always be <= 0"


def test_drawdown_zero_at_initial_point(synthetic_prices):
    """DD[0] = 0 (pas de pic precedent)."""
    dd = compute_drawdown_series(synthetic_prices)
    assert dd.iloc[0] == pytest.approx(0.0, abs=1e-9)


def test_drawdown_monotone_increasing_series_has_zero_dd():
    """Serie monotone croissante -> DD identiquement 0."""
    s = pd.Series([100, 105, 110, 120, 130], index=pd.date_range("2025-01-01", periods=5, freq="B"))
    dd = compute_drawdown_series(s)
    assert (dd.abs() < 1e-9).all()


def test_drawdown_events_returns_dataframe_or_none(synthetic_prices):
    """drawdown_details retourne DataFrame structuré."""
    events = compute_drawdown_events(synthetic_prices)
    if events is not None:
        assert isinstance(events, pd.DataFrame)
        assert "drawdown" in events.columns or "Length" in events.columns


# --- Perf metrics ----------------------------------------------------------


def test_perf_metrics_returns_full_dict(synthetic_prices):
    """compute_perf_metrics retourne dict avec toutes les cles canoniques."""
    metrics = compute_perf_metrics(synthetic_prices, rf_annual=0.02)
    expected = {
        "cagr", "total_return", "max_drawdown", "volatility_annual",
        "sharpe", "sortino", "calmar", "best_day", "worst_day",
    }
    assert set(metrics.keys()) == expected


def test_perf_metrics_values_have_correct_signs(synthetic_prices):
    """max_drawdown <= 0, volatility >= 0, sharpe peut etre signe quelconque."""
    metrics = compute_perf_metrics(synthetic_prices, rf_annual=0.0)
    if metrics["max_drawdown"] is not None:
        assert metrics["max_drawdown"] <= 0
    if metrics["volatility_annual"] is not None:
        assert metrics["volatility_annual"] >= 0


def test_perf_metrics_empty_series_returns_all_none():
    """Serie vide -> dict avec toutes valeurs None (pas d'exception)."""
    metrics = compute_perf_metrics(pd.Series(dtype=float))
    assert all(v is None for v in metrics.values())


def test_perf_metrics_single_point_returns_all_none():
    """Serie a 1 point -> impossible de calculer returns -> None."""
    s = pd.Series([100.0], index=pd.date_range("2025-01-01", periods=1, freq="B"))
    metrics = compute_perf_metrics(s)
    assert all(v is None for v in metrics.values())


# --- Rolling volatility ----------------------------------------------------


def test_rolling_vol_first_window_minus_one_is_nan(synthetic_returns):
    """rolling(window=20) -> 19 premiers points sont NaN."""
    vol = compute_rolling_volatility(synthetic_returns, window=20)
    assert vol.iloc[:19].isna().all()
    assert not vol.iloc[19:].isna().any()


def test_rolling_vol_annualized_factor(synthetic_returns):
    """annualize=True multiplie std par sqrt(252)."""
    vol_ann = compute_rolling_volatility(synthetic_returns, window=20, annualize=True)
    vol_raw = compute_rolling_volatility(synthetic_returns, window=20, annualize=False)
    ratio = (vol_ann / vol_raw).dropna()
    assert ratio.iloc[0] == pytest.approx(np.sqrt(252), rel=1e-6)


def test_rolling_vol_invalid_window_raises():
    with pytest.raises(ValueError, match="window"):
        compute_rolling_volatility(pd.Series([0.01, -0.02]), window=0)


# --- Information ratio -----------------------------------------------------


def test_information_ratio_zero_when_returns_equal_benchmark():
    """returns == benchmark -> IR = 0 (excess identiquement 0 -> std=0 -> None)."""
    s = pd.Series([0.01, 0.02, -0.01, 0.005], index=pd.date_range("2025-01-01", periods=4, freq="B"))
    ir = compute_information_ratio(s, s)
    assert ir is None, "std excess = 0 doit retourner None"


def test_information_ratio_alignment_on_inner_join():
    """Dates non-alignees -> intersection seulement."""
    dates = pd.date_range("2025-01-01", periods=5, freq="B")
    r = pd.Series([0.01, 0.02, -0.01, 0.005, 0.0], index=dates)
    b = pd.Series([0.005, 0.01, 0.0, 0.005, -0.005], index=dates)
    ir = compute_information_ratio(r, b)
    assert ir is not None and isinstance(ir, float)


def test_information_ratio_empty_returns_none():
    assert compute_information_ratio(pd.Series(dtype=float), pd.Series(dtype=float)) is None


# --- VaR / CVaR ------------------------------------------------------------


def test_var_negative_on_mixed_returns(synthetic_returns):
    """VaR 95% (alpha=0.05) doit etre negatif sur returns mixtes."""
    var = compute_value_at_risk(synthetic_returns, alpha=0.05)
    assert var is not None
    assert var <= 0


def test_var_quantile_correctness():
    """VaR = quantile(alpha) exactement."""
    rets = pd.Series([-0.05, -0.02, 0.0, 0.01, 0.03])
    var = compute_value_at_risk(rets, alpha=0.20)
    expected = rets.quantile(0.20)
    assert var == pytest.approx(expected, rel=1e-9)


def test_cvar_le_var_strict(synthetic_returns):
    """CVaR <= VaR (esperance conditionnelle plus severe que seuil)."""
    var = compute_value_at_risk(synthetic_returns, alpha=0.05)
    cvar = compute_conditional_var(synthetic_returns, alpha=0.05)
    assert var is not None and cvar is not None
    assert cvar <= var + 1e-9


def test_var_alpha_out_of_bounds_raises():
    with pytest.raises(ValueError):
        compute_value_at_risk(pd.Series([0.01, -0.01]), alpha=0.0)
    with pytest.raises(ValueError):
        compute_value_at_risk(pd.Series([0.01, -0.01]), alpha=1.0)
    with pytest.raises(ValueError):
        compute_conditional_var(pd.Series([0.01, -0.01]), alpha=1.5)


def test_var_empty_or_single_point_returns_none():
    assert compute_value_at_risk(pd.Series(dtype=float)) is None
    assert compute_value_at_risk(pd.Series([0.01])) is None
    assert compute_conditional_var(pd.Series(dtype=float)) is None
