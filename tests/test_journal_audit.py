"""Tests for /journal_audit handler.

Property-based: ratio invariants. Empirical: known fixture-like cases.
"""

import pytest
from hypothesis import given, strategies as st

from bot.handlers.journal_audit import _compute_audit, _extract_tickers


class TestExtractTickers:
    def test_empty_input(self):
        assert _extract_tickers(None) == []
        assert _extract_tickers("") == []

    def test_invalid_json(self):
        assert _extract_tickers("not json") == []

    def test_simple_list(self):
        assert _extract_tickers('["NVDA", "AMD"]') == ["NVDA", "AMD"]

    def test_filters_non_ticker_strings(self):
        # Lowercase, too long, too short -> filtered
        result = _extract_tickers('["NVDA", "nvda", "TOOLONGTICKER", "X"]')
        assert result == ["NVDA"]

    def test_dict_with_ticker_key(self):
        result = _extract_tickers('[{"ticker": "NVDA"}, {"symbol": "AMD"}]')
        assert sorted(result) == ["AMD", "NVDA"]

    def test_dict_root_with_tickers_field(self):
        result = _extract_tickers('{"tickers": ["NVDA", "AMD"]}')
        assert sorted(result) == ["AMD", "NVDA"]

    @given(st.text(min_size=0, max_size=200))
    def test_never_crashes(self, raw):
        """Property: any input string returns a list, never raises."""
        result = _extract_tickers(raw)
        assert isinstance(result, list)
        for t in result:
            assert isinstance(t, str)


class TestComputeAuditInvariants:
    def test_compute_audit_runs(self):
        """Empirical smoke: compute_audit returns expected keys."""
        data = _compute_audit(window_days=30, min_impact=3.0)
        expected_keys = {
            "window_days",
            "min_impact",
            "total_signals",
            "total_decisions",
            "ticker_signal_counts",
            "ticker_last_signal",
            "ticker_decision_counts",
            "tickers_silent",
            "tickers_tracked",
        }
        assert set(data.keys()) == expected_keys

    def test_tracked_subset_of_signal_tickers_or_decisions(self):
        """Property: tracked = tickers with both signals AND decisions."""
        data = _compute_audit(window_days=30, min_impact=3.0)
        dec_tickers = set(data["ticker_decision_counts"].keys())
        tracked_set = {t for t, _, _ in data["tickers_tracked"]}
        # tracked must be subset of decisions (every tracked ticker has dec_count)
        assert tracked_set.issubset(dec_tickers)

    def test_silent_disjoint_from_decisions(self):
        """Property: silent tickers have ZERO decisions."""
        data = _compute_audit(window_days=30, min_impact=3.0)
        silent_set = {t for t, _, _ in data["tickers_silent"]}
        dec_set = set(data["ticker_decision_counts"].keys())
        assert silent_set.isdisjoint(dec_set)

    def test_silent_subset_of_signals(self):
        """Property: silent tickers must appear in signals."""
        data = _compute_audit(window_days=30, min_impact=3.0)
        silent_set = {t for t, _, _ in data["tickers_silent"]}
        sig_set = set(data["ticker_signal_counts"].keys())
        assert silent_set.issubset(sig_set)
