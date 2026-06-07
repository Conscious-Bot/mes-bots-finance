"""Tests M-B health metrics : M7 Druckenmiller + M10 Taleb barbell + M14 Jhunjhunwala.

Verrouille la logique deterministe des metriques observation continue
(distinct des creation gates -- ces metrics observent l'etat existant).
"""

from __future__ import annotations

from intelligence.thesis_health_metrics import (
    HealthMetric,
    compute_m7_invalidation_speed_days,
    compute_m10_barbell_score,
    compute_m14_conviction_age_days,
    run_health_metrics,
)

# --- Smoke tests : modules importent + structure attendue ----------------


def test_m7_returns_health_metric():
    """compute_m7 retourne HealthMetric, jamais raise sur DB vide."""
    r = compute_m7_invalidation_speed_days()
    assert isinstance(r, HealthMetric)
    assert r.metric_name == "M7_druckenmiller_cut_speed"
    assert r.status in ("healthy", "warn", "slow", "unknown")


def test_m10_returns_health_metric():
    r = compute_m10_barbell_score()
    assert isinstance(r, HealthMetric)
    assert r.metric_name == "M10_taleb_barbell"
    assert r.status in ("healthy", "warn", "mou", "unknown")


def test_m14_returns_list_of_metrics():
    """compute_m14 retourne list[HealthMetric] (1 par these active)."""
    results = compute_m14_conviction_age_days()
    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, HealthMetric)
        assert r.metric_name == "M14_jhunjhunwala_age"
        assert r.status in ("healthy", "warn", "stale", "unknown")


def test_m14_with_ticker_filter():
    """ticker arg filtre sur ce ticker uniquement."""
    results = compute_m14_conviction_age_days(ticker="ANY_TICKER")
    assert isinstance(results, list)
    # Soit liste de 1+ avec ticker correct, soit liste de 1 "unknown"
    assert len(results) >= 1


def test_run_health_metrics_aggregator():
    """run_health_metrics retourne dict avec les 3 metrics."""
    out = run_health_metrics()
    expected_keys = {
        "M7_druckenmiller_cut_speed",
        "M10_taleb_barbell",
        "M14_jhunjhunwala_age",
    }
    assert set(out.keys()) == expected_keys


def test_health_metric_dataclass_immutable():
    """HealthMetric frozen=True : impossible de muter apres creation."""
    import dataclasses
    m = HealthMetric("test", 5.0, "healthy", "msg")
    try:
        m.value = 99  # type: ignore[misc]
        raised = False
    except dataclasses.FrozenInstanceError:
        raised = True
    assert raised
