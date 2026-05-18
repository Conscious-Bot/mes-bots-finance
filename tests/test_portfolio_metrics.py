"""Property-based tests for shared/portfolio_metrics.py.

Focuses on pure functions (parse_eur_invested) and aggregator math
(compute_portfolio_return_eur invariants). yfinance fetches not mocked
- those tested via empirical Telegram /kpi_status retest, not unit.
"""

import logging
from unittest.mock import MagicMock

import pandas as pd
from hypothesis import given, strategies as st

from shared.portfolio_metrics import (
    compute_portfolio_return_eur,
    fetch_benchmark_return_eur,
    parse_eur_invested,
)


def test_parse_eur_invested_legacy_format():
    """Standard legacy_import_2026_05_15 format."""
    s = "legacy_import_2026_05_15 | account=PEA | eur_invested=3930"
    assert parse_eur_invested(s) == 3930.0


def test_parse_eur_invested_decimal():
    """Decimal value parses."""
    assert parse_eur_invested("eur_invested=42.5") == 42.5


def test_parse_eur_invested_missing():
    """No tag present returns None."""
    assert parse_eur_invested("no tag here") is None
    assert parse_eur_invested("") is None
    assert parse_eur_invested(None) is None


def test_parse_eur_invested_malformed():
    """Empty value or non-numeric returns None (graceful)."""
    assert parse_eur_invested("eur_invested=") is None
    assert parse_eur_invested("eur_invested=abc") is None


def test_parse_eur_invested_within_larger_string():
    """Pattern found anywhere in notes."""
    s = "some prefix eur_invested=100 some suffix"
    assert parse_eur_invested(s) == 100.0


@given(st.floats(min_value=0.01, max_value=1e7, allow_nan=False, allow_infinity=False))
def test_parse_eur_invested_roundtrip(amount):
    """Property: parse(format(N)) == N for valid amounts."""
    s = f"legacy | account=TR | eur_invested={amount}"
    parsed = parse_eur_invested(s)
    assert parsed is not None
    # 0.01% tolerance for float str repr edge cases
    assert abs(parsed - amount) < max(0.01, abs(amount) * 0.0001)


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz_= ", min_size=0, max_size=50))
def test_parse_eur_invested_no_crash_on_arbitrary(text):
    """Property: never raises on arbitrary text input."""
    result = parse_eur_invested(text)
    assert result is None or isinstance(result, float)


@given(st.one_of(st.none(), st.text()))
def test_parse_eur_invested_total_function(text):
    """Property: always returns None or float, never raises."""
    result = parse_eur_invested(text)
    assert result is None or isinstance(result, float)



# === Day 9 Audit Ship IV M1 — coverage compute_portfolio_return_eur ===


class TestComputePortfolioReturnEur:
    """Aggregator tests via monkeypatch (DB list_positions + EUR price helpers)."""

    def test_empty_positions_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "shared.portfolio_metrics.list_positions",
            lambda status="open": [],
        )
        assert compute_portfolio_return_eur() is None

    def test_single_position_with_tag(self, monkeypatch):
        positions = [{
            "ticker": "ASML.AS",
            "qty": 3.0,
            "avg_cost": 1309.0,
            "notes": "legacy_import | eur_invested=3930",
            "opened_at": "2026-05-15T11:39:19+00:00",
        }]
        monkeypatch.setattr(
            "shared.portfolio_metrics.list_positions",
            lambda status="open": positions,
        )
        monkeypatch.setattr(
            "shared.portfolio_metrics.get_current_price_in",
            lambda t, c: 1350.0,
        )
        r = compute_portfolio_return_eur()
        assert r is not None
        assert abs(r["total_entry_eur"] - 3930.0) < 0.01
        assert abs(r["total_current_eur"] - 3.0 * 1350.0) < 0.01
        assert r["positions_priced"] == 1
        assert r["positions_total"] == 1

    def test_fallback_currency_aware_usd(self, monkeypatch):
        """H2 fix: position without tag, USD avg_cost converted via fx=0.858."""
        positions = [{
            "ticker": "AMD",
            "qty": 10.0,
            "avg_cost": 200.0,
            "notes": "no tag here",
            "opened_at": "2026-05-15T11:39:19+00:00",
        }]
        monkeypatch.setattr(
            "shared.portfolio_metrics.list_positions",
            lambda status="open": positions,
        )
        monkeypatch.setattr(
            "shared.portfolio_metrics.get_current_price_in",
            lambda t, c: 180.0,
        )
        r = compute_portfolio_return_eur()
        assert r is not None
        expected_entry = 10.0 * 200.0 * 0.858
        assert abs(r["total_entry_eur"] - expected_entry) < 1.0

    def test_fallback_currency_aware_jpy(self, monkeypatch):
        """H2 fix: .T suffix infers JPY currency."""
        positions = [{
            "ticker": "4063.T",
            "qty": 30.0,
            "avg_cost": 4500.0,
            "notes": "no tag",
            "opened_at": "2026-05-15T11:39:19+00:00",
        }]
        monkeypatch.setattr(
            "shared.portfolio_metrics.list_positions",
            lambda status="open": positions,
        )
        monkeypatch.setattr(
            "shared.portfolio_metrics.get_current_price_in",
            lambda t, c: 25.0,
        )
        r = compute_portfolio_return_eur()
        assert r is not None
        expected_entry = 30.0 * 4500.0 * 0.005467
        assert abs(r["total_entry_eur"] - expected_entry) < 1.0

    def test_unpriced_position_skipped_both_sides(self, monkeypatch):
        """Position with None live price excluded from BOTH entry and current sums."""
        positions = [
            {"ticker": "ASML.AS", "qty": 3.0, "avg_cost": 1309.0,
             "notes": "eur_invested=3930",
             "opened_at": "2026-05-15T11:39:19+00:00"},
            {"ticker": "DEAD", "qty": 10.0, "avg_cost": 50.0,
             "notes": "eur_invested=500",
             "opened_at": "2026-05-15T11:39:19+00:00"},
        ]

        def mock_price(t, c):
            return 1350.0 if t == "ASML.AS" else None
        monkeypatch.setattr(
            "shared.portfolio_metrics.list_positions",
            lambda status="open": positions,
        )
        monkeypatch.setattr(
            "shared.portfolio_metrics.get_current_price_in", mock_price,
        )
        r = compute_portfolio_return_eur()
        assert r is not None
        assert r["positions_priced"] == 1
        assert r["positions_total"] == 2
        assert abs(r["total_entry_eur"] - 3930.0) < 0.01

    def test_all_unpriced_returns_none(self, monkeypatch):
        positions = [{
            "ticker": "DEAD", "qty": 10, "avg_cost": 50,
            "notes": "eur_invested=500",
            "opened_at": "2026-05-15T11:39:19+00:00",
        }]
        monkeypatch.setattr(
            "shared.portfolio_metrics.list_positions",
            lambda status="open": positions,
        )
        monkeypatch.setattr(
            "shared.portfolio_metrics.get_current_price_in",
            lambda t, c: None,
        )
        assert compute_portfolio_return_eur() is None

    def test_l1_naive_datetime_warns_and_treats_as_utc(self, monkeypatch, caplog):
        """L1 fix: naive opened_at logs warning + treats as UTC."""
        positions = [{
            "ticker": "ASML.AS", "qty": 3.0, "avg_cost": 1309.0,
            "notes": "eur_invested=3930",
            "opened_at": "2026-05-15 11:39:19",
        }]
        monkeypatch.setattr(
            "shared.portfolio_metrics.list_positions",
            lambda status="open": positions,
        )
        monkeypatch.setattr(
            "shared.portfolio_metrics.get_current_price_in",
            lambda t, c: 1350.0,
        )
        with caplog.at_level(logging.WARNING):
            r = compute_portfolio_return_eur()
        assert r is not None
        assert r["days"] >= 0
        assert any("naive opened_at" in rec.message for rec in caplog.records)


# === Day 9 Audit Ship IV M1 — coverage fetch_benchmark_return_eur ===


class TestFetchBenchmarkReturnEur:
    """Benchmark fetch tests via yfinance Ticker mocks."""

    def test_returns_none_on_yfinance_exception(self, monkeypatch):
        def raise_exc(ticker):
            raise RuntimeError("yfinance API down")
        monkeypatch.setattr("yfinance.Ticker", raise_exc)
        assert fetch_benchmark_return_eur("SPY", 30) is None

    def test_returns_none_on_empty_history(self, monkeypatch):
        empty_mock = MagicMock()
        empty_mock.history.return_value = pd.DataFrame()
        monkeypatch.setattr("yfinance.Ticker", lambda t, c: empty_mock)
        assert fetch_benchmark_return_eur("SPY", 30) is None

    def test_eur_return_with_fx_change(self, monkeypatch):
        """Cross-currency: SPY USD+10% with EUR strengthening yields lower EUR return."""
        spy_hist = pd.DataFrame({"Close": [100.0, 105.0, 110.0]})
        fx_hist = pd.DataFrame({"Close": [1.10, 1.15, 1.20]})

        def mock_ticker(t):
            m = MagicMock()
            m.history.return_value = fx_hist if t == "EURUSD=X" else spy_hist
            return m
        monkeypatch.setattr("yfinance.Ticker", mock_ticker)
        ret = fetch_benchmark_return_eur("SPY", 30)
        assert ret is not None
        expected = ((110.0 / 1.20) / (100.0 / 1.10) - 1) * 100
        assert abs(ret - expected) < 0.01

    def test_eur_return_no_fx_change_equals_usd_return(self, monkeypatch):
        """Math property: no FX change -> EUR return == USD return."""
        spy_hist = pd.DataFrame({"Close": [100.0, 110.0]})
        fx_hist = pd.DataFrame({"Close": [1.10, 1.10]})

        def mock_ticker(t):
            m = MagicMock()
            m.history.return_value = fx_hist if t == "EURUSD=X" else spy_hist
            return m
        monkeypatch.setattr("yfinance.Ticker", mock_ticker)
        ret = fetch_benchmark_return_eur("SPY", 30)
        assert ret is not None
        assert abs(ret - 10.0) < 0.01

    def test_returns_none_on_fx_empty(self, monkeypatch):
        spy_hist = pd.DataFrame({"Close": [100.0, 110.0]})
        fx_hist = pd.DataFrame()

        def mock_ticker(t):
            m = MagicMock()
            m.history.return_value = fx_hist if t == "EURUSD=X" else spy_hist
            return m
        monkeypatch.setattr("yfinance.Ticker", mock_ticker)
        assert fetch_benchmark_return_eur("SPY", 30) is None

    def test_returns_none_on_zero_start_price(self, monkeypatch):
        """Defensive: protects against div by zero on bad ticker data."""
        spy_hist = pd.DataFrame({"Close": [0.0, 110.0]})
        fx_hist = pd.DataFrame({"Close": [1.10, 1.10]})

        def mock_ticker(t):
            m = MagicMock()
            m.history.return_value = fx_hist if t == "EURUSD=X" else spy_hist
            return m
        monkeypatch.setattr("yfinance.Ticker", mock_ticker)
        assert fetch_benchmark_return_eur("SPY", 30) is None
