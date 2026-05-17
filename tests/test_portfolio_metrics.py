"""Property-based tests for shared/portfolio_metrics.py.

Focuses on pure functions (parse_eur_invested) and aggregator math
(compute_portfolio_return_eur invariants). yfinance fetches not mocked
- those tested via empirical Telegram /kpi_status retest, not unit.
"""

from hypothesis import given, strategies as st

from shared.portfolio_metrics import parse_eur_invested


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
