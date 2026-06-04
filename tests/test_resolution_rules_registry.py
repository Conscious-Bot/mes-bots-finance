"""Tests pour le registre RESOLUTION_RULES (lock criteria #110, advisor 04/06).

Garde :
- register_prediction refuse les methodology_version absent du registry
- resolve_due_predictions skip silencieusement (warn) sur unknown methodology_version
- bootstrap CI sur post_resolution_brier_report retourne des bornes saines

Cf docs/LESSONS.md L13 + docs/smoke_test_lock_in_2026-06-04.md.
"""

from __future__ import annotations

import pytest

from intelligence import learning
from scripts.post_resolution_brier_report import (
    _BASELINE_NO_SKILL,
    _bootstrap_brier_ci,
    _ci_verdict,
)

# ─── Registry coverage ───────────────────────────────────────────────────────


def test_resolution_rules_registry_complete() -> None:
    """Toutes les methodology_version actives en prod doivent etre listees."""
    expected = {"v0", "v1", "v2", "rule_v1_fallback", "rule_v1_shadow"}
    assert expected.issubset(set(learning.RESOLUTION_RULES.keys()))


def test_resolution_rules_have_required_fields() -> None:
    """Chaque entry doit avoir threshold + frozen_at + doc."""
    for mv, rule in learning.RESOLUTION_RULES.items():
        assert "threshold" in rule, f"{mv} missing threshold"
        assert "frozen_at" in rule, f"{mv} missing frozen_at"
        assert "doc" in rule, f"{mv} missing doc"
        assert isinstance(rule["threshold"], (int, float)), f"{mv} threshold not numeric"
        assert float(rule["threshold"]) > 0, f"{mv} threshold not positive"


def test_resolution_rule_for_known_returns_rule() -> None:
    rule = learning.resolution_rule_for("v2")
    assert rule is not None
    assert float(rule["threshold"]) == 0.05


def test_resolution_rule_for_unknown_returns_none() -> None:
    assert learning.resolution_rule_for("v99_unknown") is None
    assert learning.resolution_rule_for("") is None


# ─── register_prediction guard ────────────────────────────────────────────────


def test_register_prediction_refuses_unknown_methodology(caplog) -> None:
    """Lock #110 : methodology_version absent du registry -> return None + log error."""
    with caplog.at_level("ERROR"):
        result = learning.register_prediction(
            signal_id=1,
            ticker="NVDA",
            direction="bullish",
            methodology_version="v99_silent_addition",
        )
    assert result is None
    assert any("RESOLUTION_RULES" in r.message for r in caplog.records)


def test_register_prediction_refuses_empty_methodology(caplog) -> None:
    with caplog.at_level("ERROR"):
        result = learning.register_prediction(
            signal_id=1,
            ticker="NVDA",
            direction="bullish",
            methodology_version="",
        )
    assert result is None


# ─── Bootstrap CI ────────────────────────────────────────────────────────────


def test_bootstrap_ci_deterministic() -> None:
    """Seed fige -> resultats reproducibles."""
    scores = [0.1, 0.2, 0.3, 0.4, 0.5]
    a = _bootstrap_brier_ci(scores)
    b = _bootstrap_brier_ci(scores)
    assert a == b


def test_bootstrap_ci_n5_envelops_baseline() -> None:
    """A N=5 sur scores mid-range, CI doit englober baseline 0.25."""
    scores = [0.15, 0.25, 0.30, 0.20, 0.35]
    mean, lo, hi = _bootstrap_brier_ci(scores)
    assert lo <= _BASELINE_NO_SKILL <= hi
    assert "ENGLOBE" in _ci_verdict(mean, lo, hi, len(scores))


def test_bootstrap_ci_strong_signal_below_baseline() -> None:
    """Scores tres bas -> CI sous baseline -> verdict signal positif."""
    scores = [0.05, 0.08, 0.10, 0.06, 0.09, 0.07, 0.11, 0.05] * 5  # N=40 strong
    mean, lo, hi = _bootstrap_brier_ci(scores)
    assert hi < _BASELINE_NO_SKILL
    assert "EN DESSOUS" in _ci_verdict(mean, lo, hi, len(scores))


def test_bootstrap_ci_strong_negative_above_baseline() -> None:
    """Scores tres hauts -> CI au-dessus baseline -> verdict signal negatif."""
    scores = [0.40, 0.45, 0.50, 0.42, 0.48, 0.46, 0.41, 0.49] * 5  # N=40 weak
    mean, lo, hi = _bootstrap_brier_ci(scores)
    assert lo > _BASELINE_NO_SKILL
    assert "AU-DESSUS" in _ci_verdict(mean, lo, hi, len(scores))


def test_bootstrap_ci_empty_returns_zeros() -> None:
    mean, lo, hi = _bootstrap_brier_ci([])
    assert mean == lo == hi == 0.0


def test_bootstrap_ci_singleton() -> None:
    """N=1 : CI degenere a la valeur unique."""
    _mean, lo, hi = _bootstrap_brier_ci([0.3])
    assert lo == hi == 0.3


@pytest.mark.parametrize(
    "scores,expect_envelope",
    [
        ([0.20] * 5, False),  # constant below baseline
        ([0.30] * 5, False),  # constant above baseline
        ([0.10, 0.40] * 3, True),  # noisy around baseline
    ],
)
def test_bootstrap_ci_envelope_logic(
    scores: list[float], expect_envelope: bool
) -> None:
    _mean, lo, hi = _bootstrap_brier_ci(scores)
    enveloped = lo <= _BASELINE_NO_SKILL <= hi
    assert enveloped == expect_envelope
