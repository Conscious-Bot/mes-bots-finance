"""Tests for /thesis_health handler."""


import pytest

# CI marker : ce module tape sur storage.DB_PATH (data/bot.db gitignored).
# CI skip via . Local : tourne normalement.
pytestmark = pytest.mark.live_data

from hypothesis import given, strategies as st

from bot.handlers.thesis_health import _compute_health, _extract_narrative, _ticker_in_entities


class TestExtractNarrative:
    def test_empty(self):
        assert _extract_narrative(None) == "untagged"
        assert _extract_narrative("") == "untagged"

    def test_no_match(self):
        assert _extract_narrative("just some text") == "untagged"

    def test_match(self):
        notes = "sector_thesis_id: STORAGE_AI_HYPERSCALE_2026\nsector_role: HBM"
        assert _extract_narrative(notes) == "STORAGE_AI_HYPERSCALE_2026"

    @given(st.text(min_size=0, max_size=500))
    def test_never_crashes(self, raw):
        result = _extract_narrative(raw)
        assert isinstance(result, str)


class TestTickerInEntities:
    def test_empty(self):
        assert _ticker_in_entities(None, "NVDA") is False
        assert _ticker_in_entities("", "NVDA") is False

    def test_match_list(self):
        assert _ticker_in_entities('["NVDA", "AMD"]', "NVDA") is True

    def test_no_match(self):
        assert _ticker_in_entities('["AMD"]', "NVDA") is False

    def test_invalid_json(self):
        assert _ticker_in_entities("not json", "NVDA") is False

    @given(st.text(max_size=100), st.text(min_size=1, max_size=10))
    def test_never_crashes(self, raw, ticker):
        result = _ticker_in_entities(raw, ticker)
        assert isinstance(result, bool)


class TestComputeHealth:
    def test_smoke(self):
        data = _compute_health(30, 3.0)
        expected_keys = {
            "window_days",
            "min_impact",
            "theses",
            "conviction_dist",
            "narrative_dist",
            "stale_count",
            "weak_count",
            "total",
        }
        assert set(data.keys()) == expected_keys

    def test_invariants(self):
        data = _compute_health(30, 3.0)
        # total == len(theses)
        assert data["total"] == len(data["theses"])
        # stale + weak counts non-negative
        assert data["stale_count"] >= 0
        assert data["weak_count"] >= 0
        # stale + weak <= total (each can flag, possibly both same thesis)
        assert data["stale_count"] <= data["total"]
        assert data["weak_count"] <= data["total"]

    def test_each_thesis_has_required_fields(self):
        data = _compute_health(30, 3.0)
        for t in data["theses"]:
            assert "id" in t
            assert "ticker" in t
            assert "conviction" in t
            assert "signal_count" in t
            assert "narrative" in t
            assert isinstance(t["signal_count"], int)
            assert t["signal_count"] >= 0

    def test_conviction_dist_sums_to_total(self):
        data = _compute_health(30, 3.0)
        # Conviction dist may exclude None conviction; sum <= total
        non_null = sum(1 for t in data["theses"] if t["conviction"] is not None)
        assert sum(data["conviction_dist"].values()) == non_null
