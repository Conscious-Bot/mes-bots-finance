"""#78 -- Tests cluster_threshold_sweep mecanique."""
from __future__ import annotations

import pytest

from intelligence.cluster_threshold_sweep import (
    default_threshold_grid,
    find_optimal_threshold,
    sweep_thresholds,
)


def _make_cluster(n: int, m: float, return_30d: float | None = None,
                  return_90d: float | None = None) -> dict:
    return {
        "distinct_buyers": n, "total_buy_m": m,
        "return_30d": return_30d, "return_90d": return_90d,
    }


def test_empty_clusters_insufficient(tmp_path):
    sweep = sweep_thresholds([], [{"min_n": 3, "min_m": 1.0}])
    assert sweep[0]["status"] == "INSUFFICIENT_DATA"
    assert sweep[0]["n_resolved"] == 0


def test_threshold_filters_below():
    """min_n=4 doit filtrer les clusters n=3."""
    clusters = [_make_cluster(n=3, m=2.0, return_30d=0.05)]
    sweep = sweep_thresholds(clusters, [{"min_n": 4, "min_m": 1.0}])
    assert sweep[0]["n_total_above"] == 0


def test_threshold_passes_above():
    clusters = [_make_cluster(n=5, m=3.0, return_30d=0.05)]
    sweep = sweep_thresholds(clusters, [{"min_n": 3, "min_m": 1.0}])
    assert sweep[0]["n_total_above"] == 1


def test_positive_returns_ok_status():
    """5 clusters, returns positifs autour 5% -> OK."""
    clusters = [_make_cluster(n=5, m=3.0, return_30d=r)
                for r in [0.03, 0.05, 0.07, 0.04, 0.06]]
    sweep = sweep_thresholds(clusters, [{"min_n": 3, "min_m": 1.0}])
    r = sweep[0]
    assert r["n_resolved"] == 5
    assert r["mean_return"] == pytest.approx(0.05, abs=0.001)
    assert r["positive_rate"] == 1.0
    assert r["status"] == "OK"


def test_negative_mean_alert():
    """5 clusters returns negatifs -> ALERT."""
    clusters = [_make_cluster(n=5, m=3.0, return_30d=-0.05) for _ in range(5)]
    sweep = sweep_thresholds(clusters, [{"min_n": 3, "min_m": 1.0}])
    assert sweep[0]["status"] == "ALERT"


def test_horizon_90d():
    """horizon='90d' utilise return_90d."""
    clusters = [_make_cluster(n=5, m=3.0, return_30d=0.05, return_90d=0.15)
                for _ in range(5)]
    sweep = sweep_thresholds(clusters, [{"min_n": 3, "min_m": 1.0}], horizon="90d")
    assert sweep[0]["mean_return"] == pytest.approx(0.15, abs=0.001)


def test_horizon_invalid_raises():
    with pytest.raises(ValueError):
        sweep_thresholds([], [{"min_n": 3}], horizon="bogus")


def test_find_optimal_picks_max_sharpe():
    """3 seuils, le 2nd a meilleur sharpe -> selected."""
    sweep_results = [
        {"threshold": {"min_n": 3}, "n_resolved": 10, "sharpe": 0.5,
         "mean_return": 0.05, "positive_rate": 0.6, "status": "OK"},
        {"threshold": {"min_n": 5}, "n_resolved": 12, "sharpe": 1.2,
         "mean_return": 0.08, "positive_rate": 0.7, "status": "OK"},
        {"threshold": {"min_n": 4}, "n_resolved": 11, "sharpe": 0.8,
         "mean_return": 0.06, "positive_rate": 0.65, "status": "OK"},
    ]
    best = find_optimal_threshold(sweep_results, min_n_signals=10, criterion="sharpe")
    assert best is not None
    assert best["threshold"]["min_n"] == 5
    assert best["sharpe"] == 1.2


def test_find_optimal_skips_below_min_n():
    """min_n_signals=10 -> seuil avec n_resolved=8 ignore."""
    sweep_results = [
        {"threshold": {"min_n": 3}, "n_resolved": 8, "sharpe": 1.5,
         "mean_return": 0.10, "positive_rate": 0.8, "status": "OK"},
        {"threshold": {"min_n": 5}, "n_resolved": 12, "sharpe": 0.8,
         "mean_return": 0.05, "positive_rate": 0.6, "status": "OK"},
    ]
    best = find_optimal_threshold(sweep_results, min_n_signals=10, criterion="sharpe")
    assert best["threshold"]["min_n"] == 5  # le 1er exclu (n<10)


def test_find_optimal_skips_alert_status():
    """ALERT status filtre."""
    sweep_results = [
        {"threshold": {"min_n": 3}, "n_resolved": 15, "sharpe": 1.5,
         "mean_return": -0.10, "positive_rate": 0.2, "status": "ALERT"},
        {"threshold": {"min_n": 5}, "n_resolved": 12, "sharpe": 0.5,
         "mean_return": 0.05, "positive_rate": 0.55, "status": "OK"},
    ]
    best = find_optimal_threshold(sweep_results, min_n_signals=10, criterion="sharpe")
    assert best["threshold"]["min_n"] == 5


def test_find_optimal_no_candidates_returns_none():
    sweep_results = [
        {"threshold": {"min_n": 3}, "n_resolved": 3, "sharpe": 1.0,
         "mean_return": 0.05, "positive_rate": 0.6, "status": "OK"},
    ]
    assert find_optimal_threshold(sweep_results, min_n_signals=10) is None


def test_default_grid_realistic():
    """Grille canonique : 25 combinaisons (5 N x 5 M)."""
    grid = default_threshold_grid()
    assert len(grid) == 25
    assert {"min_n": 3, "min_m": 1.0} in grid  # actuel
    assert {"min_n": 5, "min_m": 5.0} in grid  # "strong" rule


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
