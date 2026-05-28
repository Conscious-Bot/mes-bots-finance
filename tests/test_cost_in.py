"""Property-based tests for shared.positions.cost_in helper.

ADR 005 (Day 13): avg_cost EUR canonical. cost_in converts EUR -> target_cur.
"""

from hypothesis import given, strategies as st

from shared.positions import cost_in


class TestCostIn:
    @given(st.floats(min_value=0.01, max_value=1e9, allow_nan=False, allow_infinity=False))
    def test_eur_target_idempotent(self, avg_cost_eur):
        """EUR -> EUR is identity, no fx applied."""
        assert cost_in(avg_cost_eur, "EUR") == avg_cost_eur

    def test_none_in_none_out(self):
        """None input propagates as None across target currencies."""
        assert cost_in(None, "USD") is None
        assert cost_in(None, "EUR") is None
        assert cost_in(None, "JPY") is None

    @given(st.floats(min_value=0.01, max_value=1e9, allow_nan=False, allow_infinity=False))
    def test_usd_conversion_positive(self, avg_cost_eur):
        """EUR -> USD always produces positive result for positive input."""
        result = cost_in(avg_cost_eur, "USD")
        assert result is not None
        assert result > 0

    def test_case_insensitive_target(self):
        """target_cur normalized via .upper(): both cases produce same result."""
        assert cost_in(100.0, "usd") == cost_in(100.0, "USD")
        assert cost_in(100.0, "eur") == cost_in(100.0, "EUR")

    @given(st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False))
    def test_proportional_in_usd(self, avg_cost_eur):
        """Linear in input: doubling EUR doubles USD output (single fx applied)."""
        a = cost_in(avg_cost_eur, "USD")
        b = cost_in(avg_cost_eur * 2, "USD")
        assert a is not None and b is not None
        assert abs(b - 2 * a) < 1e-6 * (b + 1)

    def test_zero_in_zero_out(self):
        """Zero EUR maps to zero in any target."""
        assert cost_in(0.0, "USD") == 0.0
        assert cost_in(0.0, "EUR") == 0.0
        assert cost_in(0.0, "JPY") == 0.0
