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
