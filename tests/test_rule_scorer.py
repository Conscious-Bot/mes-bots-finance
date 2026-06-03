"""#94 Phase 2 -- RuleScorer (plancher determinist).

Tests math + control-flow. Property-based sur le math (clamp + determinisme
+ monotonicite), unit tests sur le control-flow (watch path + enforcement
mirrors V2 + methodology_version guard).

Spec user 03/06 :
  "Property-based : reserve aux math (rule scorer #94 C1, Brier segmente #95)."

Garanties testees :
1. methodology_version restreint a {'rule_v1_fallback', 'rule_v1_shadow'}
   (ADR 014 § Substance tier : autres tags polluent canonical/substance).
2. Determinisme : meme input -> meme output (pas de randomness, pas de I/O
   non-mocke). Reproductible bit-pour-bit.
3. Clamp : probability toujours dans [0.55, 0.85] pour non-watch.
4. Watch path : evidence none/weak -> watch (mirror V2 enforcement).
5. Watch path : sentiment None/watch -> watch.
6. base_rate fallback : si fetcher None -> prior 0.55.
7. Monotonicite faible : higher signal_score, meme tout-autre-egal,
   ne diminue jamais la proba pour une direction donnee.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import given, strategies as st

from intelligence.scorers import RuleScorer, ScorerInput

# ─── Helpers ──────────────────────────────────────────────────────────────


def _mk_input(
    sentiment: str = "bullish",
    signal_score: int | None = 8,
    signal_type: str | None = "earnings_beat",
    impact_magnitude: float | None = 0.5,
    horizon_days: int = 28,
    ticker: str = "NVDA",
) -> ScorerInput:
    return ScorerInput(
        title="t",
        ticker=ticker,
        horizon_days=horizon_days,
        signal_score=signal_score,
        signal_type=signal_type,
        impact_magnitude=impact_magnitude,
        sentiment=sentiment,
    )


# ─── 1. methodology_version guard ────────────────────────────────────────


def test_rule_scorer_methodology_version_default():
    s = RuleScorer()
    assert s.methodology_version == "rule_v1_fallback"


def test_rule_scorer_methodology_version_shadow_allowed():
    s = RuleScorer(methodology_version="rule_v1_shadow")
    assert s.methodology_version == "rule_v1_shadow"


def test_rule_scorer_rejects_invalid_methodology_version():
    """ADR 014 hazard A : tags non-rule polluent canonical/substance filters."""
    with pytest.raises(ValueError, match="rule_v1_fallback"):
        RuleScorer(methodology_version="v2")
    with pytest.raises(ValueError, match="rule_v1_fallback"):
        RuleScorer(methodology_version="rule_v2_shadow")
    with pytest.raises(ValueError):
        RuleScorer(methodology_version="")


# ─── 2. Determinisme strict ──────────────────────────────────────────────


def test_determinism_same_input_same_output():
    """Meme input + meme base_rate -> meme output (bit-pour-bit)."""
    fetcher = MagicMock(return_value={"rate": 0.60, "n": 20})
    s = RuleScorer(base_rate_fetcher=fetcher)
    inp = _mk_input()
    out1 = s.score(inp)
    out2 = s.score(inp)
    assert out1 == out2


def test_no_io_side_effects_when_base_rate_fetcher_mocked():
    """Aucun appel reseau / fichier / DB en dehors du fetcher mocke."""
    fetcher = MagicMock(return_value={"rate": 0.55, "n": 15})
    s = RuleScorer(base_rate_fetcher=fetcher)
    out = s.score(_mk_input())
    assert out is not None
    fetcher.assert_called_once()  # Le seul appel exterieur autorise.


# ─── 3. Clamp invariant (property-based) ─────────────────────────────────


@st.composite
def _strong_input_strategy(draw: Any) -> ScorerInput:
    """Generer un input qui passe les enforcement (non-watch path)."""
    return ScorerInput(
        title="t",
        ticker=draw(st.sampled_from(["NVDA", "MSFT", "AAPL"])),
        horizon_days=draw(st.integers(min_value=1, max_value=180)),
        signal_score=draw(st.integers(min_value=7, max_value=10)),  # moderate+
        signal_type=draw(st.sampled_from(["earnings_beat", "guidance_up", "insider_buy"])),
        impact_magnitude=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
        sentiment=draw(st.sampled_from(["bullish", "bearish"])),
    )


@given(inp=_strong_input_strategy(), base_rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
def test_probability_always_in_clamp_range_for_non_watch(inp: ScorerInput, base_rate: float):
    """Proba TOUJOURS dans [0.55, 0.85] quand direction != watch."""
    fetcher = MagicMock(return_value={"rate": base_rate, "n": 20})
    s = RuleScorer(base_rate_fetcher=fetcher)
    out = s.score(inp)
    assert out is not None
    if out["direction"] != "watch":
        assert 0.55 <= out["probability"] <= 0.85, (
            f"prob {out['probability']} out of [0.55, 0.85] for base_rate={base_rate} "
            f"score={inp.signal_score} impact={inp.impact_magnitude}"
        )


# ─── 4. Watch path (mirror V2 enforcement) ───────────────────────────────


def test_evidence_none_returns_watch():
    """signal_score < 6 (ou None) -> evidence='none' -> watch."""
    s = RuleScorer(base_rate_fetcher=lambda *_args, **_kw: None)
    out = s.score(_mk_input(signal_score=5))
    assert out is not None
    assert out["direction"] == "watch"
    assert out["evidence_strength"] == "none"


def test_evidence_weak_returns_watch():
    """signal_score == 6 -> evidence='weak' -> watch (non-falsifiable)."""
    s = RuleScorer(base_rate_fetcher=lambda *_args, **_kw: None)
    out = s.score(_mk_input(signal_score=6))
    assert out is not None
    assert out["direction"] == "watch"
    assert out["evidence_strength"] == "weak"


def test_sentiment_watch_returns_watch():
    """Pas de direction prefixee -> impossible de scorer -> watch."""
    s = RuleScorer(base_rate_fetcher=lambda *_args, **_kw: None)
    out = s.score(_mk_input(sentiment="watch"))
    assert out is not None
    assert out["direction"] == "watch"


def test_sentiment_none_returns_watch():
    """sentiment None -> watch."""
    s = RuleScorer(base_rate_fetcher=lambda *_args, **_kw: None)
    out = s.score(_mk_input(sentiment=None))  # type: ignore[arg-type]
    assert out is not None
    assert out["direction"] == "watch"


def test_watch_dict_is_complete_schema():
    """Watch dict doit avoir TOUS les champs du schema (audit trail). Jamais None."""
    s = RuleScorer(base_rate_fetcher=lambda *_args, **_kw: None)
    out = s.score(_mk_input(signal_score=4))
    expected_keys = {
        "version", "ticker", "horizon_days", "base_rate", "evidence_strength",
        "evidence_summary", "anti_anchoring_reason", "probability", "direction",
        "reasoning",
    }
    assert set(out.keys()) == expected_keys


# ─── 5. base_rate fallback ───────────────────────────────────────────────


def test_base_rate_fallback_to_prior_when_fetcher_returns_none():
    """Bucket vide -> prior 0.55 (pas de base rate sourced)."""
    s = RuleScorer(base_rate_fetcher=lambda *_args, **_kw: None)
    out = s.score(_mk_input(signal_score=8, impact_magnitude=0.0))
    assert out is not None
    assert out["base_rate"] == 0.55  # le prior


def test_base_rate_fetched_when_signal_type_provided():
    """Fetcher est appele avec (signal_type, direction, horizon_days)."""
    fetcher = MagicMock(return_value={"rate": 0.62, "n": 25})
    s = RuleScorer(base_rate_fetcher=fetcher)
    inp = _mk_input(
        sentiment="bearish",
        signal_type="guidance_down",
        horizon_days=30,
    )
    s.score(inp)
    fetcher.assert_called_once_with("guidance_down", "bearish", 30)


def test_base_rate_not_fetched_for_watch_path():
    """Si sentiment='watch', pas la peine de fetch base_rate (court-circuit)."""
    fetcher = MagicMock()
    s = RuleScorer(base_rate_fetcher=fetcher)
    s.score(_mk_input(sentiment="watch"))
    fetcher.assert_not_called()


# ─── 6. Monotonicite : higher score never decreases probability ─────────


@given(
    score_a=st.integers(min_value=7, max_value=10),
    score_b=st.integers(min_value=7, max_value=10),
)
def test_monotonicity_higher_score_not_lower_probability(score_a: int, score_b: int):
    """Tout-autre-egal, signal_score plus eleve -> probability >= ou == egal.

    Note : clamp peut saturer, donc on n'a pas la stricte monotonicite,
    juste la faible (>=) non-decroissance.
    """
    fetcher = lambda *_args, **_kw: {"rate": 0.55, "n": 20}  # noqa: E731
    s = RuleScorer(base_rate_fetcher=fetcher)
    inp_a = _mk_input(signal_score=score_a, impact_magnitude=0.3)
    inp_b = _mk_input(signal_score=score_b, impact_magnitude=0.3)
    p_a = s.score(inp_a)["probability"]
    p_b = s.score(inp_b)["probability"]
    if score_a < score_b:
        assert p_a <= p_b
    elif score_a > score_b:
        assert p_a >= p_b
    else:
        assert p_a == p_b  # determinisme


@given(impact=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
def test_impact_magnitude_monotonicity(impact: float):
    """impact_magnitude plus eleve -> probability >= ou == egal."""
    fetcher = lambda *_args, **_kw: {"rate": 0.55, "n": 20}  # noqa: E731
    s = RuleScorer(base_rate_fetcher=fetcher)
    inp_low = _mk_input(signal_score=9, impact_magnitude=0.0)
    inp_high = _mk_input(signal_score=9, impact_magnitude=impact)
    p_low = s.score(inp_low)["probability"]
    p_high = s.score(inp_high)["probability"]
    assert p_high >= p_low


# ─── 7. Direction propagation ─────────────────────────────────────────────


def test_bullish_sentiment_propagates_to_direction():
    s = RuleScorer(base_rate_fetcher=lambda *_args, **_kw: {"rate": 0.60, "n": 30})
    out = s.score(_mk_input(sentiment="bullish", signal_score=8))
    assert out["direction"] == "bullish"


def test_bearish_sentiment_propagates_to_direction():
    s = RuleScorer(base_rate_fetcher=lambda *_args, **_kw: {"rate": 0.60, "n": 30})
    out = s.score(_mk_input(sentiment="bearish", signal_score=8))
    assert out["direction"] == "bearish"
