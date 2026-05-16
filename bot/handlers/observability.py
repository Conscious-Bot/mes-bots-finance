"""Observability handlers — health, stats, KPIs, costs.

Extracted from bot/main.py Sprint 1.1 chunk 2 (2026-05-16).
Mechanical move only, zero logic change.

Includes 5 handlers + 4 helpers:
- cmd_health           : /health system check
- cmd_handler_stats    : /handler_stats Pareto curve
- cmd_kpi_status       : /kpi_status Path 5/6 KPI dashboard
- cmd_cost_trajectory  : /cost_trajectory budget tracking
- cmd_llm_costs        : /llm_costs token usage

Helpers exposed for cron jobs (weekly_kpi_status_job in bot/main.py):
- _kpi_compute_all
- _format_kpi_report
- _cost_compute_trajectory
- _cost_format_trajectory
"""
from __future__ import annotations

import logging

from shared.config import BUDGET_MONTHLY_USD  # single source of truth, lives in shared/config.py

log = logging.getLogger("bot")

__all__ = [
    "_cost_compute_trajectory",
    "_cost_format_trajectory",
    "_format_kpi_report",
    "_kpi_compute_all",
    "cmd_cost_trajectory",
    "cmd_handler_stats",
    "cmd_health",
    "cmd_kpi_status",
    "cmd_llm_costs",
]


async def cmd_health(update, ctx):  # noqa: ARG001
    """Health check: process, DB, LLM activity, data freshness, recent errors."""
    import os
    from datetime import datetime
    from pathlib import Path

    from shared import storage as storage_mod

    lines = ["*Bot health check*", ""]

    # Process
    pid = os.getpid()
    bot_start_iso = storage_mod.load_state().get("bot_start_ts", "?")
    try:
        bot_start = datetime.fromisoformat(bot_start_iso.replace("Z", "+00:00"))
        uptime_min = int((datetime.utcnow() - bot_start.replace(tzinfo=None)).total_seconds() / 60)
        uptime_str = f"{uptime_min // 60}h {uptime_min % 60}min"
    except Exception:
        uptime_str = "?"
    lines.append(f"*Process:* PID {pid}, uptime {uptime_str}")

    # DB
    try:
        db_path = storage_mod._DB_PATH
        db_size_mb = round(Path(db_path).stat().st_size / 1024 / 1024, 2)
        with storage_mod.db() as conn:
            wal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        lines.append(f"*DB:* OK, {db_size_mb} MB, WAL={wal_mode}")
    except Exception as e:
        lines.append(f"*DB:* FAILED ({e})")

    # LLM activity (last call from llm_calls table)
    try:
        with storage_mod.db() as conn:
            row = conn.execute(
                "SELECT MAX(created_at) as last, COUNT(*) as n FROM llm_calls WHERE created_at > datetime('now', '-24 hours')"
            ).fetchone()
            last_llm = row["last"] if row else None
            n_llm_24h = row["n"] if row else 0
            cost_24h_row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) as c FROM llm_calls WHERE created_at > datetime('now', '-24 hours')"
            ).fetchone()
            cost_24h = float(cost_24h_row["c"]) if cost_24h_row else 0.0
        lines.append(f"*LLM:* {n_llm_24h} calls last 24h, ${cost_24h:.2f}, last @ {last_llm or 'never'}")
    except Exception as e:
        lines.append(f"*LLM:* FAILED ({e})")

    # Data freshness (signals, gmail cron health)
    try:
        with storage_mod.db() as conn:
            row = conn.execute(
                "SELECT MAX(timestamp) as last, COUNT(*) as n FROM signals WHERE timestamp > datetime('now', '-24 hours')"
            ).fetchone()
            last_sig = row["last"] if row else None
            n_sig_24h = row["n"] if row else 0
        lines.append(f"*Signals 24h:* {n_sig_24h} ingested, last @ {last_sig or 'never'}")
    except Exception as e:
        lines.append(f"*Signals:* FAILED ({e})")

    # Predictions + theses active count
    try:
        with storage_mod.db() as conn:
            open_pred = conn.execute(
                "SELECT COUNT(*) FROM predictions WHERE actual_date IS NULL"
            ).fetchone()[0]
            active_theses = conn.execute(
                "SELECT COUNT(*) FROM theses WHERE COALESCE(status, 'active') = 'active'"
            ).fetchone()[0]
            open_pos = conn.execute(
                "SELECT COUNT(*) FROM positions WHERE status = 'open'"
            ).fetchone()[0]
        lines.append(f"*Active state:* {open_pred} open predictions, {active_theses} active theses, {open_pos} open positions")
    except Exception as e:
        lines.append(f"*Active state:* FAILED ({e})")

    # Recent handler usage (proves Telegram polling works)
    try:
        with storage_mod.db() as conn:
            row = conn.execute(
                "SELECT MAX(ts) as last FROM handler_calls WHERE ts > datetime('now', '-1 hour')"
            ).fetchone()
            last_handler = row["last"] if row and row["last"] else "no calls 1h"
        lines.append(f"*Telegram:* last handler call @ {last_handler}")
    except Exception:
        lines.append("*Telegram:* (no handler_calls table or empty)")

    lines.append("")
    lines.append("_Run /handler_stats for detailed call breakdown._")
    await update.message.reply_text("\n".join(lines))


async def cmd_handler_stats(update, ctx):  # noqa: ARG001
    """Phase Solidification P0 #3 — Show handler usage stats with Pareto curve.

    Usage: /handler_stats [days=30]
    """
    parts = update.message.text.split()
    days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
    import sqlite3 as _sql

    from shared import storage as _storage

    conn = _sql.connect(_storage._DB_PATH)
    conn.row_factory = _sql.Row
    try:
        rows = conn.execute(
            "SELECT handler_name, COUNT(*) AS n, "
            "MAX(timestamp) AS last_used, MIN(timestamp) AS first_used "
            "FROM handler_calls "
            "WHERE timestamp >= datetime('now', '-' || ? || ' days') "
            "GROUP BY handler_name ORDER BY n DESC",
            (int(days),),
        ).fetchall()
    finally:
        conn.close()
    total = sum(r["n"] for r in rows)
    if total == 0:
        await update.message.reply_text(f"No handler calls in last {days} days.")
        return
    lines = [f"HANDLER USAGE — last {days}d ({total} calls, {len(rows)} unique)"]
    cumulative = 0
    for r in rows:
        cumulative += r["n"]
        pct = 100 * cumulative / total
        last_dt = (r["last_used"] or "")[:10]
        lines.append(f"  {r['handler_name']:24s} n={r['n']:4d} cumul={pct:5.1f}%  last={last_dt}")
    # Pareto threshold callout
    pareto_80 = next(
        (i for i, _ in enumerate(rows) if sum(rows[j]["n"] for j in range(i + 1)) >= 0.8 * total), len(rows)
    )
    if pareto_80 < len(rows) - 1:
        lines.append(
            f"\nPareto: top {pareto_80 + 1} handlers = 80% calls. {len(rows) - pareto_80 - 1} handlers = long tail."
        )
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


def _kpi_compute_all():
    """Compute all 5 KPIs. Returns dict with status per KPI."""
    import sqlite3 as _sql

    from shared import storage as _storage

    conn = _sql.connect(_storage._DB_PATH)
    conn.row_factory = _sql.Row
    out = {}

    # KPI #2: predictions résolues 28d (target ≥5) + forecast 28d ahead
    r2 = conn.execute(
        "SELECT COUNT(*) AS resolved_28d FROM predictions "
        "WHERE resolved_at IS NOT NULL AND resolved_at >= datetime('now', '-28 days')"
    ).fetchone()
    open_pred = conn.execute("SELECT COUNT(*) AS n FROM predictions WHERE resolved_at IS NULL").fetchone()["n"]
    stuck = conn.execute(
        "SELECT COUNT(*) AS n FROM predictions WHERE target_date <= datetime('now') AND resolved_at IS NULL"
    ).fetchone()["n"]
    projected_28d = conn.execute(
        "SELECT COUNT(*) AS n FROM predictions WHERE resolved_at IS NULL AND target_date <= datetime('now', '+28 days')"
    ).fetchone()["n"]
    target = 5
    n2 = r2["resolved_28d"]
    # Forecast at J+28: current resolutions in window won't all stay (rolling), but new ones come in
    # Simpler heuristic: projected = current + new resolutions expected in next 28d
    forecast_j28 = n2 + projected_28d  # upper bound
    if n2 >= target:
        s2 = "✅ GREEN"
    elif stuck > 0:
        s2 = f"🚨 RED — {stuck} predictions stuck (target_date passé, resolve cron failing?)"
    elif forecast_j28 >= target:
        s2 = f"⏳ ON TRACK — {projected_28d} resolutions dues in next 28d, forecast J+28: {forecast_j28}"
    elif n2 >= target * 0.6:
        s2 = f"⚠️ YELLOW — forecast J+28: {forecast_j28} < target {target}"
    else:
        deficit = target - forecast_j28
        s2 = f"🚨 PROJECTED BREACH — forecast J+28: {forecast_j28}, need {deficit} more predictions created"
    out["kpi2"] = {
        "title": "KPI #2 NON-NEG: Predictions résolues 28d",
        "target": f"≥{target}",
        "current": f"{n2} resolved | {open_pred} open ({stuck} stuck) | {projected_28d} due in 28d",
        "status": s2,
        "enforcement": "Stop build 5j + force-use si breach",
    }

    # KPI #3: Brier rolling 90d (target <0.20)
    r3 = conn.execute(
        "SELECT AVG(brier_score) AS brier_avg, COUNT(*) AS n FROM predictions "
        "WHERE brier_score IS NOT NULL AND resolved_at >= datetime('now', '-90 days')"
    ).fetchone()
    brier = r3["brier_avg"]
    n3 = r3["n"]
    if n3 < 10:
        s3 = f"🔍 INSUFFICIENT DATA — N={n3}, need ≥10"
        b_str = f"N={n3} (insufficient)"
    elif brier < 0.20:
        s3 = "✅ GREEN"
        b_str = f"{brier:.3f}"
    elif brier < 0.25:
        s3 = "⚠️ YELLOW — approaching ceiling"
        b_str = f"{brier:.3f}"
    else:
        s3 = "🚨 RED — exceeded threshold, revue méthodo"
        b_str = f"{brier:.3f}"
    out["kpi3"] = {
        "title": "KPI #3: Brier rolling 90d",
        "target": "<0.20",
        "current": b_str,
        "status": s3,
        "enforcement": "Alert + revue méthodo si >0.25",
    }

    # KPI #4: panic sells (heuristic: full_exit BEFORE thesis triggered_partial)
    r4 = conn.execute(
        "SELECT COUNT(*) AS n FROM decisions d "
        "LEFT JOIN theses t ON t.id = d.thesis_id "
        "WHERE d.decision_type = 'full_exit' "
        "AND d.created_at >= datetime('now', '-30 days') "
        "AND (t.triggered_partial_at IS NULL OR d.created_at < t.triggered_partial_at) "
        "AND (t.triggered_stop_at IS NULL OR d.created_at < t.triggered_stop_at)"
    ).fetchone()
    n4 = r4["n"]
    if n4 == 0:
        s4 = "✅ GREEN"
    elif n4 == 1:
        s4 = "⚠️ YELLOW — 1 panic sell, monitor"
    else:
        s4 = f"🚨 RED — {n4} panic sells, pause + bias analysis"
    out["kpi4"] = {
        "title": "KPI #4: Panic sells core (30d)",
        "target": "0",
        "current": f"{n4} flagged (full_exit pre-partial-trigger)",
        "status": s4,
        "enforcement": "Pause + bias analysis si ≥1",
    }

    # KPI #5: decisions matérielles journalisées (reasoning >=30 chars AND bias_tags filled)
    r5 = conn.execute(
        "SELECT "
        "  SUM(CASE WHEN decision_type IN ('entry','scale_in','partial_exit','full_exit') THEN 1 ELSE 0 END) AS material, "
        "  SUM(CASE WHEN decision_type IN ('entry','scale_in','partial_exit','full_exit') "
        "           AND LENGTH(COALESCE(reasoning, '')) >= 30 "
        "           AND COALESCE(bias_tags, '') != '' THEN 1 ELSE 0 END) AS journalised "
        "FROM decisions "
        "WHERE created_at >= datetime('now', '-30 days')"
    ).fetchone()
    material = r5["material"] or 0
    journalised = r5["journalised"] or 0
    pct = 100.0 * journalised / material if material > 0 else None
    if material == 0:
        s5 = "🔍 NO MATERIAL DECISIONS 30d"
        p_str = "N/A"
    elif pct == 100:
        s5 = "✅ GREEN"
        p_str = "100%"
    elif pct >= 90:
        s5 = "⚠️ YELLOW"
        p_str = f"{pct:.0f}%"
    else:
        s5 = "🚨 RED — backfill required avant new thesis"
        p_str = f"{pct:.0f}%"
    out["kpi5"] = {
        "title": "KPI #5: Decisions matérielles journalisées",
        "target": "100%",
        "current": f"{journalised}/{material} = {p_str}",
        "status": s5,
        "enforcement": "No new thesis until backfill si <90%",
    }

    # KPI #6: skip (requires position book integration)
    out["kpi6"] = {
        "title": "KPI #6: TWR vs SPY/QQQ 12M",
        "target": ">-5pp",
        "current": "Not yet implemented",
        "status": "⏸ NOT IMPLEMENTED — requires positions integration",
        "enforcement": "Revue strat trimestrielle si <-5pp",
    }

    conn.close()
    return out


def _format_kpi_report(kpis):
    """Format KPI dict into Telegram message."""
    from datetime import datetime as _dt

    lines = [f"📊 *KPI STATUS* — {_dt.now().strftime('%Y-%m-%d %H:%M')}", ""]
    breach_count = 0
    yellow_count = 0
    green_count = 0
    for key in ["kpi2", "kpi3", "kpi4", "kpi5", "kpi6"]:
        k = kpis[key]
        lines.append(f"*{k['title']}*")
        lines.append(f"  Target  : {k['target']}")
        lines.append(f"  Current : {k['current']}")
        lines.append(f"  Status  : {k['status']}")
        lines.append(f"  Enforce : _{k['enforcement']}_")
        lines.append("")
        if "🚨 RED" in k["status"]:
            breach_count += 1
        elif "⚠️ YELLOW" in k["status"] or "⏳ TIMER" in k["status"]:
            yellow_count += 1
        elif "✅ GREEN" in k["status"]:
            green_count += 1
    lines.append("═══════════════════════")
    lines.append(f"Overall: {green_count} GREEN | {yellow_count} YELLOW/timer | {breach_count} RED")
    if breach_count > 0:
        lines.append("⚠️ Breaches detected — action required.")
    return "\n".join(lines)


async def cmd_kpi_status(update, ctx):  # noqa: ARG001
    """Phase Solidification P2 — Show KPI status with breach detection."""
    try:
        kpis = _kpi_compute_all()
        msg = _format_kpi_report(kpis)
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        log.error(f"cmd_kpi_status error: {e}")
        await update.message.reply_text(f"KPI status error: {e}")


def _cost_compute_trajectory():
    """Compute cost trajectory data: today, MTD, projection, breakdowns."""
    import calendar as _cal
    import sqlite3 as _sql
    from datetime import datetime as _dt

    from shared import storage as _storage

    conn = _sql.connect(_storage._DB_PATH)
    conn.row_factory = _sql.Row
    try:
        today_str = _dt.now().strftime("%Y-%m-%d")
        now = _dt.now()
        days_in_month = _cal.monthrange(now.year, now.month)[1]
        day_of_month = now.day
        month_start = f"{now.year:04d}-{now.month:02d}-01"

        # Spend buckets
        today = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE DATE(created_at) = ?", (today_str,)
        ).fetchone()[0]
        yesterday = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE DATE(created_at) = DATE('now', '-1 day')"
        ).fetchone()[0]
        week7 = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE created_at >= datetime('now', '-7 days')"
        ).fetchone()[0]
        days30 = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE created_at >= datetime('now', '-30 days')"
        ).fetchone()[0]
        mtd = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE DATE(created_at) >= ?", (month_start,)
        ).fetchone()[0]

        # Projection month-end (linear extrapolation)
        projection = (mtd / day_of_month) * days_in_month if day_of_month > 0 else 0
        budget_pct = 100.0 * projection / BUDGET_MONTHLY_USD if BUDGET_MONTHLY_USD > 0 else 0

        if projection < BUDGET_MONTHLY_USD * 0.6:
            status = "✅ GREEN"
        elif projection < BUDGET_MONTHLY_USD * 0.9:
            status = "⚠️ YELLOW"
        else:
            status = "🚨 RED — budget breach imminent"

        # By tier 30d
        tier_rows = conn.execute(
            "SELECT COALESCE(tier, '?') AS tier, ROUND(SUM(cost_usd), 4) AS spend, COUNT(*) AS n "
            "FROM llm_calls WHERE created_at >= datetime('now', '-30 days') "
            "GROUP BY tier ORDER BY spend DESC"
        ).fetchall()

        # By task 30d (top 8)
        task_rows = conn.execute(
            "SELECT COALESCE(NULLIF(task, ''), '(untagged)') AS task, "
            "       ROUND(SUM(cost_usd), 4) AS spend, COUNT(*) AS n "
            "FROM llm_calls WHERE created_at >= datetime('now', '-30 days') "
            "GROUP BY task ORDER BY spend DESC LIMIT 8"
        ).fetchall()

        # Daily trend last 7d
        daily_rows = conn.execute(
            "SELECT DATE(created_at) AS day, ROUND(SUM(cost_usd), 4) AS spend "
            "FROM llm_calls WHERE created_at >= datetime('now', '-7 days') "
            "GROUP BY day ORDER BY day"
        ).fetchall()

        return {
            "today": today,
            "yesterday": yesterday,
            "week7": week7,
            "days30": days30,
            "mtd": mtd,
            "projection": projection,
            "budget_pct": budget_pct,
            "status": status,
            "days_elapsed": day_of_month,
            "days_in_month": days_in_month,
            "tier_rows": [dict(r) for r in tier_rows],
            "task_rows": [dict(r) for r in task_rows],
            "daily_rows": [dict(r) for r in daily_rows],
        }
    finally:
        conn.close()


def _cost_format_trajectory(data):
    """Format trajectory dict to Telegram message."""
    lines = ["💰 *COST TRAJECTORY*", ""]
    lines.append("*Daily*")
    lines.append(f"  Today      : ${data['today']:.4f}")
    lines.append(f"  Yesterday  : ${data['yesterday']:.4f}")
    lines.append(f"  7d window  : ${data['week7']:.4f}")
    lines.append(f"  30d window : ${data['days30']:.4f}")
    lines.append("")
    lines.append("*Month-to-Date*")
    lines.append(f"  Spent     : ${data['mtd']:.4f} ({data['days_elapsed']}/{data['days_in_month']}j)")
    lines.append(f"  Projected : ${data['projection']:.2f} (linear extrapol.)")
    lines.append(f"  Budget    : ${BUDGET_MONTHLY_USD:.0f}/mo target")
    lines.append(f"  Usage     : {data['budget_pct']:.1f}% of budget")
    lines.append(f"  Status    : {data['status']}")
    lines.append("")
    lines.append("*Top tier 30d*")
    for r in data["tier_rows"]:
        pct = 100 * r["spend"] / data["days30"] if data["days30"] > 0 else 0
        lines.append(f"  {r['tier']:12s} ${r['spend']:.4f} ({pct:.0f}%, n={r['n']})")
    lines.append("")
    lines.append("*Top task 30d*")
    for r in data["task_rows"][:5]:
        lines.append(f"  {r['task'][:20]:20s} ${r['spend']:.4f} (n={r['n']})")
    lines.append("")
    lines.append("*Daily 7d trend*")
    for r in data["daily_rows"]:
        bar_len = int(r["spend"] / max(0.01, max(d["spend"] for d in data["daily_rows"])) * 15)
        bar = "█" * bar_len
        lines.append(f"  {r['day']}  ${r['spend']:.4f}  {bar}")
    return "\n".join(lines)


async def cmd_cost_trajectory(update, ctx):  # noqa: ARG001
    """Phase Solidification P2 — Strategic cost dashboard avec MTD + projection + budget."""
    try:
        data = _cost_compute_trajectory()
        msg = _cost_format_trajectory(data)
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        log.error(f"cmd_cost_trajectory error: {e}")
        await update.message.reply_text(f"Error: {e}")


async def cmd_llm_costs(update, ctx):  # noqa: ARG001
    """Phase A2 — Display LLM call costs + token usage by tier.
    Usage: /llm_costs [hours]   (default 24h)
    """
    parts = update.message.text.split()
    try:
        hours = int(parts[1]) if len(parts) > 1 else 24
    except ValueError:
        hours = 24

    from shared import llm

    try:
        data = llm.get_cost_summary(window_hours=hours)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return

    rows = data["rows"]
    errors = data["errors"]

    if not rows:
        await update.message.reply_text(f"No LLM calls in last {hours}h. (errors: {errors})")
        return

    lines = [f"LLM costs last {hours}h"]
    total_cost = sum(r.get("cost") or 0 for r in rows)
    total_calls = sum(r["n_calls"] for r in rows)
    total_in = sum(r["in_t"] or 0 for r in rows)
    total_out = sum(r["out_t"] or 0 for r in rows)
    total_cached = sum(r["cached_t"] or 0 for r in rows)
    cache_pct = (total_cached / total_in * 100) if total_in else 0
    lines.append(f"  Total: {total_calls} calls, ${total_cost:.4f}")
    lines.append(f"  Tokens: {total_in:,} in ({total_cached:,} cached, {cache_pct:.1f}%) / {total_out:,} out")
    if errors:
        lines.append(f"  Errors: {errors}")
    lines.append("")
    lines.append("By tier/model:")
    for r in rows:
        cost = r.get("cost") or 0
        avg = r.get("avg_ms") or 0
        lines.append(f"  {r['tier']:11s} {r['model'][:30]:30s} n={r['n_calls']} ${cost:.4f} avg={avg:.0f}ms")
    msg = "\n".join(lines)
    await update.message.reply_text(msg)
