"""Journal audit handler — KPI #5 alignment between material signals and decisions.

PHILOSOPHY tie: "Tout output non instrumenté est gaspille."

Threshold canonique aligned on intelligence/digest.py:318 (impact_magnitude >= 2.0
canonical, default 3.0 for audit to focus on high-signal-density tickers).

This handler is read-only. Zero touch to measurement pipeline.

Methodology:
1. Fetch all signals with impact_magnitude >= min_impact within window_days
2. Parse entities JSON (list of ticker strings) per signal
3. Aggregate by ticker: signal_count + last_signal_date
4. Cross-reference with decisions table same window
5. Flag tickers with N signals but ZERO decision = silent gap

Limitations (acknowledged):
- Not every high-impact signal warrants a decision (many narrative-level)
- "Silent gap" is informational, not a violation per se
- Ratio at portfolio level not meaningful without normalization

This handler exposes the DATA. Interpretation is the user's job.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from bot.handlers._common import db_path

__all__ = ["cmd_journal_audit"]

log = logging.getLogger("bot")


def _extract_tickers(entities_json: str | None) -> list[str]:
    """Parse signals.entities JSON; return list of ticker strings (UPPERCASE, 2-6 chars)."""
    if not entities_json:
        return []
    try:
        data = json.loads(entities_json)
    except json.JSONDecodeError, ValueError:
        return []
    tickers: list[str] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str) and item.isupper() and 2 <= len(item) <= 6:
                tickers.append(item)
            elif isinstance(item, dict):
                t = item.get("ticker") or item.get("symbol")
                if isinstance(t, str) and t.isupper() and 2 <= len(t) <= 6:
                    tickers.append(t)
    elif isinstance(data, dict):
        for t in data.get("tickers") or []:
            if isinstance(t, str) and t.isupper() and 2 <= len(t) <= 6:
                tickers.append(t)
    return tickers


def _compute_audit(window_days: int, min_impact: float) -> dict:
    """Compute the audit data structure. Pure function, testable.

    Returns:
        {
            "window_days": int,
            "min_impact": float,
            "total_signals": int,
            "total_decisions": int,
            "ticker_signal_counts": dict[ticker, count],
            "ticker_last_signal": dict[ticker, ISO date],
            "ticker_decision_counts": dict[ticker, count],
            "tickers_silent": list[(ticker, count, last_date)] sorted by count DESC,
            "tickers_tracked": list[(ticker, sig_count, dec_count)],
        }
    """
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    try:
        sig_rows = conn.execute(
            """
            SELECT id, timestamp, entities, impact_magnitude
            FROM signals
            WHERE impact_magnitude >= ?
              AND timestamp >= datetime('now', ?)
              AND entities IS NOT NULL AND entities != ''
            ORDER BY timestamp DESC
            """,
            (min_impact, f"-{window_days} days"),
        ).fetchall()

        dec_rows = conn.execute(
            """
            SELECT ticker, COUNT(*) AS n
            FROM decisions
            WHERE created_at >= datetime('now', ?)
            GROUP BY ticker
            """,
            (f"-{window_days} days",),
        ).fetchall()
    finally:
        conn.close()

    ticker_signal_counts: dict[str, int] = {}
    ticker_last_signal: dict[str, str] = {}
    for row in sig_rows:
        tickers = _extract_tickers(row["entities"])
        ts = row["timestamp"]
        for t in tickers:
            ticker_signal_counts[t] = ticker_signal_counts.get(t, 0) + 1
            if t not in ticker_last_signal or ts > ticker_last_signal[t]:
                ticker_last_signal[t] = ts

    ticker_decision_counts: dict[str, int] = {r["ticker"]: r["n"] for r in dec_rows}
    total_decisions = sum(ticker_decision_counts.values())

    tickers_silent = [
        (t, c, ticker_last_signal.get(t, "?")[:10])
        for t, c in ticker_signal_counts.items()
        if t not in ticker_decision_counts
    ]
    tickers_silent.sort(key=lambda x: -x[1])

    tickers_tracked = [(t, ticker_signal_counts.get(t, 0), c) for t, c in ticker_decision_counts.items()]
    tickers_tracked.sort(key=lambda x: -x[2])

    return {
        "window_days": window_days,
        "min_impact": min_impact,
        "total_signals": len(sig_rows),
        "total_decisions": total_decisions,
        "ticker_signal_counts": ticker_signal_counts,
        "ticker_last_signal": ticker_last_signal,
        "ticker_decision_counts": ticker_decision_counts,
        "tickers_silent": tickers_silent,
        "tickers_tracked": tickers_tracked,
    }


def _format_audit(data: dict) -> str:
    """Format audit dict into Telegram-friendly Markdown."""
    silent = data["tickers_silent"]
    tracked = data["tickers_tracked"]
    n_tickers = len(data["ticker_signal_counts"])

    lines = ["\U0001f4cb *JOURNAL AUDIT* — KPI #5 alignment"]
    lines.append(f"{data['window_days']}d window | impact_magnitude \u2265 {data['min_impact']:.1f}")
    lines.append("")
    lines.append(f"High-impact signals : {data['total_signals']}")
    lines.append(f"Decisions logged    : {data['total_decisions']}")
    lines.append(f"Tickers w/ signals  : {n_tickers}")
    lines.append(f"Tickers w/ decision : {len(tracked)}")
    lines.append(f"Silent tickers      : {len(silent)}")

    if tracked:
        lines.append("")
        lines.append("*Tracked (signal + decision):*")
        for ticker, sig_n, dec_n in tracked[:10]:
            lines.append(f"  \u2705 {ticker:8s} {sig_n:>3d} sig / {dec_n:>2d} dec")

    if silent:
        lines.append("")
        lines.append(f"*Silent tickers (top {min(10, len(silent))} by signal count):*")
        for ticker, sig_n, last_date in silent[:10]:
            lines.append(f"  \u26a0\ufe0f {ticker:8s} {sig_n:>3d} sig | last {last_date}")

    lines.append("")
    lines.append("_Note: not all high-impact signals warrant decisions._")
    lines.append("_This audit shows DATA. Interpretation is yours._")

    return "\n".join(lines)


async def cmd_journal_audit(update, ctx):  # noqa: ARG001
    """Show alignment between material signals and decisions logged.

    Usage: /journal_audit [window_days] [min_impact]
    Defaults: 30 days, impact_magnitude >= 3.0
    """
    parts = update.message.text.split()
    try:
        window_days = int(parts[1]) if len(parts) > 1 else 30
        min_impact = float(parts[2]) if len(parts) > 2 else 3.0
    except ValueError, IndexError:
        await update.message.reply_text(
            "Usage: /journal_audit [window_days] [min_impact]\nDefaults: 30 days, impact 3.0"
        )
        return

    if window_days <= 0 or window_days > 365:
        await update.message.reply_text("window_days must be 1-365")
        return
    if min_impact < 0 or min_impact > 5:
        await update.message.reply_text("min_impact must be 0.0-5.0")
        return

    try:
        data = _compute_audit(window_days, min_impact)
        msg = _format_audit(data)
        if len(msg) > 3900:
            msg = msg[:3900] + "\n[truncated]"
        await update.message.reply_text(msg)
    except Exception as e:
        log.error(f"cmd_journal_audit error: {e}")
        await update.message.reply_text(f"Audit error: {e}")
