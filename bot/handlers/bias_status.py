"""/bias_status -- observability biais events (table bias_events, Pile 2.1).

Lecture-seule. Aggrege l'etat actuel de l'instrumentation des biais :
- Total events
- Breakdown par bias (lock_in, fomo_greed, other)
- Breakdown par status (open, resolved, void, thesis_invalidated, reentered, missing_data)
- Dernier event (timestamp + ticker)
- Marqueurs de canaux (kca actif vs over_cap en veille vs lock_in surface 2 non-instrumente)

Cf docs/glossary.md section Biais documentes + memory presage-biais-1-only.
"""

from __future__ import annotations

import logging
import sqlite3
from collections import Counter

from bot.handlers._common import db_path

__all__ = ["cmd_bias_status"]

log = logging.getLogger("bot")


def _format_count_line(items: Counter, total: int, *, pad: int = 12) -> str:
    """Format `lock_in       3 ░░░  / total = N`."""
    if not items:
        return "(aucun)"
    return "\n".join(
        f"  {k:<{pad}}{v:>4}  ({v / total * 100:.0f}%)" if total else f"  {k:<{pad}}{v:>4}"
        for k, v in items.most_common()
    )


def _query_bias_status() -> dict:
    """Returns dict avec total, by_bias, by_status, latest."""
    cx = sqlite3.connect(db_path())
    try:
        rows = cx.execute(
            "SELECT bias, status, ticker, created_at FROM bias_events ORDER BY id DESC"
        ).fetchall()
    finally:
        cx.close()
    total = len(rows)
    by_bias = Counter(r[0] for r in rows)
    by_status = Counter(r[1] for r in rows)
    latest = rows[0] if rows else None
    return {
        "total": total,
        "by_bias": by_bias,
        "by_status": by_status,
        "latest": latest,
    }


async def cmd_bias_status(update, ctx):  # noqa: ARG001
    """Observability : etat actuel du User Bias Detector mecanique.

    Sortie example :
        BIAS_EVENTS -- 12 total

        Par biais :
          lock_in      0 (0%)   -- Surface 2 non instrumente (ADR-010)
          fomo_greed  10 (83%)  -- 2 canaux (kca actif + over_cap veille)
          other        2 (17%)

        Par statut :
          resolved     6 (50%)
          open         4 (33%)
          missing_data 1 (8%)
          void         1 (8%)

        Dernier : 2026-06-01 18:32 NVDA fomo_greed open

    Cf docs/glossary.md § Biais documentes + ADR-010.
    """
    try:
        s = _query_bias_status()
    except sqlite3.Error as e:
        await update.message.reply_text(f"bias_status DB error: {e}")
        return

    total = s["total"]
    if total == 0:
        await update.message.reply_text(
            "BIAS_EVENTS -- 0 total\n\n"
            "Aucun bias_event encore. Canaux instrumentes :\n"
            "  fomo_greed (lock_in trim/exit) : kca actif, over_cap en veille (construction).\n"
            "  lock_in (vendre winners) : Surface 2 non instrumentee (cf ADR-010)."
        )
        return

    by_bias = s["by_bias"]
    by_status = s["by_status"]
    latest = s["latest"]
    lat_str = f"{latest[3][:16]} {latest[2] or '?'} {latest[0]} {latest[1]}" if latest else "(aucun)"

    msg = (
        f"BIAS_EVENTS -- {total} total\n\n"
        f"Par biais :\n{_format_count_line(by_bias, total)}\n\n"
        f"Par statut :\n{_format_count_line(by_status, total)}\n\n"
        f"Dernier : {lat_str}\n\n"
        f"Canaux : kca actif / over_cap veille (construction) / lock_in Surface 2 non instrumente."
    )
    await update.message.reply_text(msg)
