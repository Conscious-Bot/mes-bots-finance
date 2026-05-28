"""Signal drilldown handler — show all signals mentioning a ticker.

Read-only. Companion to /journal_audit: when /journal_audit shows a silent
ticker, use /signal_drilldown TICKER to see WHAT signals were ingested
and ignored.

Output per signal:
- Date, impact_magnitude, reversibility, time_to_realization
- Source name + credibility
- Title (truncated)
- Reasoning from materiality_breakdown (LLM rationale)

Then top sources for this ticker + decisions count.

Zero touch to measurement pipeline. Pure SQL + JSON parsing.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from bot.handlers._common import db_path

__all__ = ["cmd_signal_drilldown"]

log = logging.getLogger("bot")


def _parse_breakdown(breakdown_json: str | None) -> dict:
    """Parse materiality_breakdown JSON. Returns {} if invalid."""
    if not breakdown_json:
        return {}
    try:
        data = json.loads(breakdown_json)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError, ValueError:
        return {}


def _ticker_in_entities(entities_json: str | None, ticker: str) -> bool:
    """Check if ticker appears in entities list (UPPERCASE string match)."""
    if not entities_json:
        return False
    try:
        data = json.loads(entities_json)
        if isinstance(data, list):
            return ticker in data
        if isinstance(data, dict):
            tickers = data.get("tickers") or []
            return ticker in tickers
    except json.JSONDecodeError, ValueError:
        return False
    return False


def _compute_drilldown(ticker: str, window_days: int, min_impact: float) -> dict:
    """Fetch all signals 30d mentioning ticker with impact >= min_impact.

    Returns dict with: ticker, window_days, min_impact, signals (list of dicts),
    source_counts (dict), decision_count (int).
    """
    ticker = ticker.upper()
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT s.id, s.timestamp, s.title, s.summary, s.signal_type,
                   s.impact_magnitude, s.reversibility, s.time_to_realization,
                   s.materiality_breakdown, s.materiality_boost,
                   s.entities,
                   src.name AS source_name, src.credibility AS source_cred
            FROM signals s
            LEFT JOIN sources src ON s.source_id = src.id
            WHERE s.impact_magnitude >= ?
              AND s.timestamp >= datetime('now', ?)
              AND s.entities IS NOT NULL AND s.entities != ''
            ORDER BY s.timestamp DESC
            """,
            (min_impact, f"-{window_days} days"),
        ).fetchall()

        dec_count = conn.execute(
            """SELECT COUNT(*) FROM decisions
               WHERE ticker = ? AND created_at >= datetime('now', ?)""",
            (ticker, f"-{window_days} days"),
        ).fetchone()[0]
    finally:
        conn.close()

    signals: list[dict] = []
    source_counts: dict[str, int] = {}

    for row in rows:
        if not _ticker_in_entities(row["entities"], ticker):
            continue
        breakdown = _parse_breakdown(row["materiality_breakdown"])
        source_name = (row["source_name"] or "?").split("<")[0].strip()[:30]
        signals.append(
            {
                "id": row["id"],
                "date": row["timestamp"][:10],
                "title": (row["title"] or "")[:80],
                "impact": row["impact_magnitude"],
                "reversibility": row["reversibility"],
                "time": row["time_to_realization"],
                "signal_type": row["signal_type"],
                "source": source_name,
                "source_cred": row["source_cred"],
                "boost": row["materiality_boost"] or 1.0,
                "reasoning": (breakdown.get("reasoning") or "")[:200],
            }
        )
        source_counts[source_name] = source_counts.get(source_name, 0) + 1

    return {
        "ticker": ticker,
        "window_days": window_days,
        "min_impact": min_impact,
        "signals": signals,
        "source_counts": source_counts,
        "decision_count": dec_count,
    }


def _format_drilldown(data: dict) -> str:
    """Format drilldown dict into Telegram plain text."""
    sigs = data["signals"]
    if not sigs:
        return (
            f"🔍 SIGNAL DRILLDOWN — {data['ticker']}\n"
            f"{data['window_days']}d window | impact >= {data['min_impact']:.1f}\n\n"
            f"No matching signals.\n"
            f"Decisions logged: {data['decision_count']}"
        )

    lines = [
        f"🔍 SIGNAL DRILLDOWN — {data['ticker']}",
        f"{data['window_days']}d window | impact >= {data['min_impact']:.1f} | {len(sigs)} matched",
        "",
    ]

    # Show up to 8 signals (Telegram length limit consideration)
    for s in sigs[:8]:
        cred = f"{s['source_cred']:.2f}" if s.get("source_cred") is not None else "?"
        lines.append(f"[{s['date']}] impact={s['impact']:.1f} rev={s['reversibility']:.1f} {s['signal_type'] or '?'}")
        lines.append(f"  Source: {s['source']} (cred {cred})")
        lines.append(f"  Title : {s['title']}")
        if s["reasoning"]:
            lines.append(f"  Why   : {s['reasoning']}")
        lines.append("")

    if len(sigs) > 8:
        lines.append(f"... +{len(sigs) - 8} more signals not shown")
        lines.append("")

    if data["source_counts"]:
        lines.append(f"Top sources ({data['window_days']}d):")
        sorted_srcs = sorted(data["source_counts"].items(), key=lambda x: -x[1])
        for name, n in sorted_srcs[:6]:
            lines.append(f"  {name:30s}: {n}")
        lines.append("")

    lines.append(f"Decisions logged for {data['ticker']} ({data['window_days']}d): {data['decision_count']}")

    return "\n".join(lines)


async def cmd_signal_drilldown(update, ctx):  # noqa: ARG001
    """Drill into all signals mentioning a specific ticker.

    Usage: /signal_drilldown TICKER [window_days] [min_impact]
    Defaults: 30 days, impact >= 2.0 (broader than /journal_audit to expose more)
    """
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "Usage: /signal_drilldown TICKER [window_days] [min_impact]\nDefaults: 30 days, impact >= 2.0"
        )
        return

    ticker = parts[1].upper()
    try:
        window_days = int(parts[2]) if len(parts) > 2 else 30
        min_impact = float(parts[3]) if len(parts) > 3 else 2.0
    except ValueError, IndexError:
        await update.message.reply_text("Bad args. Usage: /signal_drilldown TICKER [days] [min_impact]")
        return

    if window_days <= 0 or window_days > 365:
        await update.message.reply_text("window_days must be 1-365")
        return
    if min_impact < 0 or min_impact > 5:
        await update.message.reply_text("min_impact must be 0.0-5.0")
        return

    try:
        data = _compute_drilldown(ticker, window_days, min_impact)
        msg = _format_drilldown(data)
        if len(msg) > 3900:
            msg = msg[:3900] + "\n[truncated]"
        await update.message.reply_text(msg)
    except Exception as e:
        log.error(f"cmd_signal_drilldown error: {e}")
        await update.message.reply_text(f"Drilldown error: {e}")
