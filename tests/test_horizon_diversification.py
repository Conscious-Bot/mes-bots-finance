"""Property-based tests for horizon_for_signal_type."""

from hypothesis import given, settings, strategies as st

from intelligence.learning import SIGNAL_TYPE_HORIZONS, horizon_for_signal_type


def test_catalyst_short_horizon():
    """catalyst → 14 days base (event-driven, short window)."""
    assert horizon_for_signal_type("catalyst") == 14


def test_narrative_long_horizon():
    """narrative → 60 days (slow-burn)."""
    assert horizon_for_signal_type("narrative") == 60


def test_opinion_default():
    assert horizon_for_signal_type("opinion") == 30


def test_data_default():
    assert horizon_for_signal_type("data") == 30


def test_unknown_signal_type_fallback_30():
    assert horizon_for_signal_type("random_type") == 30
    assert horizon_for_signal_type(None) == 30


def test_high_impact_narrows_catalyst():
    """impact ≥4 narrows catalyst from 14 → 7."""
    assert horizon_for_signal_type("catalyst", impact_magnitude=4) == 7
    assert horizon_for_signal_type("catalyst", impact_magnitude=5) == 7


def test_high_impact_narrows_narrative():
    """impact ≥4 narrows narrative from 60 → 30."""
    assert horizon_for_signal_type("narrative", impact_magnitude=4) == 30


def test_low_impact_no_change():
    """impact <4 doesn't change base horizon."""
    assert horizon_for_signal_type("catalyst", impact_magnitude=2) == 14
    assert horizon_for_signal_type("narrative", impact_magnitude=3) == 60


@given(impact=st.floats(min_value=4.0, max_value=5.0, allow_nan=False))
@settings(max_examples=100)
def test_high_impact_always_narrows_or_keeps(impact):
    """impact≥4: output ≤ base for any signal_type."""
    for stype, base in SIGNAL_TYPE_HORIZONS.items():
        result = horizon_for_signal_type(stype, impact_magnitude=impact)
        assert result <= base, f"{stype} impact={impact} → {result} > base {base}"
        assert result >= 7, f"{stype} impact={impact} → {result} < min 7"


@given(impact=st.floats(min_value=0.0, max_value=3.9, allow_nan=False))
@settings(max_examples=100)
def test_low_impact_keeps_base(impact):
    """impact<4: output == base."""
    for stype, base in SIGNAL_TYPE_HORIZONS.items():
        assert horizon_for_signal_type(stype, impact_magnitude=impact) == base


@given(
    stype=st.sampled_from([*list(SIGNAL_TYPE_HORIZONS.keys()), "unknown", None]),
    impact=st.one_of(st.none(), st.floats(0.0, 5.0, allow_nan=False)),
)
@settings(max_examples=200)
def test_horizon_always_positive_min_7(stype, impact):
    """Universal invariant: horizon ∈ [7, 60]."""
    result = horizon_for_signal_type(stype, impact)
    assert 7 <= result <= 60


def test_catalyst_always_shorter_than_narrative():
    """Structural invariant: catalyst horizon < narrative horizon."""
    for impact in (None, 1, 2, 3, 4, 5):
        c = horizon_for_signal_type("catalyst", impact)
        n = horizon_for_signal_type("narrative", impact)
        assert c < n, f"impact={impact}: catalyst={c} not < narrative={n}"
