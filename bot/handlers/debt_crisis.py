"""Debt crisis monitor Telegram handlers (ADR 006)."""

from __future__ import annotations

from intelligence.debt_monitor import (
    INDICATOR_CONFIG,
    run_scan,
    status_snapshot,
)

_PHASE_ICON = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}
_PHASE_LABEL = {1: "NORMAL", 2: "STRESS", 3: "SEVERE", 4: "CRISIS"}


def _fmt_indicator_line(name: str, ind: dict) -> str:
    cfg = INDICATOR_CONFIG.get(name, {})
    label = cfg.get("label", name)
    phase = ind.get("phase") or 1
    icon = _PHASE_ICON.get(phase, "?")
    val = ind.get("value")
    if val is None:
        val_s = "n/a"
    elif val >= 1000:
        val_s = f"{val:,.0f}"
    elif val >= 10:
        val_s = f"{val:.2f}"
    else:
        val_s = f"{val:.4f}"
    return f"{icon} {label:<32} {val_s:>12}  P{phase}"


async def cmd_debt_status(update, ctx):  # noqa: ARG001
    """Show latest debt crisis monitor status. Usage: /debt_status [refresh]"""
    parts = update.message.text.split()
    refresh = len(parts) > 1 and parts[1].lower() in {"refresh", "fetch", "live"}

    if refresh:
        await update.message.reply_text("🔄 Fetching all 15 indicators...")
        r = run_scan()
        composite_score = r["score"]
        composite_phase = r["phase"]
        breakdown = r["breakdown"]
    else:
        snap = status_snapshot()
        if not snap["composite"]:
            await update.message.reply_text(
                "No debt monitor data yet. Run `/debt_status refresh` to fetch."
            )
            return
        composite_score = snap["composite"]["score"]
        composite_phase = snap["composite"]["phase"]
        import json
        breakdown = json.loads(snap["composite"]["tier_breakdown"])
        # Convert keys back to int (JSON loses int keys)
        breakdown = {int(k): v for k, v in breakdown.items()}

    overall_icon = _PHASE_ICON[composite_phase]
    overall_label = _PHASE_LABEL[composite_phase]

    lines = [
        f"💣 DEBT CRISIS MONITOR — {overall_icon} {overall_label}",
        "",
        f"Composite: {composite_score:.1f} pts → Phase {composite_phase}",
        "",
    ]

    for tier in [1, 2, 3]:
        tier_data = breakdown.get(tier, [])
        if not tier_data:
            continue
        tier_score = sum(e["contribution"] for e in tier_data)
        lines.append(f"━ Tier {tier} ({tier_score:.1f}pts) ━")
        for entry in tier_data:
            ind = {"value": entry.get("value"), "phase": entry.get("phase")}
            line = _fmt_indicator_line(entry["name"], ind)
            stale = " (stale)" if entry.get("stale") else ""
            lines.append(line + stale)
        lines.append("")

    lines.append("Run `/debt_status refresh` for live fetch.")
    msg = "\n".join(lines)
    await update.message.reply_text(f"```\n{msg}\n```", parse_mode="Markdown")
