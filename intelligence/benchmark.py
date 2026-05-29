"""Sprint 16 — Benchmark SOX (PHLX Semiconductor) alpha vs beta sector.

Per la critique : "Compare ta concentration/tes facteurs a un benchmark
(SOX, ETF semis) : ta surperformance est-elle de l'alpha ou juste du beta
de secteur ?"

Approche deterministe simple :
  1. Fetch historical SOX (^SOX yfinance) sur la fenetre
  2. Compute book daily return weighted (sum of position weights × daily_return)
  3. Compute alpha (excess return) + beta (regression sur SOX) + R^2
  4. Decompose : "+25% vs +8% SOX = +17% alpha sur 6 mois"

Simplification : on prend snapshot prix actuels et entry, sans serie
journaliere. Alpha proxy = book CAGR - SOX CAGR sur la fenetre.
Beta exact necessite serie de prix journaliere (Sprint 17 infra).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

log = logging.getLogger(__name__)


def _get_user_benchmark() -> tuple[str, str]:
    """Sprint 19 : lit user_strategy.benchmark_ticker + fallback."""
    try:
        from pathlib import Path

        import yaml

        cfg = yaml.safe_load(Path("config.yaml").read_text())
        us = cfg.get("user_strategy") or {}
        return (us.get("benchmark_ticker", "SOXX"), us.get("benchmark_fallback", "^SOX"))
    except Exception:
        return ("SOXX", "^SOX")


def fetch_benchmark_return(months: int = 6) -> dict | None:
    """Fetch benchmark % change over window via yfinance.

    Sprint 19 : utilise user_strategy.benchmark_ticker (default SOXX = iShares
    Semiconductor ETF, plus pertinent qu'un large-cap pour un concentrator
    semis). Fallback ^SOX si SOXX indispo.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None
    primary, fallback = _get_user_benchmark()
    for ticker in (primary, fallback):
        try:
            from datetime import timedelta

            end = datetime.now(UTC)
            start = end - timedelta(days=months * 30)
            t = yf.Ticker(ticker)
            hist = t.history(start=start, end=end)
            if hist is None or hist.empty:
                continue
            first = float(hist["Close"].iloc[0])
            last = float(hist["Close"].iloc[-1])
            pct = (last - first) / first * 100 if first else 0
            return {
                "ticker": ticker,
                "months": months,
                "start_date": str(hist.index[0])[:10],
                "end_date": str(hist.index[-1])[:10],
                "start_price": round(first, 2),
                "end_price": round(last, 2),
                "return_pct": round(pct, 1),
            }
        except Exception as e:
            log.warning(f"fetch_benchmark_return {ticker} failed: {e}")
            continue
    return None


def compute_book_return_proxy() -> dict:
    """Approximate book return : weighted (current - cost) / cost per position."""
    from dashboard.render import _cached_price_eur, _positions

    positions = _positions()
    book_value = 0.0
    invested = 0.0
    n_valid = 0
    for p in positions:
        ac = p.get("avg_cost", 0) or 0
        w = p.get("weight", 0) or 0  # = qty * avg_cost (cost basis eur)
        if not ac or not w:
            continue
        qty = w / ac
        cur = _cached_price_eur(p["ticker"]) or ac
        book_value += qty * cur
        invested += w
        n_valid += 1
    if not invested:
        return {}
    return_pct = (book_value - invested) / invested * 100
    return {
        "invested_eur": round(invested, 0),
        "current_value_eur": round(book_value, 0),
        "return_pct": round(return_pct, 1),
        "n_positions": n_valid,
    }


def _median_position_age_days() -> int:
    """Median age of held positions (from positions.opened_at proxy)."""
    try:
        from shared.storage import db

        with db() as cx:
            rows = cx.execute(
                "SELECT julianday('now') - julianday(opened_at) "
                "FROM positions WHERE qty > 0 AND status='open' AND opened_at IS NOT NULL"
            ).fetchall()
        ages = sorted([int(r[0]) for r in rows if r[0]])
        if not ages:
            return 0
        mid = len(ages) // 2
        return ages[mid] if len(ages) % 2 else (ages[mid - 1] + ages[mid]) // 2
    except Exception:
        return 0


def compute_alpha_vs_sox(months: int = 6) -> dict:
    """alpha = book_return - SOX_return sur la meme fenetre.

    Guard : si l'age median des positions < 60j, l'alpha est meaningless
    (fenetre SOX > age positions). On rapporte alors avec warning et on
    raccourcit la fenetre.
    """
    median_age = _median_position_age_days()
    if median_age > 0 and median_age < months * 30:
        adjusted_months = max(1, median_age // 30)
        bench = fetch_benchmark_return(months=adjusted_months)
        if bench:
            book = compute_book_return_proxy()
            if book:
                alpha = book["return_pct"] - bench["return_pct"]
                return {
                    "months": adjusted_months,
                    "median_position_age_days": median_age,
                    "book_return_pct": book["return_pct"],
                    "bench_return_pct": bench["return_pct"],
                    "bench_ticker": bench["ticker"],
                    "alpha_pct": round(alpha, 1),
                    "bench_window": f"{bench['start_date']} → {bench['end_date']}",
                    "warning": f"fenetre ajustee a {adjusted_months}m (age median {median_age}j)",
                    "interpretation": (
                        f"+{alpha:.1f}% alpha sur {adjusted_months}m (ajuste age book)"
                        if alpha > 0 else
                        f"{alpha:.1f}% sous-performance vs SOX sur {adjusted_months}m (ajuste)"
                    ),
                }
    bench = fetch_benchmark_return(months=months)
    book = compute_book_return_proxy()
    if not bench or not book:
        return {"error": "no_data", "bench": bench, "book": book}
    alpha = book["return_pct"] - bench["return_pct"]
    return {
        "months": months,
        "median_position_age_days": median_age,
        "book_return_pct": book["return_pct"],
        "bench_return_pct": bench["return_pct"],
        "bench_ticker": bench["ticker"],
        "alpha_pct": round(alpha, 1),
        "bench_window": f"{bench['start_date']} → {bench['end_date']}",
        "interpretation": (
            f"+{alpha:.1f}% alpha sur {months}m" if alpha > 0
            else f"{alpha:.1f}% sous-performance vs SOX sur {months}m"
        ),
    }
