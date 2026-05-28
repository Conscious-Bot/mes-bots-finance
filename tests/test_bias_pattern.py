"""Tests for /bias_pattern handler."""

from hypothesis import given, strategies as st

from bot.handlers.bias_pattern import _compute_bias_pattern, _parse_bias_tags
from intelligence.bias_tagger import BIASES


class TestParseBiasTags:
    def test_empty(self):
        assert _parse_bias_tags(None) == []
        assert _parse_bias_tags("") == []
        assert _parse_bias_tags("[]") == []

    def test_valid_list(self):
        result = _parse_bias_tags('["anchoring", "fomo"]')
        assert sorted(result) == ["anchoring", "fomo"]

    def test_filters_unknown_tags(self):
        # Only tags in BIASES taxonomy survive
        result = _parse_bias_tags('["anchoring", "not_a_real_bias", "fomo"]')
        assert "anchoring" in result
        assert "fomo" in result
        assert "not_a_real_bias" not in result

    def test_invalid_json(self):
        assert _parse_bias_tags("not json {{{") == []

    def test_non_list_root(self):
        # JSON dict at root should return empty (we expect a list)
        assert _parse_bias_tags('{"anchoring": true}') == []

    @given(st.text(min_size=0, max_size=300))
    def test_never_crashes(self, raw):
        result = _parse_bias_tags(raw)
        assert isinstance(result, list)
        for tag in result:
            assert tag in BIASES


class TestComputeBiasPattern:
    def test_smoke(self):
        data = _compute_bias_pattern(window_days=90)
        expected_keys = {
            "window_days",
            "total_decisions",
            "with_bias_tags",
            "with_mistake_auto",
            "with_mistake_manual",
            "bias_counts",
            "mistake_auto_counts",
            "mistake_manual_counts",
            "ticker_bias_map",
            "tagged_decisions",
        }
        assert set(data.keys()) == expected_keys

    def test_with_counts_bounded(self):
        """Invariant: with_* counts <= total_decisions."""
        data = _compute_bias_pattern(90)
        assert data["with_bias_tags"] <= data["total_decisions"]
        assert data["with_mistake_auto"] <= data["total_decisions"]
        assert data["with_mistake_manual"] <= data["total_decisions"]

    def test_ticker_bias_map_only_for_tagged(self):
        """Invariant: every ticker in ticker_bias_map has >= 1 bias."""
        data = _compute_bias_pattern(90)
        for _ticker, counter in data["ticker_bias_map"].items():
            assert sum(counter.values()) >= 1

    def test_bias_counts_only_valid_taxonomy(self):
        """Invariant: all bias counts use BIASES taxonomy keys."""
        data = _compute_bias_pattern(90)
        for bias in data["bias_counts"]:
            assert bias in BIASES

    def test_window_param_respected(self):
        data30 = _compute_bias_pattern(30)
        data90 = _compute_bias_pattern(90)
        # 30d subset of 90d (monotonic)
        assert data30["total_decisions"] <= data90["total_decisions"]
