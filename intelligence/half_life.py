"""Phase A4 — Information Half-Life per source.

For each signal with extracted tickers, measure forward window delay
between signal timestamp and first day where ticker move >= threshold.
Aggregate per source as median (in days).

Use case: signals from short-half-life sources decay urgency fast,
long-half-life sources retain actionability over days/weeks.
"""

import json
import logging
import statistics
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.05
DEFAULT_MAX_DAYS = 30
DEFAULT_MIN_SAMPLES = 3


def _parse_tickers(entities_json):
    if not entities_json:
        return []
    try:
        v = json.loads(entities_json) if isinstance(entities_json, str) else entities_json
        if isinstance(v, list):
            return [str(t).upper() for t in v if t]
    except Exception:
        pass
    return []


def compute_signal_time_to_move(signal, threshold=DEFAULT_THRESHOLD, max_days=DEFAULT_MAX_DAYS):
    """Days-until-significant-move on signal's primary ticker.
    Returns dict {ticker, days, return_pct, ...} or None.
    """
    from shared import prices

    tickers = _parse_tickers(signal.get("entities"))
    if not tickers:
        return None
    ticker = tickers[0]
    sig_ts = signal.get("timestamp")
    if not sig_ts:
        return None
    try:
        sig_dt = datetime.fromisoformat(sig_ts.replace("Z", "+00:00"))
    except Exception:
        return None

    now_utc = datetime.now(UTC)
    if (now_utc - sig_dt).days < 1:
        return None

    _baseline_date_str, baseline_price = prices.get_price_on_date(ticker, sig_dt)
    if not baseline_price:
        return None

    end_dt = sig_dt + timedelta(days=max_days)
    if end_dt > now_utc:
        end_dt = now_utc
    window = prices.get_price_window(ticker, sig_dt + timedelta(days=1), end_dt)
    if not window:
        return None

    for date_str, close in window:
        ret = (close - baseline_price) / baseline_price
        if abs(ret) >= threshold:
            try:
                hit_dt = datetime.fromisoformat(date_str).replace(tzinfo=sig_dt.tzinfo)
                days_delta = max(1, (hit_dt - sig_dt).days)
            except Exception:
                continue
            return {
                "ticker": ticker,
                "days": days_delta,
                "return_pct": ret,
                "baseline_price": baseline_price,
                "hit_price": close,
                "hit_date": date_str,
            }
    return None


def compute_source_half_life(source_id, min_samples=DEFAULT_MIN_SAMPLES):
    """Median time-to-move across ticker-having signals from source."""
    from shared import storage

    signals = storage.get_signals_by_source_with_tickers(source_id)
    days_list = []
    samples_detail = []
    for sig in signals:
        try:
            result = compute_signal_time_to_move(sig)
            if result is not None:
                days_list.append(result["days"])
                samples_detail.append({**result, "signal_id": sig["id"]})
        except Exception as e:
            log.warning(f"time_to_move failed signal {sig.get('id')}: {e}")

    if len(days_list) < min_samples:
        return {
            "source_id": source_id,
            "n_samples": len(days_list),
            "median_days": None,
            "samples": samples_detail,
            "insufficient": True,
        }
    return {
        "source_id": source_id,
        "n_samples": len(days_list),
        "median_days": statistics.median(days_list),
        "samples": samples_detail,
    }


def refresh_all_source_half_lives(min_samples=DEFAULT_MIN_SAMPLES):
    """Iterate all sources, compute half-life, persist where n_samples >= min."""
    import sqlite3

    from shared import storage

    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    sources = [dict(r) for r in conn.execute("SELECT id, name FROM sources").fetchall()]
    conn.close()

    results = {}
    for src in sources:
        try:
            r = compute_source_half_life(src["id"], min_samples=min_samples)
            if r:
                if r.get("median_days") is not None:
                    storage.update_source_half_life(src["id"], r["median_days"], r["n_samples"])
                    results[src["name"]] = {
                        "median_days": r["median_days"],
                        "n_samples": r["n_samples"],
                        "persisted": True,
                    }
                else:
                    results[src["name"]] = {
                        "median_days": None,
                        "n_samples": r["n_samples"],
                        "persisted": False,
                        "reason": f"insufficient samples ({r['n_samples']} < {min_samples})",
                    }
        except Exception as e:
            log.exception(f"refresh failed source {src['name']}: {e}")
    return results
