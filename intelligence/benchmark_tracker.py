"""Benchmark tracking : portfolio EUR return vs SMH/SPY/QQQ over rolling windows.

Tier 2 #5 wiring (26/06/2026) post red-teams critique « no benchmark explicit ».
Surface unique pour bandeau Monitors live + Cerebro accordion + Telegram digest.

Choice (Olivier 26/06) : 3 benchmarks tracked simultanément :
- **SMH** (semi ETF) : test le plus dur, book 70% AI-compute
- **SPY** (broad market) : sanity check macro
- **QQQ** (Nasdaq tech) : middle ground

Math :
- portfolio_return = (value_today - value_T_start) / value_T_start
  via portfolio_snapshots.total_value_eur
- benchmark_return (EUR-equivalent) = (price_today / EURUSD_today) /
                                       (price_T_start / EURUSD_T_start) - 1
  via shared.prices canonical helpers (USD assets, EUR investor view)
- delta_pp = (portfolio_return - benchmark_return) * 100

Status logic per benchmark :
- GREEN : delta > -5pp (battant ou dans 5pp)
- YELLOW : delta -5pp..-10pp (sous-perf modérée)
- RED : delta < -10pp (sous-perf significative)

Insufficient si :
- < window_days de snapshots disponibles
- yfinance fetch fail pour le benchmark
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

log = logging.getLogger(__name__)

BENCHMARKS: tuple[str, ...] = ("SMH", "SPY", "QQQ")
DEFAULT_WINDOWS: tuple[int, ...] = (30, 90)


def _get_portfolio_snapshot_on_or_before(conn, target_date: str) -> dict | None:
    """Snapshot le plus récent <= target_date (handle weekends gracefully)."""
    row = conn.execute(
        "SELECT snapshot_date, total_value_eur FROM portfolio_snapshots "
        "WHERE snapshot_date <= ? ORDER BY snapshot_date DESC LIMIT 1",
        (target_date,),
    ).fetchone()
    if not row:
        return None
    return {"date": row[0], "value_eur": float(row[1])}


def _benchmark_return_eur(ticker: str, days: int) -> float | None:
    """Return EUR-equivalent du benchmark sur 'days' (USD asset, EUR investor)."""
    try:
        from shared.portfolio_metrics import fetch_benchmark_return_eur
        return fetch_benchmark_return_eur(ticker, days)
    except Exception as e:
        log.debug("benchmark fetch %s %dj fail: %s", ticker, days, e)
        return None


def compute_benchmarks(window_days: int = 30) -> dict[str, Any]:
    """Compute portfolio vs 3 benchmarks pour une fenêtre donnée.

    Returns :
        {
            'ok': bool,
            'window_days': int,
            'start_date': str | None,
            'portfolio_start_eur': float | None,
            'portfolio_end_eur': float | None,
            'portfolio_return_pct': float | None,
            'benchmarks': {
                'SMH': {'return_pct': float, 'delta_pp': float, 'status': 'green'|'yellow'|'red'} | None,
                'SPY': {...},
                'QQQ': {...},
            },
            'reason': str (debug),
        }
    """
    from shared import storage

    out: dict[str, Any] = {
        "ok": False,
        "window_days": window_days,
        "start_date": None,
        "portfolio_start_eur": None,
        "portfolio_end_eur": None,
        "portfolio_return_pct": None,
        "benchmarks": dict.fromkeys(BENCHMARKS),
        "reason": "",
    }

    today = date.today()
    target_start = (today - timedelta(days=window_days)).isoformat()
    target_end = today.isoformat()

    try:
        with storage.db() as conn:
            snap_start = _get_portfolio_snapshot_on_or_before(conn, target_start)
            snap_end = _get_portfolio_snapshot_on_or_before(conn, target_end)
    except Exception as e:
        out["reason"] = f"db err: {e}"
        return out

    if not snap_start or not snap_end:
        out["reason"] = "no snapshots for window"
        return out

    if snap_start["value_eur"] <= 0:
        out["reason"] = f"snap_start value <= 0 ({snap_start['value_eur']})"
        return out

    # Si snap_start est trop ancien (>window+grace), data insuffisante
    grace_days = 7
    snap_start_date = date.fromisoformat(snap_start["date"])
    snap_age = (today - snap_start_date).days
    if snap_age > window_days + grace_days:
        out["reason"] = f"start snap too old: {snap_age}d vs window {window_days}d (+ {grace_days}d grace)"
        return out

    # NB : portfolio_return_pct est en % (déjà *100). _benchmark_return_eur de
    # shared/portfolio_metrics.py retourne aussi en % (déjà *100). On compare en %.
    portfolio_return_pct = (snap_end["value_eur"] - snap_start["value_eur"]) / snap_start["value_eur"] * 100
    out["start_date"] = snap_start["date"]
    out["portfolio_start_eur"] = snap_start["value_eur"]
    out["portfolio_end_eur"] = snap_end["value_eur"]
    out["portfolio_return_pct"] = portfolio_return_pct

    # Fetch benchmark returns (EUR-equivalent, déjà en %)
    for tk in BENCHMARKS:
        bench_ret_pct = _benchmark_return_eur(tk, window_days)
        if bench_ret_pct is None:
            out["benchmarks"][tk] = None
            continue
        delta_pp = portfolio_return_pct - bench_ret_pct
        if delta_pp >= -5:
            status = "green"
        elif delta_pp >= -10:
            status = "yellow"
        else:
            status = "red"
        out["benchmarks"][tk] = {
            "return_pct": bench_ret_pct,
            "delta_pp": delta_pp,
            "status": status,
        }

    # ok si au moins 1 benchmark fetché
    out["ok"] = any(v is not None for v in out["benchmarks"].values())
    if not out["ok"]:
        out["reason"] = "all benchmark fetches failed"
    return out


def get_benchmarks_summary() -> dict[str, Any]:
    """Compute pour 30d + 90d windows, retourne struct user-display.

    Pour bandeau Overview : on prend le 30d delta SMH (primary).
    Pour Cerebro accordion : on affiche les 2 windows × 3 benchmarks.
    """
    return {
        "w30": compute_benchmarks(30),
        "w90": compute_benchmarks(90),
    }
