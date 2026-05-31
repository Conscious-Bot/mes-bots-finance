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


@pytest.fixture(autouse=True)
def _isolate_fx_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force tests to use hardcoded fallback path (deterministic, offline).
    Sans ca les property tests roundtrip/transitivity feraient des fetch
    yfinance reels -> non-reproductible + lent + ban-risk."""
    monkeypatch.setattr("shared.prices._fetch_fx_live", lambda f, t: None)
    from shared.prices import _FX_CACHE
    _FX_CACHE.clear()


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


# ===== Phase 2 R1 : live FX layer with cache + fallback =====


def test_get_fx_rate_uses_live_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si _fetch_fx_live retourne une valeur, get_fx_rate la retourne (pas le hardcoded)."""
    monkeypatch.setattr("shared.prices._fetch_fx_live", lambda f, t: 199.99)
    from shared.prices import _FX_CACHE
    _FX_CACHE.clear()
    rate = get_fx_rate("EUR", "JPY")
    assert rate == approx(199.99)
    assert rate != approx(1.0 / 0.005467, rel=1e-3)  # NOT the hardcoded fallback


def test_get_fx_rate_cache_hit_skips_refetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Apres premier fetch, les appels suivants dans le TTL ne refetchent pas."""
    call_count = {"n": 0}

    def fake_fetch(f: str, t: str) -> float:
        call_count["n"] += 1
        return 100.0

    monkeypatch.setattr("shared.prices._fetch_fx_live", fake_fetch)
    from shared.prices import _FX_CACHE
    _FX_CACHE.clear()

    get_fx_rate("USD", "JPY")
    get_fx_rate("USD", "JPY")
    get_fx_rate("USD", "JPY")
    assert call_count["n"] == 1  # fetched once, cached the 2 suivantes


def test_get_fx_rate_falls_back_to_hardcoded_on_live_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si live retourne None, fallback hardcoded prend le relais."""
    monkeypatch.setattr("shared.prices._fetch_fx_live", lambda f, t: None)
    from shared.prices import _FX_CACHE
    _FX_CACHE.clear()
    rate = get_fx_rate("JPY", "EUR")
    assert rate == approx(0.005467)  # hardcoded value


def test_get_fx_rate_identity_short_circuits_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_fx_rate(X, X) doit retourner 1.0 sans appeler le live."""
    call_count = {"n": 0}

    def fake_fetch(f: str, t: str) -> float:
        call_count["n"] += 1
        return 999.0

    monkeypatch.setattr("shared.prices._fetch_fx_live", fake_fetch)
    assert get_fx_rate("EUR", "EUR") == 1.0
    assert call_count["n"] == 0


# ===== Phase Ground-truth 31/05 : get_close_on (resolve_predictions fix) =====


def test_get_close_on_returns_close_for_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock yfinance pour donner un close connu, get_close_on doit l'extraire."""
    from unittest.mock import MagicMock

    import pandas as pd

    fake_df = pd.DataFrame(
        {"Close": [100.0, 101.0, 102.0]},
        index=pd.to_datetime(["2026-05-29", "2026-06-01", "2026-06-02"]),
    )
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = fake_df
    monkeypatch.setattr("shared.prices.yf.Ticker", lambda t: mock_ticker)
    from shared.prices import get_close_on

    assert get_close_on("AAPL", "2026-05-29") == 100.0


def test_get_close_on_weekend_returns_next_trading_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """date_str = samedi -> doit retourner le close du lundi. yfinance
    auto-aligne en n'incluant pas weekend dans son daily index."""
    from unittest.mock import MagicMock

    import pandas as pd

    fake_df = pd.DataFrame({"Close": [105.0]}, index=pd.to_datetime(["2026-06-01"]))
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = fake_df
    monkeypatch.setattr("shared.prices.yf.Ticker", lambda t: mock_ticker)
    from shared.prices import get_close_on

    assert get_close_on("AAPL", "2026-05-30") == 105.0  # 30/05 = samedi


def test_get_close_on_returns_none_for_empty_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ticker delisted / data gap > 7j -> None."""
    from unittest.mock import MagicMock

    import pandas as pd

    fake_df = pd.DataFrame({"Close": []})
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = fake_df
    monkeypatch.setattr("shared.prices.yf.Ticker", lambda t: mock_ticker)
    from shared.prices import get_close_on

    assert get_close_on("DELISTED", "2026-05-29") is None


def test_get_close_on_returns_none_for_invalid_date() -> None:
    """Date format invalide -> exception attrapee -> None (pas de crash)."""
    from shared.prices import get_close_on

    assert get_close_on("AAPL", "not-a-date") is None


# ===== fx_freshness / fx_is_stale (point #3 user 31/05 : max-age flag) =====


def test_fx_freshness_never_queried_returns_never() -> None:
    """Pair jamais query -> source='never_queried'."""
    from shared.prices import _FX_LIVE_LAST_SUCCESS, fx_freshness

    _FX_LIVE_LAST_SUCCESS.clear()
    out = fx_freshness("XYZ", "ABC")
    assert out["source"] == "never_queried"
    assert out["age_seconds"] is None


def test_fx_freshness_after_live_fetch_returns_live_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apres un live fetch reussi, freshness = live_cached avec age petit."""
    from shared.prices import _FX_CACHE, _FX_LIVE_LAST_SUCCESS, fx_freshness

    monkeypatch.setattr("shared.prices._fetch_fx_live", lambda f, t: 100.0)
    _FX_CACHE.clear()
    _FX_LIVE_LAST_SUCCESS.clear()
    get_fx_rate("USD", "JPY")
    out = fx_freshness("USD", "JPY")
    assert out["source"] == "live_cached"
    assert out["age_seconds"] is not None
    assert out["age_seconds"] < 10
    assert out["last_live_at"] is not None


def test_fx_is_stale_returns_true_when_never_queried() -> None:
    """Pair jamais query live -> fx_is_stale True (fallback en cours)."""
    from shared.prices import _FX_LIVE_LAST_SUCCESS, fx_is_stale

    _FX_LIVE_LAST_SUCCESS.clear()
    assert fx_is_stale("XYZ", "ABC") is True


def test_fx_is_stale_identity_returns_false() -> None:
    """fx_is_stale(X, X) = False (identite triviale, jamais stale)."""
    from shared.prices import fx_is_stale

    assert fx_is_stale("USD", "USD") is False
