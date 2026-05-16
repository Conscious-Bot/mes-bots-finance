"""Cross-domain ticker aggregator — /find TICKER handler.

Zero-LLM, zero-external-API. Pure SQL read-only.
Aggregates: positions + portfolio_targets + theses + recent signals (7d) +
filings_8k_log (30d) + insider activity (30d).

Use case: instant ticker dump before deep /analyze. Quotidien.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

__all__ = ["cmd_find"]


def _db_path() -> Path:
    """Resolve repo_root/data/bot.db from this module location."""
    return Path(__file__).resolve().parent.parent.parent / "data" / "bot.db"


def _format_position(conn: sqlite3.Connection, ticker: str) -> str:
    rows = conn.execute(
        "SELECT qty, avg_cost, account, status, opened_at "
        "FROM positions WHERE ticker = ? AND status = 'open'",
        (ticker,),
    ).fetchall()
    if not rows:
        return "\U0001F4CC POSITION\n  None\n"
    lines = ["\U0001F4CC POSITION"]
    for qty, avg_cost, account, status, opened_at in rows:
        cost_basis = qty * avg_cost
        lines.append(
            f"  Qty: {qty:.4f} @ \u20AC{avg_cost:.2f}  "
            f"= \u20AC{cost_basis:,.0f} cost basis"
        )
        lines.append(f"  Account: {account}  Opened: {opened_at[:10] if opened_at else '?'}")
    lines.append("")
    return "\n".join(lines)


def _format_target(conn: sqlite3.Connection, ticker: str) -> str:
    rows = conn.execute(
        "SELECT account, target_eur, target_weight_pct, status, phase_week, "
        "narrative, priority, bucket "
        "FROM portfolio_targets WHERE ticker = ?",
        (ticker,),
    ).fetchall()
    if not rows:
        return "\U0001F3AF PORTFOLIO TARGET\n  None\n"
    lines = ["\U0001F3AF PORTFOLIO TARGET"]
    for account, target_eur, weight_pct, status, phase_week, narrative, priority, bucket in rows:
        phase_str = f"W{phase_week}" if phase_week is not None else "—"
        narr_str = f" — {narrative}" if narrative else ""
        prio_str = f" [{priority}]" if priority else ""
        bucket_str = f" ({bucket})" if bucket else ""
        weight_str = f", {weight_pct:.1f}%" if weight_pct else ""
        lines.append(
            f"  {account}{bucket_str}: \u20AC{target_eur:,.0f}{weight_str} "
            f"— {status}{prio_str} (phase {phase_str}){narr_str}"
        )
    lines.append("")
    return "\n".join(lines)


def _format_theses(conn: sqlite3.Connection, ticker: str) -> str:
    rows = conn.execute(
        "SELECT id, conviction, direction, horizon, key_drivers, "
        "invalidation_triggers, status, opened_at, notes "
        "FROM theses WHERE ticker = ? AND status != 'deleted' "
        "ORDER BY opened_at DESC",
        (ticker,),
    ).fetchall()
    if not rows:
        return "\U0001F4C8 THESIS\n  None\n"
    lines = ["\U0001F4C8 THESIS"]
    for tid, conv, direction, horizon, drivers, triggers, status, opened_at, notes in rows:
        opened = opened_at[:10] if opened_at else "?"
        lines.append(
            f"  #{tid} {status} | conv {conv}/5 | {direction} | "
            f"{horizon or '?'} | opened {opened}"
        )
        # Drivers: try JSON list first, fallback to string
        if drivers:
            try:
                drv_list = json.loads(drivers)
                if isinstance(drv_list, list):
                    drv_str = "; ".join(str(d) for d in drv_list[:3])
                else:
                    drv_str = str(drivers)[:120]
            except (json.JSONDecodeError, TypeError):
                drv_str = str(drivers)[:120]
            lines.append(f"    Drivers: {drv_str}")
        if triggers:
            try:
                trg_list = json.loads(triggers)
                if isinstance(trg_list, list):
                    trg_str = " OR ".join(str(t) for t in trg_list[:2])
                else:
                    trg_str = str(triggers)[:120]
            except (json.JSONDecodeError, TypeError):
                trg_str = str(triggers)[:120]
            lines.append(f"    Invalidation: {trg_str}")
        if notes and "sector_thesis_id" in notes:
            # Extract sector_thesis_id from notes
            for line in notes.split("\n"):
                if "sector_thesis_id" in line:
                    lines.append(f"    {line.strip()}")
                    break
    lines.append("")
    return "\n".join(lines)


def _format_signals(conn: sqlite3.Connection, ticker: str, days: int = 7) -> str:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    # JSON list match: entities like \'%"TICKER"%\' covers ["TICKER", ...] and ["X", "TICKER", ...]
    rows = conn.execute(
        "SELECT s.id, substr(s.title, 1, 70) AS title, s.signal_type, "
        "s.impact_magnitude, s.timestamp, src.name AS source_name "
        "FROM signals s LEFT JOIN sources src ON s.source_id = src.id "
        "WHERE s.entities LIKE ? AND s.timestamp >= ? "
        "ORDER BY s.timestamp DESC LIMIT 10",
        (f'%"{ticker}"%', cutoff),
    ).fetchall()
    if not rows:
        return f"\U0001F4F0 SIGNALS ({days}j)\n  None\n"
    lines = [f"\U0001F4F0 SIGNALS ({days}j)"]
    for sid, title, stype, impact, ts, source_name in rows:
        impact_str = f"{impact:.1f}" if impact is not None else "?"
        type_str = stype or "?"
        src_str = (source_name or "?")[:25]
        date_str = ts[:10] if ts else "?"
        lines.append(
            f"  #{sid} [{date_str}] {src_str} | impact {impact_str} | {type_str}"
        )
        lines.append(f"    {title}")
    lines.append("")
    return "\n".join(lines)


def _format_filings(conn: sqlite3.Connection, ticker: str, days: int = 30) -> str:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        rows = conn.execute(
            "SELECT filed_at, item_code, severity, summary "
            "FROM filings_8k_log WHERE ticker = ? AND filed_at >= ? "
            "ORDER BY filed_at DESC LIMIT 5",
            (ticker, cutoff),
        ).fetchall()
    except sqlite3.OperationalError:
        # Column names may differ; try generic
        rows = []
    if not rows:
        return f"\U0001F3DB 8-K FILINGS ({days}j)\n  None\n"
    lines = [f"\U0001F3DB 8-K FILINGS ({days}j)"]
    for filed_at, item_code, severity, summary in rows:
        sev_str = f"sev {severity}" if severity is not None else "?"
        item_str = item_code or "?"
        summ = (summary or "")[:80]
        lines.append(f"  [{filed_at[:10]}] {item_str} ({sev_str})")
        if summ:
            lines.append(f"    {summ}")
    lines.append("")
    return "\n".join(lines)


def _format_insider(conn: sqlite3.Connection, ticker: str, days: int = 30) -> str:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        rows = conn.execute(
            "SELECT detected_at, cluster_size, total_value_m, summary "
            "FROM insider_buy_clusters_log WHERE ticker = ? AND detected_at >= ? "
            "ORDER BY detected_at DESC LIMIT 3",
            (ticker, cutoff),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    if not rows:
        return f"\U0001F465 INSIDER BUY CLUSTERS ({days}j)\n  None\n"
    lines = [f"\U0001F465 INSIDER BUY CLUSTERS ({days}j)"]
    for detected_at, cluster_size, value_m, summary in rows:
        val_str = f"\u20AC{value_m:.1f}M" if value_m else "?"
        size_str = f"{cluster_size} buyers" if cluster_size else "?"
        lines.append(f"  [{detected_at[:10]}] {size_str}, total {val_str}")
        if summary:
            lines.append(f"    {str(summary)[:80]}")
    lines.append("")
    return "\n".join(lines)


async def cmd_find(update, ctx):  # noqa: ARG001
    """Cross-domain ticker dump. Usage: /find TICKER"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "Usage: /find TICKER\n"
            "Exemple: /find 4063.T\n"
            "Aggregate: position + target + thesis + signals 7j + 8-K 30j + insider 30j"
        )
        return
    ticker = parts[1].strip().upper()
    if not ticker:
        await update.message.reply_text("Ticker vide")
        return

    db_path = _db_path()
    if not db_path.exists():
        await update.message.reply_text(f"DB not found at {db_path}")
        return

    try:
        conn = sqlite3.connect(str(db_path))
        sections = [
            f"\U0001F50D /find {ticker}\n",
            _format_position(conn, ticker),
            _format_target(conn, ticker),
            _format_theses(conn, ticker),
            _format_signals(conn, ticker, days=7),
            _format_filings(conn, ticker, days=30),
            _format_insider(conn, ticker, days=30),
        ]
        conn.close()
        msg = "\n".join(sections)
        # Telegram limit 4096 chars; chunk if needed
        if len(msg) > 3900:
            chunks = []
            cur = ""
            for section in sections:
                if len(cur) + len(section) + 2 < 3900:
                    cur = cur + "\n" + section if cur else section
                else:
                    if cur:
                        chunks.append(cur)
                    cur = section
            if cur:
                chunks.append(cur)
            for c in chunks:
                await update.message.reply_text(c)
        else:
            await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Error in /find {ticker}: {type(e).__name__}: {e}")
