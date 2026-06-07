"""Backfill 5y price_history pour toutes les positions ouvertes (Axe 5 closing).

Spec QUALITY_BAR Axe 5 : "make M1 reel partout". Apres ce script, price_history
contient 5 ans d'historique pour les 26 positions du book -> tous les chantiers
(attribution 2x2, backtest, Performance panel, Brier resolution) tapent DB sans
yfinance live.

Idempotent : ensure_price_history skip si coverage >= 70%. Re-run safe.

Usage : python3 scripts/backfill_price_history_book.py [--years 5]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_book")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5, help="annees backfill (default 5)")
    args = parser.parse_args()

    from shared import storage
    from shared.prices import ensure_price_history

    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=args.years * 365)
    log.info(f"Backfill window {start_dt:%Y-%m-%d} -> {end_dt:%Y-%m-%d}")

    with storage.db() as cx:
        rows = cx.execute(
            "SELECT id, ticker FROM positions "
            "WHERE status='open' AND qty > 0 ORDER BY ticker"
        ).fetchall()

    if not rows:
        log.info("Aucune position ouverte")
        return 0

    log.info(f"Backfill {len(rows)} positions...")
    ok = 0
    failed = 0
    for r in rows:
        ticker = r[1]
        try:
            df = ensure_price_history(ticker, start_dt, end_dt)
            n = len(df) if df is not None else 0
            log.info(f"  {ticker}: {n} obs en DB")
            if n > 0:
                ok += 1
            else:
                failed += 1
        except Exception as e:
            log.warning(f"  {ticker}: FAILED {e}")
            failed += 1

    log.info(f"Done: {ok} ok, {failed} failed")

    # Stats globales price_history
    with storage.db() as cx:
        total = cx.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        tickers = cx.execute(
            "SELECT COUNT(DISTINCT ticker) FROM price_history"
        ).fetchone()[0]
        oldest = cx.execute("SELECT MIN(asof) FROM price_history").fetchone()[0]
        newest = cx.execute("SELECT MAX(asof) FROM price_history").fetchone()[0]
    log.info(
        f"price_history : {total} obs, {tickers} tickers, "
        f"oldest={oldest[:10] if oldest else 'N/A'}, "
        f"newest={newest[:10] if newest else 'N/A'}"
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
