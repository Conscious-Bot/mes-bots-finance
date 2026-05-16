"""Sources + universe admin handlers.

Extracted from bot/main.py Sprint 1.1 chunk 5 (2026-05-16, Day 5).
Mechanical move only, zero logic change.

Module exports (6 handlers):
- cmd_sources_health    : /sources_health overall sources signal stats
- cmd_sources_brier     : /sources_brier Brier-based credibility ranking
- cmd_sources_half_life : /sources_half_life decay/freshness per source
- cmd_tiers             : /tiers tier S/A/B breakdown
- cmd_tiers_watch       : /tiers_watch watch tier summary
- cmd_promote           : /promote TICKER tier (universe move)
"""
from __future__ import annotations

__all__ = [
    "cmd_promote",
    "cmd_sources_brier",
    "cmd_sources_half_life",
    "cmd_sources_health",
    "cmd_tiers",
    "cmd_tiers_watch",
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
    now = datetime.now(UTC).replace(tzinfo=None)
    for name, cred, n_30d, last_seen in rows:
        short = (name.split("<")[0].strip() or name)[:30]
        age_days = None
        if last_seen:
            try:
                last_dt = datetime.fromisoformat(last_seen.replace("Z", "").split(".")[0])
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


async def cmd_sources_half_life(update, ctx):  # noqa: ARG001
    """Phase A4 — Display per-source information half-life."""
    from shared import storage as storage_mod

    rows = storage_mod.get_all_sources_with_half_life()
    if not rows:
        await update.message.reply_text("No sources found.")
        return

    with_hl = [r for r in rows if r.get("half_life_days") is not None]
    without_hl = [r for r in rows if r.get("half_life_days") is None]

    lines = ["Information Half-Life per source"]
    lines.append(
        f"  {len(with_hl)} computed, {len(without_hl)} awaiting data (need N>=3 signals with tickers + 30j forward)"
    )
    lines.append("")

    if with_hl:
        lines.append("Computed (ascending = signals decay fastest):")
        for r in with_hl[:15]:
            hl = r["half_life_days"]
            n = r.get("half_life_n_samples") or 0
            cr = r.get("credibility") or 0.5
            name = r["name"][:30]
            lines.append(f"  {name:30s} hl={hl:5.1f}d n={n:2d} cred={cr:.2f}")

    if without_hl:
        lines.append("")
        lines.append(f"Awaiting data (top 5 of {len(without_hl)}):")
        for r in without_hl[:5]:
            n = r.get("half_life_n_samples") or 0
            n_sig = r.get("n_signals") or 0
            lines.append(f"  {r['name'][:30]:30s} n_sig={n_sig} (n_with_move={n})")

    lines.append("")
    lines.append("Refresh runs Sundays 5h Paris. Threshold ±5% within 30j forward window.")

    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_tiers(update, ctx):  # noqa: ARG001
    """Phase Tickers Tiered — display ticker tier breakdown."""
    from shared import config as cfg_mod

    bd = cfg_mod.get_tier_breakdown()
    lines = ["TICKER UNIVERSE — Tiered Architecture"]
    lines.append(f"Total: {bd['total']} tickers\n")
    lines.append(f"━━━ T1 CORE ({bd['counts']['core']}) — scan complet ━━━")
    for cat, tks in (bd["core"] or {}).items():
        if isinstance(tks, list):
            lines.append(f"  {cat:22s} {tks}")
    lines.append(f"\n━━━ T2 WATCH ({bd['counts']['watch']}) — scan moyen ━━━")
    lines.append("  (flat list, see /tiers_watch for full list)")
    lines.append(f"\n━━━ T3 EXTENDED ({bd['counts']['extended']}) — scan minimal ━━━")
    for cat, tks in (bd["extended"] or {}).items():
        if isinstance(tks, list):
            lines.append(f"  {cat:22s} {tks}")
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_tiers_watch(update, ctx):  # noqa: ARG001
    """Full list of T2 watch tickers."""
    from shared import config as cfg_mod

    watch = cfg_mod.get_tickers("watch")
    msg = f"T2 WATCH ({len(watch)} tickers):\n\n" + ", ".join(watch)
    await update.message.reply_text(msg)


async def cmd_promote(update, ctx):  # noqa: ARG001
    """Phase Tickers Tiered — promote ticker between tiers.
    Usage: /promote TICKER tier  (tier = core | watch | extended)"""
    parts = update.message.text.split()
    if len(parts) < 3:
        await update.message.reply_text(
            "Usage: /promote TICKER tier\n  tier = core | watch | extended\n  Example: /promote PLTR core"
        )
        return
    ticker = parts[1].upper()
    new_tier = parts[2].lower()
    from shared import config as cfg_mod

    ok, msg = cfg_mod.promote_ticker(ticker, new_tier)
    await update.message.reply_text(("OK " if ok else "FAIL ") + msg)
