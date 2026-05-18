"""
Daily insider digest : refresh top tickers, snapshot net flows, alert on shifts.
Cron-driven (6h Paris). Output formatted for Telegram.
"""

import logging
from datetime import date, timedelta

from shared import edgar
from shared.storage import db

# Alert thresholds (USD millions)
DELTA_1D_THRESHOLD = 30.0  # Δnet between today and prior snapshot
DELTA_7D_THRESHOLD = 75.0  # Δnet over 7 days
BIG_NET_THRESHOLD = 100.0  # absolute net flow >$100M (any direction)

log = logging.getLogger(__name__)


def _ensure_table(cx) -> None:
    cx.execute("""
        CREATE TABLE IF NOT EXISTS insider_snapshots (
            ticker TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            net_m REAL,
            n_buys INTEGER,
            n_sells INTEGER,
            total_buys_m REAL,
            total_sells_m REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ticker, snapshot_date)
        )
    """)
    cx.execute("CREATE INDEX IF NOT EXISTS idx_insider_snap_ticker ON insider_snapshots(ticker, snapshot_date DESC)")


def _prev_snapshot(cx, ticker: str, before_date: str) -> dict | None:
    r = cx.execute(
        "SELECT snapshot_date, net_m FROM insider_snapshots "
        "WHERE ticker=? AND snapshot_date < ? "
        "ORDER BY snapshot_date DESC LIMIT 1",
        (ticker, before_date),
    ).fetchone()
    return {"date": r["snapshot_date"], "net_m": r["net_m"]} if r else None


def _snapshot_at_or_before(cx, ticker: str, target_date: str) -> dict | None:
    r = cx.execute(
        "SELECT snapshot_date, net_m FROM insider_snapshots "
        "WHERE ticker=? AND snapshot_date <= ? "
        "ORDER BY snapshot_date DESC LIMIT 1",
        (ticker, target_date),
    ).fetchone()
    return {"date": r["snapshot_date"], "net_m": r["net_m"]} if r else None


def daily_insider_refresh() -> dict:
    """Force-refresh top tickers, snapshot, compute deltas, return alerts payload."""
    # Lazy import to avoid circular
    from intelligence.digest import INSIDER_TOP_TICKERS

    today = date.today().isoformat()
    j7 = (date.today() - timedelta(days=7)).isoformat()

    refreshed = 0
    failed = []
    alerts = []
    big_positions = []  # for context : absolute heavy zones

    with db() as cx:
        _ensure_table(cx)

        for ticker in INSIDER_TOP_TICKERS:
            try:
                # Bypass cache : ttl_hours=0 → cache always stale → fresh fetch
                brief = edgar.get_insider_brief(ticker, ttl_hours=0)
                if not brief:
                    failed.append(ticker)
                    continue

                net = brief.get("net_m", 0.0) or 0.0
                cx.execute(
                    """
                    INSERT OR REPLACE INTO insider_snapshots
                    (ticker, snapshot_date, net_m, n_buys, n_sells, total_buys_m, total_sells_m)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        ticker,
                        today,
                        net,
                        brief.get("n_buys", 0),
                        brief.get("n_sells", 0),
                        brief.get("total_buys_m", 0.0) or 0.0,
                        brief.get("total_sells_m", 0.0) or 0.0,
                    ),
                )
                refreshed += 1

                # Compute deltas
                prev = _prev_snapshot(cx, ticker, today)
                snap7 = _snapshot_at_or_before(cx, ticker, j7)

                d1 = (net - prev["net_m"]) if prev else None
                d7 = (net - snap7["net_m"]) if snap7 and snap7["date"] != today else None

                # Alert if 1d delta exceeds threshold
                if d1 is not None and abs(d1) >= DELTA_1D_THRESHOLD:
                    assert prev is not None
                    alerts.append(
                        {
                            "ticker": ticker,
                            "kind": "1d",
                            "delta_m": d1,
                            "now_m": net,
                            "prev_date": prev["date"],
                        }
                    )
                # Alert if 7d delta exceeds threshold
                if d7 is not None and abs(d7) >= DELTA_7D_THRESHOLD:
                    assert snap7 is not None
                    alerts.append(
                        {
                            "ticker": ticker,
                            "kind": "7d",
                            "delta_m": d7,
                            "now_m": net,
                            "prev_date": snap7["date"],
                        }
                    )

                # Big absolute positions (context, not alert)
                if abs(net) >= BIG_NET_THRESHOLD:
                    big_positions.append(
                        {
                            "ticker": ticker,
                            "net_m": net,
                            "n_buys": brief.get("n_buys", 0),
                            "n_sells": brief.get("n_sells", 0),
                        }
                    )

            except Exception as e:
                log.warning(f"insider_refresh {ticker} failed: {e}")
                failed.append(ticker)

        cx.commit()

    return {
        "date": today,
        "refreshed": refreshed,
        "failed": failed,
        "alerts": alerts,
        "big_positions": sorted(big_positions, key=lambda x: x["net_m"]),
    }


def format_daily_insider_digest(r: dict) -> str:
    if not r:
        return "(no data)"
    lines = [f"📋 *Daily Insider Digest* — {r['date']}"]
    lines.append(
        f"Refreshed: {r['refreshed']} tickers" + (f" | failed: {','.join(r['failed'])}" if r["failed"] else "")
    )
    lines.append("")

    if r["alerts"]:
        lines.append("🚨 *Flow shifts*")
        for a in sorted(r["alerts"], key=lambda x: x["delta_m"]):
            arrow = "⬇" if a["delta_m"] < 0 else "⬆"
            sign = "dump" if a["delta_m"] < 0 else "accumulation"
            lines.append(
                f"  {arrow} {a['ticker']:6s} {a['kind']} {sign}: "
                f"Δ={a['delta_m']:+.0f}M (vs {a['prev_date']}) → now ${a['now_m']:+.0f}M"
            )
        lines.append("")
    else:
        lines.append("No flow shifts above threshold today.")
        lines.append("")

    if r["big_positions"]:
        lines.append("📊 *Heavy positions (absolute)*")
        for p in r["big_positions"][:8]:
            lines.append(f"  {p['ticker']:6s} ${p['net_m']:+.0f}M ({p['n_buys']}B/{p['n_sells']}S)")

    return "\n".join(lines)
