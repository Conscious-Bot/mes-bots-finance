"""Sources + universe admin handlers.

Extracted from bot/main.py Sprint 1.1 chunk 5 (2026-05-16, Day 5).
Mechanical move only, zero logic change.

Module exports (6 handlers):
- cmd_sources_health    : /sources_health overall sources signal stats
- cmd_sources_brier     : /sources_brier Brier-based credibility ranking
"""
from __future__ import annotations

__all__ = [
    "cmd_sources",
    "cmd_sources_brier",
    "cmd_sources_health",
]


async def cmd_sources_health(update, ctx):  # noqa: ARG001
    """Health check newsletter sources."""
    import sqlite3
    from datetime import UTC, datetime

    conn = sqlite3.connect("data/bot.db")
    try:
        rows = conn.execute("""
            SELECT s.name, s.credibility,
                   COUNT(sig.id) AS n_30d,
                   MAX(sig.timestamp) AS last_seen
            FROM sources s
            LEFT JOIN signals sig ON s.id = sig.source_id
              AND sig.timestamp > datetime('now', '-30 days')
            WHERE s.type = 'newsletter'
            GROUP BY s.id
            ORDER BY (last_seen IS NULL), last_seen DESC
        """).fetchall()
    finally:
        conn.close()
    if not rows:
        await update.message.reply_text("No newsletter sources found")
        return
    lines = ["Newsletter sources health (30d window):\n"]
    now = datetime.now(UTC)
    for name, cred, n_30d, last_seen in rows:
        short = (name.split("<")[0].strip() or name)[:30]
        age_days = None
        if last_seen:
            try:
                last_dt = datetime.fromisoformat(last_seen.replace("Z", "").split(".")[0])
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
                age_days = (now - last_dt).days
            except Exception:
                pass
        if age_days is None:
            status = "NEVER"
        elif age_days > 7:
            status = f"SILENT {age_days}d"
        elif age_days > 3:
            status = f"slow {age_days}d"
        else:
            status = f"ok {age_days}d"
        cred = cred or 0
        lines.append(f"{short:<30} cred={cred:.2f} 30d={n_30d:>3} {status}")
    await update.message.reply_text("\n".join(lines))


async def cmd_sources_brier(update, ctx):  # noqa: ARG001
    """Phase A1 — Display per-source Brier calibration stats."""
    from shared import storage as storage_mod

    try:
        stats = storage_mod.get_brier_stats_by_source()
    except Exception as e:
        await update.message.reply_text(f"Error fetching brier stats: {e}")
        return

    with_brier = [s for s in stats if s.get("n_resolved") and s["n_resolved"] > 0]
    no_data = [s for s in stats if not s.get("n_resolved")]

    lines = ["Brier calibration stats"]
    lines.append(f"  Sources with resolved predictions: {len(with_brier)}")
    lines.append(f"  Sources awaiting data: {len(no_data)}")
    lines.append("")

    if with_brier:
        lines.append("Top calibrated (low Brier = good):")
        for s in with_brier[:10]:
            mb = s.get("mean_brier")
            mb_s = f"{mb:.3f}" if mb is not None else "n/a"
            cr = s.get("current_cred") or 0.5
            n = s.get("n_resolved") or 0
            nc = s.get("n_correct") or 0
            nn = s.get("n_neutral") or 0
            ni = s.get("n_incorrect") or 0
            lines.append(f"  {s['source_name'][:25]:25s} brier={mb_s} cred={cr:.2f} n={n} ({nc}c/{nn}n/{ni}i)")

    if no_data:
        lines.append("")
        lines.append(f"Sources awaiting (first 5 of {len(no_data)}):")
        for s in no_data[:5]:
            cr = s.get("current_cred") or 0.5
            lines.append(f"  {s['source_name'][:25]:25s} cred={cr:.2f} (no resolved preds yet)")

    lines.append("")
    lines.append("Recalibration runs 1st of month, min N=10 resolved predictions.")
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)

async def cmd_sources(update, ctx):
    """Sprint 1.2 Phase I dispatcher - /sources family.

    Usage:
      /sources health                    -> newsletter sources health check
      /sources brier                     -> per-source Brier calibration stats
      /sources credibility               -> top/worst credibility leaderboard
      /sources feedback ID up|down       -> user feedback on signal #ID

    Backward-compat aliases preserved 1 release cycle:
      /sources_health, /sources_brier, /credibility, /feedback
    """
    args = ctx.args or []
    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "  /sources health        (sources health check)\n"
            "  /sources brier         (per-source Brier stats)\n"
            "  /sources credibility   (top/worst credibility)\n"
            "  /sources feedback ID up|down  (rate signal)"
        )
        return
    action = args[0].lower()
    if action == "health":
        await cmd_sources_health(update, ctx)
        return
    if action == "brier":
        await cmd_sources_brier(update, ctx)
        return
    if action == "credibility":
        from bot.handlers.predictions import cmd_credibility
        await cmd_credibility(update, ctx)
        return
    if action == "feedback":
        if len(args) < 3:
            await update.message.reply_text("Usage: /sources feedback <signal_id> <up|down>")
            return
        try:
            signal_id = int(args[1])
        except ValueError:
            await update.message.reply_text(f"signal_id invalide: {args[1]}")
            return
        rating = args[2].lower()
        if rating not in ("up", "down"):
            await update.message.reply_text(f"rating doit etre up ou down, got: {rating}")
            return
        from bot.handlers.predictions import _feedback_impl
        await _feedback_impl(update, signal_id, rating)
        return
    await update.message.reply_text(
        f"Unknown action: '{action}'\n"
        "Valid: health, brier, credibility, feedback"
    )

