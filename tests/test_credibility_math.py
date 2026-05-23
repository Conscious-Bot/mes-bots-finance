"""Property-based tests for credibility clamping (mirrors SQL MAX(0, MIN(1, c+delta)))."""

from hypothesis import given, settings, strategies as st

from shared.math_helpers import clamp_credibility


@given(current=st.floats(0.0, 1.0, allow_nan=False), delta=st.floats(-2.0, 2.0, allow_nan=False))
@settings(max_examples=500)
def test_clamp_output_in_unit_interval(current, delta):
    r = clamp_credibility(current, delta)
    assert 0.0 <= r <= 1.0


@given(current=st.floats(0.0, 1.0, allow_nan=False))
def test_clamp_identity_zero_delta(current):
    assert clamp_credibility(current, 0.0) == current


@given(current=st.floats(0.0, 1.0, allow_nan=False))
def test_clamp_floor_at_zero(current):
    assert clamp_credibility(current, -10.0) == 0.0


@given(current=st.floats(0.0, 1.0, allow_nan=False))
def test_clamp_ceiling_at_one(current):
    assert clamp_credibility(current, 10.0) == 1.0


@given(current=st.floats(0.1, 0.9, allow_nan=False), delta=st.floats(-0.1, 0.1, allow_nan=False))
def test_clamp_linear_mid_range(current, delta):
    r = clamp_credibility(current, delta)
    expected = current + delta
    if 0.0 <= expected <= 1.0:
        assert abs(r - expected) < 1e-9


def test_clamp_none_returns_none():
    assert clamp_credibility(None, 0.5) is None


from hypothesis import given, strategies as st

from shared.math_helpers import credibility_from_hitrate


@given(c=st.integers(0, 1000), i=st.integers(0, 1000))
def test_cred_hitrate_in_unit(c, i):
    assert 0.0 <= credibility_from_hitrate(c, i) <= 1.0


@given(n=st.integers(0, 1000))
def test_cred_hitrate_balanced_half(n):
    assert credibility_from_hitrate(n, n) == 0.5


@given(c=st.integers(1, 1000))
def test_cred_hitrate_perfect_below_one(c):
    assert credibility_from_hitrate(c, 0) < 1.0
