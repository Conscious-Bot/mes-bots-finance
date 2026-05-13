"""Property-based tests for Brier score (mirrors learning.py L107-111)."""
from hypothesis import given, strategies as st, settings
from shared.math_helpers import compute_brier_score


@given(prob=st.floats(0.0, 1.0, allow_nan=False))
@settings(max_examples=500)
def test_brier_in_unit_interval(prob):
    for outcome in ('correct', 'incorrect', 'neutral'):
        s = compute_brier_score(prob, outcome)
        assert 0.0 <= s <= 1.0


def test_brier_perfect_predictions():
    assert compute_brier_score(1.0, 'correct') == 0.0
    assert compute_brier_score(0.0, 'incorrect') == 0.0
    assert compute_brier_score(0.5, 'neutral') == 0.0


def test_brier_worst_predictions():
    assert compute_brier_score(0.0, 'correct') == 1.0
    assert compute_brier_score(1.0, 'incorrect') == 1.0


@given(prob=st.floats(0.0, 1.0, allow_nan=False))
@settings(max_examples=300)
def test_brier_symmetry(prob):
    a = compute_brier_score(prob, 'incorrect')
    b = compute_brier_score(1.0 - prob, 'correct')
    assert abs(a - b) < 1e-12


@given(prob=st.floats(0.0, 1.0, allow_nan=False))
@settings(max_examples=300)
def test_brier_neutral_max_quarter(prob):
    s = compute_brier_score(prob, 'neutral')
    assert 0.0 <= s <= 0.25


def test_brier_none_prob():
    assert compute_brier_score(None, 'correct') is None


def test_brier_unknown_outcome_defaults_neutral():
    assert compute_brier_score(0.5, 'random') == 0.0
    assert abs(compute_brier_score(0.8, 'unknown') - 0.09) < 1e-12


@given(prob1=st.floats(0.0, 1.0, allow_nan=False), prob2=st.floats(0.0, 1.0, allow_nan=False))
@settings(max_examples=300)
def test_brier_monotone_distance(prob1, prob2):
    for outcome in ('correct', 'incorrect', 'neutral'):
        ob = {'correct': 1.0, 'incorrect': 0.0, 'neutral': 0.5}[outcome]
        d1 = abs(prob1 - ob)
        d2 = abs(prob2 - ob)
        b1 = compute_brier_score(prob1, outcome)
        b2 = compute_brier_score(prob2, outcome)
        if d1 <= d2:
            assert b1 <= b2 + 1e-12
