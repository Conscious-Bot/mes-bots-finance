"""Debt crisis monitor Telegram handlers (ADR 006)."""

from __future__ import annotations

from intelligence.debt_monitor import INDICATOR_CONFIG, run_scan, status_snapshot
from shared import storage
from shared.storage import db

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

# ============================================================
# Phase 2C — /debt_history INDICATOR + /debt_alerts on|off
# ============================================================


def _sparkline(values: list[float]) -> str:
    """ASCII sparkline using Unicode block characters. Empty string if no values."""
    if not values:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    vmin, vmax = min(values), max(values)
    if vmin == vmax:
        return blocks[4] * len(values)
    return "".join(
        blocks[min(7, int((v - vmin) / (vmax - vmin) * 7))] for v in values
    )


def _format_val_compact(val: float | None) -> str:
    """Smart format indicator value, abs-aware for negatives."""
    if val is None:
        return "n/a"
    av = abs(val)
    if av >= 1000:
        return f"{val:,.0f}"
    if av >= 1:
        return f"{val:.2f}"
    return f"{val:.4f}"


async def cmd_debt_history(update, ctx):  # noqa: ARG001
    """Show 30d history + sparkline for one debt monitor indicator.

    Usage:
      /debt_history          — list all 15 available indicators by tier
      /debt_history TYX      — 30d history for TYX (case-insensitive)
    """
    parts = update.message.text.split()
    args = parts[1:] if len(parts) > 1 else []

    if not args:
        lines = ["*Debt Monitor Indicators (15)*", "", "Usage: `/debt_history INDICATOR`", ""]
        for tier in [1, 2, 3]:
            lines.append(f"*Tier {tier}:*")
            for name, cfg in INDICATOR_CONFIG.items():
                if cfg.get("tier") == tier:
                    lines.append(f"  • `{name}` — {cfg.get('label', name)}")
            lines.append("")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    target = args[0]
    matched_name = next(
        (n for n in INDICATOR_CONFIG if n.lower() == target.lower()),
        None,
    )
    if not matched_name:
        names_list = ", ".join(INDICATOR_CONFIG.keys())
        await update.message.reply_text(
            f"Unknown indicator `{target}`.\n\nAvailable: {names_list}",
            parse_mode="Markdown",
        )
        return

    name = matched_name
    cfg = INDICATOR_CONFIG[name]
    label = cfg.get("label", name)

    with db() as cx:
        rows = cx.execute(
            "SELECT timestamp, value, phase FROM debt_signals "
            "WHERE indicator_name = ? ORDER BY timestamp DESC LIMIT 30",
            (name,),
        ).fetchall()

    if not rows:
        await update.message.reply_text(
            f"No history yet for `{name}`. Run `/debt_status refresh` first.",
            parse_mode="Markdown",
        )
        return

    rows = list(reversed(rows))
    numeric_values = [r["value"] for r in rows if r["value"] is not None]
    sparkline = _sparkline(numeric_values) if numeric_values else "(no numeric values)"

    phases_seq = [r["phase"] for r in rows if r["phase"] is not None]
    transitions = sum(1 for i in range(1, len(phases_seq)) if phases_seq[i] != phases_seq[i - 1])

    latest = rows[-1]
    cur_phase = latest["phase"]
    cur_val = latest["value"]
    cur_icon = _PHASE_ICON.get(cur_phase, "?") if cur_phase else "?"
    cur_label = _PHASE_LABEL.get(cur_phase, "?") if cur_phase else "?"

    msg_lines = [
        f"*📊 {label}* (`{name}`)",
        "",
        f"Current: {cur_icon} {cur_label} (P{cur_phase}) — {_format_val_compact(cur_val)}",
    ]
    if numeric_values:
        msg_lines.append(
            f"30d range: {_format_val_compact(min(numeric_values))} — "
            f"{_format_val_compact(max(numeric_values))}"
        )
    msg_lines += [
        f"Transitions: {transitions} in {len(rows)} observations",
        "",
        f"Sparkline: `{sparkline}`",
        "",
        "*Last 5 observations:*",
    ]
    for r in rows[-5:][::-1]:
        ts_short = r["timestamp"][:16].replace("T", " ")
        p = r["phase"]
        p_icon = _PHASE_ICON.get(p, "?") if p else "?"
        msg_lines.append(f"  `{ts_short}` {p_icon} P{p} {_format_val_compact(r['value'])}")

    await update.message.reply_text("\n".join(msg_lines), parse_mode="Markdown")


async def cmd_debt_alerts(update, ctx):  # noqa: ARG001
    """Toggle debt monitor Telegram alerts.

    Usage:
      /debt_alerts        — show current state
      /debt_alerts on     — enable alerts (default)
      /debt_alerts off    — disable Telegram push (scans continue silently)

    When OFF: cron scans persist data normally, but no Telegram push fires
    on composite escalations or per-indicator transitions. Manual /debt_status
    queries still work.
    """
    parts = update.message.text.split()
    args = parts[1:] if len(parts) > 1 else []

    state = storage.load_state()
    current = bool(state.get("debt_alerts_enabled", True))

    if not args:
        icon = "🟢" if current else "🔴"
        await update.message.reply_text(
            f"*Debt monitor alerts: {icon} {'ON' if current else 'OFF'}*\n\n"
            f"Usage: `/debt_alerts on` or `/debt_alerts off`\n\n"
            f"When OFF: scans persist data, but no Telegram push on transitions.",
            parse_mode="Markdown",
        )
        return

    arg = args[0].lower()
    if arg not in ("on", "off"):
        await update.message.reply_text(
            f"Invalid arg `{args[0]}`. Use `on` or `off`.",
            parse_mode="Markdown",
        )
        return

    new_val = arg == "on"
    storage.update_state(debt_alerts_enabled=new_val)

    icon = "🟢" if new_val else "🔴"
    msg = (
        "You will be notified on phase transitions."
        if new_val
        else "Telegram push suppressed. Scans continue silently."
    )
    await update.message.reply_text(
        f"Debt monitor alerts: {icon} *{'ON' if new_val else 'OFF'}*\n\n{msg}",
        parse_mode="Markdown",
    )

