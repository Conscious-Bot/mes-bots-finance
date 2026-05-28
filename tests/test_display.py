"""Property-based tests for shared/display.py canonical helpers.

Tests are CURRENCY-AGNOSTIC: they assert against CANONICAL_FINANCE.value
and CANONICAL_BILLING.value rather than hardcoded symbols. Migration of
canonical currency (e.g. flip CANONICAL_FINANCE to Currency.USD) leaves
this test suite green.
"""

from hypothesis import given, strategies as st

from shared import display
from shared.display import CANONICAL_BILLING, CANONICAL_FINANCE, Currency


# ===== Currency enum sanity =====
def test_currency_eur_is_euro_symbol():
    assert Currency.EUR.value == "\u20ac"


def test_currency_usd_is_dollar():
    assert Currency.USD.value == "$"


def test_canonical_finance_is_eur_for_now():
    """Sanity check current state. Will change post USD migration."""
    assert CANONICAL_FINANCE == Currency.EUR


def test_canonical_billing_is_usd():
    """Anthropic structural invariant — should never change."""
    assert CANONICAL_BILLING == Currency.USD


# ===== format_money (low-level primitive) =====
@given(st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
def test_format_money_eur_always_starts_with_euro(value):
    assert display.format_money(value, Currency.EUR).startswith(Currency.EUR.value)


@given(st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
def test_format_money_usd_always_starts_with_dollar(value):
    assert display.format_money(value, Currency.USD).startswith(Currency.USD.value)


@given(
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.integers(min_value=4, max_value=20),
    st.sampled_from([Currency.EUR, Currency.USD]),
)
def test_format_money_width_minimum_padding(value, width, currency):
    result = display.format_money(value, currency, decimals=2, width=width)
    numeric = result[len(currency.value) :]
    assert len(numeric) >= width


# ===== format_finance (canonical wrapper) =====
@given(st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
def test_format_finance_uses_canonical_finance_symbol(value):
    """Currency-agnostic invariant: survives CANONICAL_FINANCE flip."""
    result = display.format_finance(value)
    assert result.startswith(CANONICAL_FINANCE.value)


def test_format_finance_no_width():
    result = display.format_finance(1234.56)
    assert result == f"{CANONICAL_FINANCE.value}1,234.56"


def test_format_finance_decimals_zero():
    result = display.format_finance(1234.56, decimals=0)
    assert result == f"{CANONICAL_FINANCE.value}1,235"


# ===== format_billing =====
@given(st.floats(min_value=0, max_value=1000, allow_nan=False))
def test_format_billing_uses_canonical_billing_symbol(value):
    result = display.format_billing(value)
    assert result.startswith(CANONICAL_BILLING.value)


def test_format_billing_typical_llm_cost():
    assert display.format_billing(0.39, decimals=2) == "$0.39"


# ===== format_pct =====
@given(st.floats(min_value=-100, max_value=100, allow_nan=False))
def test_format_pct_signed_always_has_sign_and_percent(value):
    result = display.format_pct(value, signed=True)
    assert result.endswith("%")
    # Round-to-zero normalizes to "+0.0%" per UX policy
    rounded = round(value, 1)
    if rounded == 0 or value >= 0:
        assert result.startswith("+"), f"Expected + for value={value} (rounded={rounded}), got {result!r}"
    else:
        assert result.startswith("-"), f"Expected - for value={value} (rounded={rounded}), got {result!r}"


def test_format_pct_zero_is_plus_zero():
    assert display.format_pct(0.0) == "+0.0%"


def test_format_pct_unsigned():
    assert display.format_pct(5.0, signed=False) == "5.0%"


# ===== format_pnl_pct =====
def test_format_pnl_pct_none_returns_fixed_width():
    result = display.format_pnl_pct(None, width=7)
    assert len(result) == 7
    assert "n/a" in result


@given(st.floats(min_value=-100, max_value=100, allow_nan=False))
def test_format_pnl_pct_value_has_sign_and_percent(value):
    result = display.format_pnl_pct(value, width=7)
    assert "%" in result


# ===== format_position_line =====
def test_format_position_line_full_render():
    line = display.format_position_line(
        ticker="6920.T",
        name="LASERTEC CORP",
        conviction=5,
        avg_cost=208.22,
        current_price=209.99,
        market_value=2017,
        pct_book=4.7,
        pnl_pct=1.5,
    )
    assert "6920.T" in line
    assert "LASERTEC CORP" in line
    assert "c5" in line
    assert CANONICAL_FINANCE.value in line
    assert "+1.5%" in line


def test_format_position_line_none_current_price():
    line = display.format_position_line(
        ticker="NVDA",
        name="NVIDIA",
        conviction=3,
        avg_cost=100.0,
        current_price=None,
        market_value=0,
        pct_book=0,
        pnl_pct=None,
    )
    assert "n/a" in line


def test_format_position_line_name_truncation():
    long_name = "A" * 50
    line = display.format_position_line(
        ticker="X",
        name=long_name,
        conviction=1,
        avg_cost=1.0,
        current_price=1.0,
        market_value=1.0,
        pct_book=0,
        pnl_pct=0,
    )
    assert "A" * 50 not in line


def test_format_position_line_none_name_fallback_ticker():
    line = display.format_position_line(
        ticker="UNKNOWN",
        name=None,
        conviction=2,
        avg_cost=10.0,
        current_price=10.0,
        market_value=10.0,
        pct_book=1.0,
        pnl_pct=0.0,
    )
    assert "UNKNOWN" in line


# ===== format_brief_position_line =====
def test_format_brief_position_line_full_render():
    line = display.format_brief_position_line(
        ticker="6920.T",
        name="LASERTEC CORP",
        conviction=5,
        value=2017.0,
        pnl_pct=1.5,
    )
    assert "6920.T" in line
    assert "c5" in line
    assert CANONICAL_FINANCE.value in line
    assert "+1.5%" in line


def test_format_brief_position_line_none_value_renders_n_a():
    line = display.format_brief_position_line(
        ticker="NVDA",
        name="NVIDIA",
        conviction=3,
        value=None,
        pnl_pct=None,
    )
    assert "price n/a" in line


# ===== format_aggregate_line =====
def test_format_aggregate_line_render():
    line = display.format_aggregate_line(
        label="semis_core",
        market_value=12345.67,
        pct_total=28.9,
        n_positions=7,
        pnl_pct=12.3,
    )
    assert "semis_core" in line
    assert CANONICAL_FINANCE.value in line
    assert "28.9%" in line
    assert "7 pos" in line
    assert "+12.3%" in line


# ===== signed=True behavior (for PnL displays) =====
def test_format_money_signed_positive_has_plus():
    assert display.format_money(100.0, Currency.EUR, signed=True) == "\u20ac+100.00"


def test_format_money_signed_negative_has_minus():
    assert display.format_money(-100.0, Currency.EUR, signed=True) == "\u20ac-100.00"


def test_format_finance_signed_works():
    """format_finance inherits signed param via format_money."""
    assert display.format_finance(50.0, signed=True).startswith(CANONICAL_FINANCE.value)
    assert "+50" in display.format_finance(50.0, signed=True)
    assert "-50" in display.format_finance(-50.0, signed=True)


def test_format_finance_signed_with_thousands_sep():
    """signed + thousands separator both apply."""
    result = display.format_finance(1234.56, signed=True)
    assert "+" in result
    assert "," in result
    assert "1,234.56" in result


def test_format_finance_signed_with_width():
    """signed + width both apply."""
    result = display.format_finance(100.0, decimals=2, width=10, signed=True)
    assert result.startswith(CANONICAL_FINANCE.value)
    numeric = result[1:]
    assert len(numeric) >= 10  # respects min width
    assert "+100.00" in result
