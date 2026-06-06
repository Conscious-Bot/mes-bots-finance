"""Tests for /signal_drilldown handler."""


import pytest

# CI marker : ce module tape sur storage.DB_PATH (data/bot.db gitignored).
# CI skip via . Local : tourne normalement.
pytestmark = pytest.mark.live_data

from hypothesis import given, strategies as st

from bot.handlers.signal_drilldown import (
    _compute_drilldown,
    _parse_breakdown,
    _ticker_in_entities,
)


class TestParseBreakdown:
    def test_empty(self):
        assert _parse_breakdown(None) == {}
        assert _parse_breakdown("") == {}

    def test_invalid_json(self):
        assert _parse_breakdown("not json {{{") == {}

    def test_valid(self):
        raw = '{"impact_magnitude": 4.0, "reasoning": "test"}'
        assert _parse_breakdown(raw) == {"impact_magnitude": 4.0, "reasoning": "test"}

    def test_non_dict_root(self):
        assert _parse_breakdown('["array", "not", "dict"]') == {}

    @given(st.text(min_size=0, max_size=200))
    def test_never_crashes(self, raw):
        result = _parse_breakdown(raw)
        assert isinstance(result, dict)


class TestTickerInEntities:
    def test_empty(self):
        assert _ticker_in_entities(None, "AMD") is False
        assert _ticker_in_entities("", "AMD") is False

    def test_list_match(self):
        assert _ticker_in_entities('["AMD", "NVDA"]', "AMD") is True

    def test_list_no_match(self):
        assert _ticker_in_entities('["NVDA"]', "AMD") is False

    def test_dict_tickers_field(self):
        assert _ticker_in_entities('{"tickers": ["AMD"]}', "AMD") is True

    def test_invalid_json(self):
        assert _ticker_in_entities("bad json", "AMD") is False

    @given(st.text(min_size=0, max_size=100), st.text(min_size=1, max_size=10))
    def test_never_crashes(self, raw, ticker):
        result = _ticker_in_entities(raw, ticker)
        assert isinstance(result, bool)


class TestComputeDrilldown:
    def test_compute_runs(self):
        """Smoke: compute returns expected dict keys."""
        data = _compute_drilldown("AMD", 30, 2.0)
        expected = {"ticker", "window_days", "min_impact", "signals", "source_counts", "decision_count"}
        assert set(data.keys()) == expected
        assert data["ticker"] == "AMD"

    def test_signals_invariants(self):
        """Property: each signal has consistent shape + valid impact."""
        data = _compute_drilldown("AMD", 30, 2.0)
        for sig in data["signals"]:
            assert "id" in sig
            assert "impact" in sig
            assert sig["impact"] >= 2.0  # filter respected

    def test_source_counts_sum_eq_signals(self):
        """Invariant: sum of source_counts == len(signals) (each signal has 1 source)."""
        data = _compute_drilldown("AMD", 30, 2.0)
        assert sum(data["source_counts"].values()) == len(data["signals"])

    def test_unknown_ticker(self):
        """Unknown ticker returns empty signals + zero decisions."""
        data = _compute_drilldown("ZZZZZZZ", 30, 2.0)
        assert data["signals"] == []
        assert data["decision_count"] == 0
