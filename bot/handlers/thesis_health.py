"""Thesis health handler — review active theses with signal support + staleness.

Read-only. Complements /journal_audit (silent tickers reveal) +
/signal_drilldown (per-ticker signals) by showing the OTHER direction:
which active theses lack supporting evidence.

Output structure:
1. By-thesis health rows (signal count, days old, last revisit, narrative)
2. Conviction distribution (inflation watch: alert if >20% at conviction=5)
3. Narrative grouping (5 dominant narratives from sector_thesis_id)
4. Staleness flags (>30d no review)
5. Weak signal support flags (<3 signals 30d for ticker)

Zero touch to measurement pipeline. Pure SQL + JSON parsing.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import Counter
from datetime import UTC, datetime

from bot.handlers._common import db_path

__all__ = ["cmd_thesis_health"]

log = logging.getLogger("bot")


_SECTOR_THESIS_RE = re.compile(r"sector_thesis_id:\s*([A-Z0-9_]+)")
_NARRATIVE_RE = re.compile(r"narrative\s*=\s*(\w+)")


def _extract_narrative(notes: str | None) -> str:
    """Extract narrative tag from notes.

    Recognizes 2 formats:
    1. 'narrative=AI_compute | tier=A | ...' (16/05 doc format)
    2. 'sector_thesis_id: STORAGE_AI_HYPERSCALE_2026' (15/05 framework format)
    Returns 'untagged' if neither present.
    """
    if not notes:
        return "untagged"
    # Try 16/05 narrative= format first (recent)
    m = _NARRATIVE_RE.search(notes)
    if m:
        return m.group(1)
    # Fallback to 15/05 sector_thesis_id format
    m = _SECTOR_THESIS_RE.search(notes)
    return m.group(1) if m else "untagged"


def _ticker_in_entities(entities_json: str | None, ticker: str) -> bool:
    """Check if ticker in signals.entities JSON list."""
    if not entities_json:
        return False
    try:
        data = json.loads(entities_json)
        if isinstance(data, list):
            return ticker in data
        if isinstance(data, dict):
            return ticker in (data.get("tickers") or [])
    except (json.JSONDecodeError, ValueError):
        pass
    return False


def _compute_health(window_days: int, min_impact: float) -> dict:
    """Compute health snapshot for all active theses.

    Returns dict with: theses (list per-thesis dicts), conviction_dist (Counter),
    narrative_dist (Counter), stale_count, weak_support_count.
    """
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    try:
        thesis_rows = conn.execute(
            """SELECT id, ticker, conviction, direction, status, opened_at,
                      last_reviewed, last_revisit_at, notes
               FROM theses WHERE status='active'
               ORDER BY conviction DESC, opened_at DESC"""
        ).fetchall()

        sig_rows = conn.execute(
            """SELECT entities FROM signals
               WHERE impact_magnitude >= ?
                 AND timestamp >= datetime('now', ?)
                 AND entities IS NOT NULL AND entities != ''""",
            (min_impact, f"-{window_days} days"),
        ).fetchall()
    finally:
        conn.close()

    # Build ticker -> signal count map
    ticker_sigs: dict[str, int] = {}
    for row in sig_rows:
        try:
            ents = json.loads(row["entities"])
            if isinstance(ents, list):
                for t in ents:
                    if isinstance(t, str) and t.isupper() and 2 <= len(t) <= 6:
                        ticker_sigs[t] = ticker_sigs.get(t, 0) + 1
            elif isinstance(ents, dict):
                for t in ents.get("tickers") or []:
                    if isinstance(t, str):
                        ticker_sigs[t] = ticker_sigs.get(t, 0) + 1
        except (json.JSONDecodeError, ValueError):
            pass

    now = datetime.now(UTC)
    theses = []
    stale = 0
    weak = 0

    for row in thesis_rows:
        opened = row["opened_at"]
        try:
            opened_dt = datetime.fromisoformat(opened.replace("Z", "+00:00"))
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=UTC)
            days_old = (now - opened_dt).days
        except (ValueError, AttributeError):
            days_old = -1

        last_rev = row["last_revisit_at"] or row["last_reviewed"]
        if last_rev:
            try:
                rev_dt = datetime.fromisoformat(last_rev.replace("Z", "+00:00"))
                if rev_dt.tzinfo is None:
                    rev_dt = rev_dt.replace(tzinfo=UTC)
                days_since_review = (now - rev_dt).days
            except (ValueError, AttributeError):
                days_since_review = days_old
        else:
            days_since_review = days_old

        ticker = row["ticker"]
        signal_count = ticker_sigs.get(ticker, 0)
        narrative = _extract_narrative(row["notes"])

        is_stale = days_since_review > 30
        is_weak = signal_count < 3 and days_old > 7

        if is_stale:
            stale += 1
        if is_weak:
            weak += 1

        theses.append({
            "id": row["id"],
            "ticker": ticker,
            "conviction": row["conviction"],
            "direction": row["direction"],
            "days_old": days_old,
            "days_since_review": days_since_review,
            "signal_count": signal_count,
            "narrative": narrative,
            "is_stale": is_stale,
            "is_weak": is_weak,
        })

    conviction_dist = Counter(t["conviction"] for t in theses if t["conviction"] is not None)
    narrative_dist = Counter(t["narrative"] for t in theses)

    return {
        "window_days": window_days,
        "min_impact": min_impact,
        "theses": theses,
        "conviction_dist": conviction_dist,
        "narrative_dist": narrative_dist,
        "stale_count": stale,
        "weak_count": weak,
        "total": len(theses),
    }


def _format_health(data: dict) -> str:
    """Format health snapshot for Telegram (no parse_mode, lesson from 69e70c1)."""
    if data["total"] == 0:
        return "No active theses."

    lines = []
    lines.append(f"THESIS HEALTH — {data['total']} active theses")
    lines.append(f"Signal window: {data['window_days']}d, min impact: {data['min_impact']:.1f}")
    lines.append("")

    # Stale + weak summary
    lines.append(f"Stale (>30d no review): {data['stale_count']}")
    lines.append(f"Weak support (<3 sig 30d, >7d old): {data['weak_count']}")
    lines.append("")

    # Per-thesis rows (sorted by conviction DESC, then signal_count DESC)
    sorted_theses = sorted(
        data["theses"],
        key=lambda t: (-(t["conviction"] or 0), -t["signal_count"])
    )

    lines.append("Per-thesis (sorted by conviction):")
    for t in sorted_theses[:20]:
        flag = ""
        if t["is_stale"]:
            flag += " STALE"
        if t["is_weak"]:
            flag += " WEAK"
        if t["signal_count"] >= 5:
            flag += " OK"
        lines.append(
            f"  #{t['id']:2d} {t['ticker']:9s} c{t['conviction']} | "
            f"{t['signal_count']:2d} sig | {t['days_old']:3d}d old | {t['narrative'][:25]:25s}{flag}"
        )

    if len(sorted_theses) > 20:
        lines.append(f"  ... +{len(sorted_theses) - 20} more")

    # Conviction distribution + inflation watch
    lines.append("")
    lines.append("Conviction distribution:")
    total = data["total"]
    for c in sorted(data["conviction_dist"].keys(), reverse=True):
        n = data["conviction_dist"][c]
        pct = (n / total * 100) if total else 0
        bar = "*" * int(pct / 5)
        lines.append(f"  {c}: {n:2d} ({pct:.0f}%) {bar}")

    # Inflation watch
    high_conviction = data["conviction_dist"].get(5, 0)
    if total > 0 and (high_conviction / total) > 0.20:
        pct = high_conviction / total * 100
        lines.append("")
        lines.append(f"INFLATION WATCH: {pct:.0f}% theses at conviction=5 (target <20%)")

    # Narrative dist
    if data["narrative_dist"]:
        lines.append("")
        lines.append("By narrative:")
        for narrative, n in data["narrative_dist"].most_common(8):
            lines.append(f"  {narrative:35s}: {n}")

    return "\n".join(lines)


async def cmd_thesis_health(update, ctx):  # noqa: ARG001
    """Show health snapshot of all active theses.

    Usage: /thesis_health [signal_window_days] [min_impact]
    Defaults: 30 days, impact >= 3.0
    """
    parts = update.message.text.split()
    try:
        window_days = int(parts[1]) if len(parts) > 1 else 30
        min_impact = float(parts[2]) if len(parts) > 2 else 3.0
    except (ValueError, IndexError):
        await update.message.reply_text(
            "Usage: /thesis_health [window_days] [min_impact]\nDefaults: 30 days, impact 3.0"
        )
        return

    if window_days <= 0 or window_days > 365:
        await update.message.reply_text("window_days must be 1-365")
        return
    if min_impact < 0 or min_impact > 5:
        await update.message.reply_text("min_impact must be 0.0-5.0")
        return

    try:
        data = _compute_health(window_days, min_impact)
        msg = _format_health(data)
        if len(msg) > 3900:
            msg = msg[:3900] + "\n[truncated]"
        await update.message.reply_text(msg)
    except Exception as e:
        log.error(f"cmd_thesis_health error: {e}")
        await update.message.reply_text(f"Error: {e}")
