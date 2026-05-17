"""Portfolio enrichment handlers — sectors, narratives, drift.

Read-only handlers added in Sprint 1.1 chunk Day 5 Ship B (2026-05-16).
Zero touch to measurement pipeline. Pure SQL + config.yaml read.

Three handlers:
- /portfolio_sectors    : breakdown by sector (config.yaml taxonomy)
- /portfolio_narratives : breakdown by sector_thesis_id from theses.notes
- /portfolio_drift      : positions vs portfolio_targets, over/underweight
"""
from __future__ import annotations

import logging
import re
import sqlite3

import yaml

from bot.handlers._common import config_path, db_path
from shared.display import format_aggregate_line, format_finance, format_pct

__all__ = [
    "cmd_portfolio_drift",
    "cmd_portfolio_narratives",
    "cmd_portfolio_sectors",
]

log = logging.getLogger("bot")


def _build_ticker_to_sector() -> dict[str, str]:
    """Map every ticker in config.yaml universe to its sector label.

    Returns dict ticker -> sector_label (e.g. "core/semis_core", "watch", "ext/european_pea").
    Unknown tickers default to "unknown" via .get() fallback in callers.
    """
    cfg = yaml.safe_load(config_path().read_text())
    universe = cfg.get("universe", {})
    mapping: dict[str, str] = {}

    # Core has sub-categories
    for sub_cat, tickers in universe.get("core", {}).items():
        if isinstance(tickers, list):
            for t in tickers:
                mapping[t] = f"core/{sub_cat}"

    # Watch is flat list
    for t in universe.get("watch", []):
        if t not in mapping:
            mapping[t] = "watch"

    # Extended has sub-categories
    for sub_cat, tickers in universe.get("extended", {}).items():
        if isinstance(tickers, list):
            for t in tickers:
                if t not in mapping:
                    mapping[t] = f"ext/{sub_cat}"

    return mapping


_SECTOR_THESIS_RE = re.compile(r"sector_thesis_id:\s*([A-Z0-9_]+)")


def _extract_narrative(notes: str | None) -> str | None:
    """Extract sector_thesis_id from theses.notes multi-line string. Returns None if absent."""
    if not notes:
        return None
    m = _SECTOR_THESIS_RE.search(notes)
    return m.group(1) if m else None


def _compute_book_market_value(conn: sqlite3.Connection) -> tuple[float, list[dict]]:
    """Fetch open positions + compute market value via FX-aware price helper.

    Returns (total_market_value, list_of_position_dicts).
    Falls back to cost_basis if live price unavailable (network failure resilience).
    """
    from shared.prices import get_current_price_in_eur

    rows = conn.execute(
        "SELECT ticker, qty, avg_cost, account FROM positions WHERE status='open'"
    ).fetchall()

    positions = []
    total_mv = 0.0
    for ticker, qty, avg_cost, account in rows:
        try:
            cur_price = get_current_price_in_eur(ticker)
        except Exception:
            cur_price = None
        cost_basis = qty * avg_cost
        mv = (cur_price * qty) if cur_price else cost_basis
        positions.append({
            "ticker": ticker,
            "qty": qty,
            "avg_cost": avg_cost,
            "account": account,
            "cost_basis": cost_basis,
            "market_value": mv,
            "has_live_price": cur_price is not None,
        })
        total_mv += mv

    return total_mv, positions


async def cmd_portfolio_sectors(update, ctx):  # noqa: ARG001
    """Show portfolio breakdown by sector taxonomy (config.yaml). Usage: /portfolio_sectors"""
    try:
        ticker_to_sector = _build_ticker_to_sector()
    except Exception as e:
        log.error(f"cmd_portfolio_sectors config load error: {e}")
        await update.message.reply_text(f"Config load error: {e}")
        return

    conn = sqlite3.connect(str(db_path()))
    try:
        total_mv, positions = _compute_book_market_value(conn)
    finally:
        conn.close()

    if not positions:
        await update.message.reply_text("No active positions.")
        return

    # Group by sector
    sectors: dict[str, dict] = {}
    for p in positions:
        sector = ticker_to_sector.get(p["ticker"], "unknown")
        if sector not in sectors:
            sectors[sector] = {"tickers": [], "mv": 0.0, "cost_basis": 0.0}
        sectors[sector]["tickers"].append(p["ticker"])
        sectors[sector]["mv"] += p["market_value"]
        sectors[sector]["cost_basis"] += p["cost_basis"]

    # Sort by market value descending
    sorted_sectors = sorted(sectors.items(), key=lambda x: x[1]["mv"], reverse=True)

    lines = [f"\U0001F4CA *PORTFOLIO BY SECTOR* — {format_finance(total_mv, decimals=0)} total\n"]
    for sector, data in sorted_sectors:
        pct = (data["mv"] / total_mv * 100) if total_mv else 0
        n = len(data["tickers"])
        pnl_pct = ((data["mv"] / data["cost_basis"] - 1) * 100) if data["cost_basis"] else 0
        tickers_str = ", ".join(sorted(data["tickers"])[:5])
        if n > 5:
            tickers_str += f" +{n-5}"
        # Escape underscores in sub_cat for Telegram Markdown legacy (avoid italic)
        sector_display = sector.replace("_", "\\_")
        lines.append(format_aggregate_line(
            label=sector_display,
            market_value=data["mv"],
            pct_total=pct,
            n_positions=n,
            pnl_pct=pnl_pct,
        ))
        lines.append(f"    {tickers_str}")

    # Warnings
    unknown_count = len(sectors.get("unknown", {}).get("tickers", []))
    if unknown_count > 0:
        lines.append("")
        lines.append(f"\u26A0\uFE0F {unknown_count} tickers not in config.yaml universe: {', '.join(sectors['unknown']['tickers'])}")
        lines.append("Add them to universe.core/watch/extended in config.yaml")

    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_portfolio_narratives(update, ctx):  # noqa: ARG001
    """Show portfolio breakdown by sector_thesis_id narrative. Usage: /portfolio_narratives"""
    conn = sqlite3.connect(str(db_path()))
    try:
        total_mv, positions = _compute_book_market_value(conn)

        # Fetch theses notes for narrative extraction
        rows = conn.execute(
            "SELECT ticker, notes FROM theses WHERE status='active'"
        ).fetchall()
        ticker_to_narrative: dict[str, str] = {}
        for ticker, notes in rows:
            narrative = _extract_narrative(notes)
            if narrative:
                ticker_to_narrative[ticker] = narrative
    finally:
        conn.close()

    if not positions:
        await update.message.reply_text("No active positions.")
        return

    # Group by narrative (fallback to "untagged" if no thesis or no sector_thesis_id)
    narratives: dict[str, dict] = {}
    for p in positions:
        narrative = ticker_to_narrative.get(p["ticker"], "untagged")
        if narrative not in narratives:
            narratives[narrative] = {"tickers": [], "mv": 0.0, "cost_basis": 0.0}
        narratives[narrative]["tickers"].append(p["ticker"])
        narratives[narrative]["mv"] += p["market_value"]
        narratives[narrative]["cost_basis"] += p["cost_basis"]

    sorted_narratives = sorted(narratives.items(), key=lambda x: x[1]["mv"], reverse=True)

    lines = [f"\U0001F3AF *PORTFOLIO BY NARRATIVE* — {format_finance(total_mv, decimals=0)} total\n"]
    for narrative, data in sorted_narratives:
        pct = (data["mv"] / total_mv * 100) if total_mv else 0
        n = len(data["tickers"])
        pnl_pct = ((data["mv"] / data["cost_basis"] - 1) * 100) if data["cost_basis"] else 0
        tickers_str = ", ".join(sorted(data["tickers"]))
        # Escape underscores in narrative for Telegram Markdown legacy (avoid italic in bold)
        narrative_display = narrative.replace("_", "\\_")
        lines.append(
            f"  *{narrative_display}*  {format_finance(data['mv'], decimals=0)}  "
            f"[{pct:4.1f}%]  ({n} pos, PnL {format_pct(pnl_pct, decimals=1, signed=True)})"
        )
        lines.append(f"    {tickers_str}")
        lines.append("")

    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_portfolio_drift(update, ctx):  # noqa: ARG001
    """Show drift between actual positions and portfolio_targets. Usage: /portfolio_drift"""
    conn = sqlite3.connect(str(db_path()))
    try:
        # Fetch all targets with their actual positions
        rows = conn.execute("""
            SELECT pt.ticker, pt.account, pt.target_eur, pt.status, pt.phase_week,
                   pt.narrative, pt.priority,
                   COALESCE(p.qty * p.avg_cost, 0) AS cost_basis_eur,
                   p.qty, p.avg_cost
            FROM portfolio_targets pt
            LEFT JOIN positions p ON pt.ticker = p.ticker AND p.status = 'open'
            ORDER BY pt.target_eur DESC
        """).fetchall()
    finally:
        conn.close()

    if not rows:
        await update.message.reply_text("No portfolio_targets configured. Use scripts/import_portfolio_targets.py.")
        return

    # Aggregate by status
    executed: list[dict] = []
    planned: list[dict] = []
    locked: list[dict] = []
    dropped: list[dict] = []

    total_target = 0.0
    total_actual = 0.0

    for ticker, account, target_eur, status, phase_week, narrative, priority, cost_basis, _qty, _avg_cost in rows:
        target_eur = float(target_eur or 0)
        cost_basis = float(cost_basis or 0)
        drift = cost_basis - target_eur
        drift_pct = (drift / target_eur * 100) if target_eur else 0
        item = {
            "ticker": ticker,
            "account": account,
            "target": target_eur,
            "actual": cost_basis,
            "drift": drift,
            "drift_pct": drift_pct,
            "status": status,
            "phase_week": phase_week,
            "narrative": narrative or "",
            "priority": priority or "",
        }
        total_target += target_eur
        total_actual += cost_basis
        if status == "executed":
            executed.append(item)
        elif status == "locked":
            locked.append(item)
        elif status == "planned":
            planned.append(item)
        elif status == "dropped":
            dropped.append(item)

    total_drift = total_actual - total_target
    pct_deployed = (total_actual / total_target * 100) if total_target else 0

    lines = ["\U0001F4C9 *PORTFOLIO DRIFT vs TARGETS*\n"]
    lines.append(f"  Total target  : {format_finance(total_target, decimals=0, width=7)}")
    lines.append(f"  Total actual  : {format_finance(total_actual, decimals=0, width=7)}")
    lines.append(f"  Deployed      : {pct_deployed:.1f}%")
    lines.append(f"  Net drift     : {format_finance(total_drift, decimals=0, signed=True)}")
    lines.append("")

    # Executed positions with drift
    if executed:
        lines.append(f"*EXECUTED* ({len(executed)})")
        for item in sorted(executed, key=lambda x: x["drift"], reverse=False)[:15]:
            sign = "\U0001F534" if item["drift_pct"] < -10 else ("\U0001F7E2" if abs(item["drift_pct"]) <= 10 else "\U0001F535")
            lines.append(
                f"  {sign} {item['ticker']:10s} "
                f"{format_finance(item['actual'], decimals=0, width=5)}/"
                f"{format_finance(item['target'], decimals=0, width=5)}  "
                f"drift {format_finance(item['drift'], decimals=0, signed=True)} "
                f"({format_pct(item['drift_pct'], decimals=0, signed=True)})"
            )
        lines.append("")

    # Locked (PEA)
    if locked:
        lines.append(f"*LOCKED* ({len(locked)} PEA)")
        for item in locked[:10]:
            lines.append(f"  \U0001F512 {item['ticker']:10s} {format_finance(item['actual'], decimals=0, width=5)}/{format_finance(item['target'], decimals=0, width=5)}")
        lines.append("")

    # Planned (to execute)
    if planned:
        lines.append(f"*PLANNED* ({len(planned)} pending)")
        for item in sorted(planned, key=lambda x: (x["phase_week"] or 99, -x["target"]))[:10]:
            phase_str = f"W{item['phase_week']}" if item['phase_week'] else "—"
            prio_str = f" [{item['priority']}]" if item['priority'] else ""
            lines.append(f"  \u23F3 {item['ticker']:10s} {format_finance(item['target'], decimals=0, width=5)}  phase {phase_str}{prio_str}")
        lines.append("")

    if dropped:
        lines.append(f"_dropped: {len(dropped)} items_")

    msg = "\n".join(lines)
    if len(msg) > 3900:
        # Chunk by sections
        chunks = []
        cur = ""
        for line in msg.split("\n"):
            if len(cur) + len(line) + 1 < 3900:
                cur += "\n" + line if cur else line
            else:
                chunks.append(cur)
                cur = line
        if cur:
            chunks.append(cur)
        for c in chunks:
            await update.message.reply_text(c, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")
