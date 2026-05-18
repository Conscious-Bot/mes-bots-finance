"""Tests for shared.prices FX layer (Day 11 ADR 004 USD canonical Batch 1).

Tests parametric currency conversion + FX invariants + hardcoded rates.
Does NOT test get_current_price (yfinance-dependent, integration scope).
"""

import pytest
from hypothesis import given, strategies as st
from pytest import approx

from shared.prices import (
    BASE_CURRENCY,
    HARDCODED_FX_TO_EUR,
    HARDCODED_FX_TO_USD,
    get_currency_for_ticker,
    get_fx_rate,
)


def test_base_currency_is_usd() -> None:
    """ADR 004: canonical changed from EUR to USD."""
    assert BASE_CURRENCY == "USD"


def test_hardcoded_fx_to_usd_self_is_one() -> None:
    assert HARDCODED_FX_TO_USD["USD"] == approx(1.0)


def test_hardcoded_fx_to_usd_eur_inverse() -> None:
    """USD/EUR rate ~= 1/0.858 ~= 1.166."""
    assert HARDCODED_FX_TO_USD["EUR"] == approx(1.0 / 0.858, rel=1e-6)


def test_fx_rate_identity() -> None:
    """get_fx_rate(x, x) == 1.0 for any currency."""
    for cur in HARDCODED_FX_TO_EUR:
        assert get_fx_rate(cur, cur) == 1.0


@given(
    st.sampled_from(list(HARDCODED_FX_TO_EUR.keys())),
    st.sampled_from(list(HARDCODED_FX_TO_EUR.keys())),
)
def test_fx_rate_roundtrip(cur1: str, cur2: str) -> None:
    """rate(x,y) * rate(y,x) ~= 1.0."""
    a = get_fx_rate(cur1, cur2)
    b = get_fx_rate(cur2, cur1)
    if a is not None and b is not None:
        assert a * b == approx(1.0, rel=1e-6)


@given(
    st.sampled_from(list(HARDCODED_FX_TO_EUR.keys())),
    st.sampled_from(list(HARDCODED_FX_TO_EUR.keys())),
    st.sampled_from(list(HARDCODED_FX_TO_EUR.keys())),
)
def test_fx_rate_transitivity(cur1: str, cur2: str, cur3: str) -> None:
    """rate(x,y) * rate(y,z) ~= rate(x,z)."""
    direct = get_fx_rate(cur1, cur3)
    via = get_fx_rate(cur1, cur2)
    via2 = get_fx_rate(cur2, cur3)
    if direct is not None and via is not None and via2 is not None:
        assert via * via2 == approx(direct, rel=1e-6)


def test_get_currency_for_ticker_us_default() -> None:
    assert get_currency_for_ticker("AAPL") == "USD"
    assert get_currency_for_ticker("MSFT") == "USD"


def test_get_currency_for_ticker_suffix() -> None:
    assert get_currency_for_ticker("6920.T") == "JPY"
    assert get_currency_for_ticker("000660.KS") == "KRW"
    assert get_currency_for_ticker("MC.PA") == "EUR"


def test_get_current_price_in_usd_native(monkeypatch: pytest.MonkeyPatch) -> None:
    """USD-native ticker (no suffix) → no conversion."""
    monkeypatch.setattr("shared.prices.get_current_price", lambda t: 150.0)
    from shared.prices import get_current_price_in_usd

    assert get_current_price_in_usd("AAPL") == 150.0


def test_get_current_price_in_eur_from_usd(monkeypatch: pytest.MonkeyPatch) -> None:
    """USD ticker → EUR at 0.858."""
    monkeypatch.setattr("shared.prices.get_current_price", lambda t: 100.0)
    from shared.prices import get_current_price_in_eur

    assert get_current_price_in_eur("AAPL") == approx(85.8, rel=1e-3)


def test_get_current_price_in_usd_from_jpy(monkeypatch: pytest.MonkeyPatch) -> None:
    """JPY-native ticker → USD."""
    monkeypatch.setattr("shared.prices.get_current_price", lambda t: 10000.0)
    from shared.prices import get_current_price_in_usd

    expected = 10000.0 * (0.005467 / 0.858)
    assert get_current_price_in_usd("6920.T") == approx(expected, rel=1e-3)


def test_get_current_price_returns_none_when_raw_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("shared.prices.get_current_price", lambda t: None)
    from shared.prices import get_current_price_in_usd

    assert get_current_price_in_usd("INVALID") is None
