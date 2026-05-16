"""Bias pattern handler — aggregate cognitive bias tags across decisions.

Read-only. Complete the empirical tetrahedron:
1. /journal_audit       — reveal silent tickers (signals + zero decisions)
2. /signal_drilldown    — investigate signals per ticker
3. /thesis_health       — review active theses health
4. /bias_pattern (NEW)  — aggregate bias patterns across decisions

Data sources:
- decisions.bias_tags (JSON list, auto-tagged by intelligence.bias_tagger)
- decisions.mistake_tag_auto (single tag, auto)
- decisions.mistake_tag_manual (single tag, user override)

Taxonomy: 10 BIASES from intelligence.bias_tagger.BIASES
(anchoring, recency_bias, confirmation_bias, fomo, narrative_capture,
loss_aversion, regret_avoidance, overconfidence, sunk_cost,
availability_heuristic).

Sparse data is informative: zero bias_tags 30d means either no decisions
OR bias_tagger not running. Show coverage ratio explicitly.

Zero touch to measurement pipeline.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections import Counter

from bot.handlers._common import db_path
from intelligence.bias_tagger import BIASES

__all__ = ["cmd_bias_pattern"]

log = logging.getLogger("bot")


def _parse_bias_tags(tags_json: str | None) -> list[str]:
    """Parse decisions.bias_tags JSON list. Returns [] on parse failure."""
    if not tags_json or tags_json == "[]":
        return []
    try:
        data = json.loads(tags_json)
        if isinstance(data, list):
            return [t for t in data if isinstance(t, str) and t in BIASES]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _compute_bias_pattern(window_days: int) -> dict:
    """Aggregate bias_tags + mistake_tag_auto + mistake_tag_manual across decisions.

    Returns dict with: window_days, total_decisions, with_bias_tags,
    with_mistake_auto, with_mistake_manual, bias_counts (Counter),
    mistake_auto_counts (Counter), mistake_manual_counts (Counter),
    ticker_bias_map (dict ticker -> Counter of biases), top_tagged_decisions (list).
    """
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT id, ticker, decision_type, bias_tags,
                      mistake_tag_auto, mistake_tag_manual, created_at
               FROM decisions
               WHERE created_at >= datetime('now', ?)
               ORDER BY created_at DESC""",
            (f"-{window_days} days",),
        ).fetchall()
    finally:
        conn.close()

    total = len(rows)
    with_bias = 0
    with_auto = 0
    with_manual = 0
    bias_counts: Counter[str] = Counter()
    mistake_auto_counts: Counter[str] = Counter()
    mistake_manual_counts: Counter[str] = Counter()
    ticker_bias_map: dict[str, Counter] = {}
    tagged_decisions: list[dict] = []

    for row in rows:
        ticker = row["ticker"]
        bias_list = _parse_bias_tags(row["bias_tags"])
        if bias_list:
            with_bias += 1
            for tag in bias_list:
                bias_counts[tag] += 1
                if ticker not in ticker_bias_map:
                    ticker_bias_map[ticker] = Counter()
                ticker_bias_map[ticker][tag] += 1
            tagged_decisions.append({
                "id": row["id"],
                "ticker": ticker,
                "decision_type": row["decision_type"],
                "biases": bias_list,
                "date": row["created_at"][:10],
            })

        mta = row["mistake_tag_auto"]
        if mta and mta.strip():
            with_auto += 1
            mistake_auto_counts[mta] += 1

        mtm = row["mistake_tag_manual"]
        if mtm and mtm.strip():
            with_manual += 1
            mistake_manual_counts[mtm] += 1

    return {
        "window_days": window_days,
        "total_decisions": total,
        "with_bias_tags": with_bias,
        "with_mistake_auto": with_auto,
        "with_mistake_manual": with_manual,
        "bias_counts": bias_counts,
        "mistake_auto_counts": mistake_auto_counts,
        "mistake_manual_counts": mistake_manual_counts,
        "ticker_bias_map": ticker_bias_map,
        "tagged_decisions": tagged_decisions,
    }


def _format_bias_pattern(data: dict) -> str:
    """Format bias pattern for Telegram (no parse_mode, plain text)."""
    total = data["total_decisions"]
    if total == 0:
        return (
            f"BIAS PATTERN — {data['window_days']}d window\n\n"
            f"No decisions in window. Use /position_buy or /position_sell to log decisions.\n"
            f"Bias tagger runs automatically on each decision."
        )

    lines = []
    lines.append(f"BIAS PATTERN — {data['window_days']}d window")
    lines.append("")
    lines.append(f"Total decisions       : {total}")
    lines.append(f"With bias_tags        : {data['with_bias_tags']} ({100*data['with_bias_tags']/total:.0f}%)")
    lines.append(f"With mistake_auto     : {data['with_mistake_auto']} ({100*data['with_mistake_auto']/total:.0f}%)")
    lines.append(f"With mistake_manual   : {data['with_mistake_manual']} ({100*data['with_mistake_manual']/total:.0f}%)")
    lines.append("")

    # Coverage warning
    if total >= 5 and data["with_bias_tags"] == 0:
        lines.append("WARNING: 0 bias_tags despite N>=5 decisions.")
        lines.append("Check that intelligence.bias_tagger.auto_tag_biases runs after each decision.")
        lines.append("")

    if data["bias_counts"]:
        lines.append("Bias frequency (auto-tagged):")
        for bias, n in data["bias_counts"].most_common(10):
            pct = 100 * n / total
            bar = "*" * min(int(pct / 5), 20)
            lines.append(f"  {bias:25s}: {n:2d} ({pct:.0f}%) {bar}")
        lines.append("")

    if data["mistake_auto_counts"]:
        lines.append("Mistake tags (auto):")
        for tag, n in data["mistake_auto_counts"].most_common(8):
            lines.append(f"  {tag:25s}: {n}")
        lines.append("")

    if data["mistake_manual_counts"]:
        lines.append("Mistake tags (manual override):")
        for tag, n in data["mistake_manual_counts"].most_common(8):
            lines.append(f"  {tag:25s}: {n}")
        lines.append("")

    if data["ticker_bias_map"]:
        lines.append("By ticker:")
        # Sort tickers by total bias count
        sorted_tickers = sorted(
            data["ticker_bias_map"].items(),
            key=lambda x: -sum(x[1].values()),
        )
        for ticker, counter in sorted_tickers[:8]:
            top = ", ".join(f"{b}({n})" for b, n in counter.most_common(3))
            lines.append(f"  {ticker:9s}: {top}")
        lines.append("")

    if data["tagged_decisions"]:
        lines.append("Recent tagged decisions:")
        for d in data["tagged_decisions"][:5]:
            biases_str = ", ".join(d["biases"])
            lines.append(f"  #{d['id']:3d} [{d['date']}] {d['ticker']:9s} {d['decision_type']:14s} {biases_str}")
        lines.append("")

    lines.append("Reference: 10 BIASES defined in intelligence/bias_tagger.py")
    return "\n".join(lines)


async def cmd_bias_pattern(update, ctx):  # noqa: ARG001
    """Show cognitive bias pattern aggregate across decisions window.

    Usage: /bias_pattern [window_days]
    Default: 90 days
    """
    parts = update.message.text.split()
    try:
        window_days = int(parts[1]) if len(parts) > 1 else 90
    except (ValueError, IndexError):
        await update.message.reply_text(
            "Usage: /bias_pattern [window_days]\nDefault: 90 days"
        )
        return

    if window_days <= 0 or window_days > 730:
        await update.message.reply_text("window_days must be 1-730")
        return

    try:
        data = _compute_bias_pattern(window_days)
        msg = _format_bias_pattern(data)
        if len(msg) > 3900:
            msg = msg[:3900] + "\n[truncated]"
        await update.message.reply_text(msg)
    except Exception as e:
        log.error(f"cmd_bias_pattern error: {e}")
        await update.message.reply_text(f"Error: {e}")
