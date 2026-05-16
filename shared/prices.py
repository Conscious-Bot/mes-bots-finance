"""Price data wrapper. Thin abstraction over yfinance so we can swap
in Polygon/Tiingo later without touching downstream code.

Returns None on failures - downstream must handle gracefully.
"""

import logging as _logging
from datetime import datetime, timedelta

_logging.getLogger("yfinance").setLevel(_logging.CRITICAL)
# Also suppress yfinance's print() to stdout for missing tickers
import contextlib
from typing import Any

import yfinance.utils as _yfu

with contextlib.suppress(Exception):
    _yfu.get_yf_logger().setLevel(_logging.CRITICAL)

import yfinance as yf


def get_current_price(ticker: str) -> float | None:
    """Latest close price. Returns float or None."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d", interval="1d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"price fetch error for {ticker}: {e}")
        return None


# ===== FX CONVERSION LAYER (Phase 1: hardcoded constants, Phase 2: SQLite-cached) =====

# Base currency = user portfolio currency (PEA/TR account)
BASE_CURRENCY = "EUR"

# Ticker suffix -> quote currency mapping
SUFFIX_TO_CURRENCY = {
    ".T": "JPY",      # Tokyo
    ".KS": "KRW",     # Korea (Seoul)
    ".AS": "EUR",     # Amsterdam
    ".PA": "EUR",     # Paris
    ".DE": "EUR",     # Germany
    ".MI": "EUR",     # Milan
    ".L": "GBP",      # London
    ".AX": "AUD",     # Australia
    ".TO": "CAD",     # Toronto
    ".ST": "SEK",     # Stockholm
    ".HK": "HKD",     # Hong Kong
    ".SS": "CNY",     # Shanghai
    ".SZ": "CNY",     # Shenzhen
}

# Hardcoded fx rates to EUR (Phase 1 R3)
# Derived empirically from broker observations 2026-05-16
# JPY/EUR=0.005467 (1 JPY = 0.0055 EUR; 38410 JPY = €210 -> Lasertec catch)
# KRW/EUR=0.000591 (1 KRW = 0.00059 EUR; 1819000 KRW = €1075 -> SK Hynix catch)
# USD/EUR=0.858 (empirically calibrated 2026-05-16 vs broker TSM €347.5, TER €289.7)
# TODO Phase 2 R1: migrate to fx_rates SQLite table + daily refresh cron
HARDCODED_FX_TO_EUR = {
    "EUR": 1.0,
    "JPY": 0.005467,
    "KRW": 0.000591,
    "USD": 0.858,
    "GBP": 1.17,
    "AUD": 0.61,
    "CAD": 0.68,
    "SEK": 0.087,
    "HKD": 0.118,
    "CNY": 0.128,
}


def get_currency_for_ticker(ticker: str) -> str:
    """Infer quote currency from ticker suffix. Defaults to USD (US listing, no suffix)."""
    for suffix, cur in SUFFIX_TO_CURRENCY.items():
        if ticker.endswith(suffix):
            return cur
    return "USD"


def get_fx_rate(from_cur: str, to_cur: str = "EUR") -> float | None:
    """Return fx rate from `from_cur` to `to_cur`.

    Phase 1 (R3): reads HARDCODED_FX_TO_EUR.
    Phase 2 (R1): will read from fx_rates SQLite table with hardcoded fallback.
    """
    if from_cur == to_cur:
        return 1.0
    if to_cur != "EUR":
        # Cross-pair: convert via EUR
        from_eur = HARDCODED_FX_TO_EUR.get(from_cur)
        to_eur = HARDCODED_FX_TO_EUR.get(to_cur)
        if from_eur is None or to_eur is None or to_eur == 0:
            return None
        return from_eur / to_eur
    return HARDCODED_FX_TO_EUR.get(from_cur)


def get_current_price_in_eur(ticker: str) -> float | None:
    """Return current price converted to EUR (user base currency).

    For tickers quoted in foreign currency (.T=JPY, .KS=KRW, etc.),
    converts using cached fx rate. For EUR-native tickers (.AS, .PA, .DE),
    returns price as-is. For USD tickers (no suffix), applies USD/EUR fx.

    Returns None if price fetch or fx conversion fails.
    """
    raw_price = get_current_price(ticker)
    if raw_price is None:
        return None
    cur = get_currency_for_ticker(ticker)
    if cur == BASE_CURRENCY:
        return raw_price
    fx = get_fx_rate(cur, BASE_CURRENCY)
    if fx is None:
        return None
    return raw_price * fx


def get_price_on_date(ticker: str, date: str | datetime) -> tuple[str | None, float | None]:
    """Close price on or after `date` (str YYYY-MM-DD or datetime).
    Falls back to next trading day. Returns (actual_date_str, price) or (None, None).
    """
    if isinstance(date, datetime):
        date_str = date.strftime("%Y-%m-%d")
        target = date
    else:
        date_str = str(date)[:10]
        try:
            target = datetime.fromisoformat(date_str)
        except Exception:
            return (None, None)

    end = (target + timedelta(days=10)).strftime("%Y-%m-%d")
    try:
        t = yf.Ticker(ticker)
        hist = t.history(start=date_str, end=end, interval="1d")
        if hist.empty:
            return (None, None)
        first = hist.iloc[0]
        actual = first.name.strftime("%Y-%m-%d")
        return (actual, float(first["Close"]))
    except Exception as e:
        print(f"price fetch error for {ticker} @ {date_str}: {e}")
        return (None, None)


def get_returns(ticker: str, baseline_date: str, current_date: str | None = None) -> dict[str, Any]:
    """Return between baseline_date and current_date (default now)."""
    b_actual, b_price = get_price_on_date(ticker, baseline_date)
    if b_price is None:
        return {"error": f"no baseline price for {ticker} @ {baseline_date}"}
    c_actual: str | None
    if current_date is None:
        c_price = get_current_price(ticker)
        c_actual = datetime.now().strftime("%Y-%m-%d")
    else:
        c_actual, c_price = get_price_on_date(ticker, current_date)
    if c_price is None:
        return {"error": f"no current price for {ticker}"}
    return {
        "ticker": ticker,
        "baseline_date": b_actual,
        "baseline_price": b_price,
        "current_date": c_actual,
        "current_price": c_price,
        "return_pct": (c_price - b_price) / b_price,
    }


if __name__ == "__main__":
    print("Test get_current_price(NVDA):")
    p = get_current_price("NVDA")
    print(f"  current = ${p:.2f}" if p else "  FAILED")

    print("Test get_price_on_date(NVDA, 2026-04-11):")
    d, p = get_price_on_date("NVDA", "2026-04-11")
    print(f"  {d} = ${p:.2f}" if p else "  FAILED")

    print("Test get_returns(NVDA, 2026-02-11):")
    r = get_returns("NVDA", "2026-02-11")
    if "error" in r:
        print(f"  ERROR: {r['error']}")
    else:
        print(
            f"  {r['ticker']}: {r['baseline_date']} ${r['baseline_price']:.2f} -> {r['current_date']} ${r['current_price']:.2f} = {r['return_pct']:+.1%}"
        )


def get_price_window(ticker: str, start_date: str | datetime, end_date: str | datetime) -> Any:  # pd.DataFrame | None
    """Phase A4 — Daily closes between start and end (inclusive).
    Returns list of (date_str_YYYYMMDD, close_float). Empty list on failure.
    """
    if isinstance(start_date, datetime):
        start_str = start_date.strftime("%Y-%m-%d")
    else:
        start_str = str(start_date)[:10]
    if isinstance(end_date, datetime):
        end_str = end_date.strftime("%Y-%m-%d")
    else:
        end_str = str(end_date)[:10]
    try:
        t = yf.Ticker(ticker)
        hist = t.history(start=start_str, end=end_str, interval="1d")
        if hist.empty:
            return []
        return [(d.strftime("%Y-%m-%d"), float(c)) for d, c in hist["Close"].items()]
    except Exception as e:
        print(f"price window error for {ticker}: {e}")
        return []
