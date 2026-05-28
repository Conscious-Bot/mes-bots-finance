from hypothesis import given, strategies as st

from shared.math_helpers import estimate_probability


@given(
    score=st.integers(min_value=0, max_value=20),
    cred=st.floats(min_value=0, max_value=1),
    stype=st.sampled_from([None, "catalyst", "data", "opinion", "narrative"]),
    imp=st.floats(min_value=0, max_value=10),
)
def test_bounds(score, cred, stype, imp):
    assert 0.50 <= estimate_probability(score, cred, stype, imp) <= 0.72


@given(
    s1=st.integers(min_value=0, max_value=20),
    s2=st.integers(min_value=0, max_value=20),
    cred=st.floats(min_value=0, max_value=1),
)
def test_monotonic_in_score(s1, s2, cred):
    if s1 <= s2:
        assert estimate_probability(s1, cred) <= estimate_probability(s2, cred)


@given(
    score=st.integers(min_value=0, max_value=20),
    cred=st.floats(min_value=0, max_value=1),
    imp=st.floats(min_value=0, max_value=10),
)
def test_catalyst_ge_narrative(score, cred, imp):
    assert estimate_probability(score, cred, "catalyst", imp) >= estimate_probability(score, cred, "narrative", imp)


def test_floor_when_all_none():
    assert estimate_probability(None, None) == 0.50


def test_dynamic_range_over_support():
    # Efficacy, not form: a strong signal must be meaningfully more confident than a
    # weak one across the empirical score support (~3..8). A near-constant estimator
    # passes bounds/monotonic/order/floor but fails here -- this is the regression guard.
    weak = estimate_probability(2, 0.5, "opinion", 0)
    strong = estimate_probability(8, 0.5, "catalyst", 5)
    assert strong - weak >= 0.15
    # score alone must move the prior by >= 0.12 over the support, credibility held flat
    assert estimate_probability(8, 0.5) - estimate_probability(3, 0.5) >= 0.12
