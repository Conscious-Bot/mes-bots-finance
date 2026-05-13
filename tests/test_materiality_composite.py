"""Property-based tests for materiality_v2.compute_composite_score."""

from hypothesis import given, settings, strategies as st

from intelligence.materiality_v2 import TIME_FACTORS, compute_composite_score


def _bd(imp, rev, time="medium"):
    return {"impact_magnitude": imp, "reversibility": rev, "time_to_realization": time}


@given(
    imp=st.floats(1.0, 5.0, allow_nan=False),
    rev=st.floats(1.0, 5.0, allow_nan=False),
    time=st.sampled_from(list(TIME_FACTORS.keys())),
)
@settings(max_examples=500)
def test_composite_in_valid_range(imp, rev, time):
    s = compute_composite_score(_bd(imp, rev, time))
    assert 2.0 <= s <= 10.0


def test_composite_max():
    assert abs(compute_composite_score(_bd(5, 1, "urgent")) - 10.0) < 0.01


def test_composite_min():
    assert abs(compute_composite_score(_bd(1, 5, "slow")) - 2.0) < 0.01


def test_composite_none_returns_none():
    assert compute_composite_score(None) is None


def test_composite_empty_returns_none():
    assert compute_composite_score({}) is None


@given(
    imp1=st.floats(1.0, 5.0, allow_nan=False),
    imp2=st.floats(1.0, 5.0, allow_nan=False),
    rev=st.floats(1.0, 5.0, allow_nan=False),
)
@settings(max_examples=300)
def test_composite_monotone_impact(imp1, imp2, rev):
    s1 = compute_composite_score(_bd(imp1, rev, "medium"))
    s2 = compute_composite_score(_bd(imp2, rev, "medium"))
    if imp1 <= imp2:
        assert s1 <= s2 + 0.01


@given(
    rev1=st.floats(1.0, 5.0, allow_nan=False),
    rev2=st.floats(1.0, 5.0, allow_nan=False),
    imp=st.floats(1.0, 5.0, allow_nan=False),
)
@settings(max_examples=300)
def test_composite_antimonotone_rev(rev1, rev2, imp):
    s1 = compute_composite_score(_bd(imp, rev1, "medium"))
    s2 = compute_composite_score(_bd(imp, rev2, "medium"))
    if rev1 <= rev2:
        assert s1 >= s2 - 0.01


def test_composite_time_ordering():
    u = compute_composite_score(_bd(3, 3, "urgent"))
    m = compute_composite_score(_bd(3, 3, "medium"))
    sl = compute_composite_score(_bd(3, 3, "slow"))
    assert u > m > sl


def test_composite_unknown_time_defaults_na():
    u = compute_composite_score(_bd(3, 3, "random_str"))
    n = compute_composite_score(_bd(3, 3, "na"))
    assert abs(u - n) < 0.01


def test_composite_rounded_two_decimals():
    s = compute_composite_score(_bd(3.14, 2.71, "medium"))
    assert s == round(s, 2)
