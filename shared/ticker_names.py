"""Ticker -> common name resolver with DB cache.

Lifecycle:
- First call for a ticker: fetch yfinance shortName + cache in DB
- Subsequent calls: served from cache (no latency)
- Names don't change so no refresh logic needed (manual refresh if needed)

Usage:
    from shared.ticker_names import get_short_name
    name = get_short_name("7011.T")  # -> "MITSUBISHI HEAVY INDUSTRIES"
"""
from __future__ import annotations

import logging
import sqlite3
from typing import cast

from shared import storage

log = logging.getLogger("bot")


def get_short_name(ticker: str) -> str | None:
    """Return cached short name or fetch yfinance + cache."""
    if not ticker:
        return None
    ticker = ticker.upper().strip()

    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT short_name FROM ticker_names WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        if row and row["short_name"]:
            return cast(str | None, row["short_name"])
    except Exception as e:
        log.warning(f"ticker_names cache read failed for {ticker}: {e}")
    finally:
        conn.close()

    # Cache miss: fetch yfinance
    short_name = None
    long_name = None
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        short_name = info.get("shortName")
        long_name = info.get("longName")
    except Exception as e:
        log.warning(f"yfinance fetch failed for {ticker}: {e}")
        return None

    if not short_name:
        return None

    # Persist (even partial)
    try:
        conn = sqlite3.connect(storage._DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO ticker_names (ticker, short_name, long_name) "
            "VALUES (?, ?, ?)",
            (ticker, short_name, long_name),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"ticker_names cache write failed for {ticker}: {e}")

    return cast(str | None, short_name)


def get_short_names_bulk(tickers: list[str]) -> dict[str, str]:
    """Bulk-resolve N tickers. Returns dict ticker -> short_name (or empty for misses)."""
    result = {}
    for tk in tickers:
        name = get_short_name(tk)
        if name:
            result[tk] = name
    return result
