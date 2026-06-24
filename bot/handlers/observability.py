"""Observability handlers — health, stats, KPIs, costs.

Extracted from bot/main.py Sprint 1.1 chunk 2 (2026-05-16).
Mechanical move only, zero logic change.

Includes 5 handlers + 4 helpers:
- cmd_health           : /health system check
- cmd_handler_stats    : /handler_stats Pareto curve
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
from shared.display import format_billing

log = logging.getLogger("bot")

__all__ = [
    "_cost_compute_trajectory",
    "_cost_format_trajectory",
    "_format_kpi_report",
    "_kpi_compute_all",
    "cmd_bot_data",
    "cmd_cost_trajectory",
    "cmd_handler_stats",
    "cmd_health",
    "cmd_llm_costs",
]


async def cmd_health(update, ctx):  # noqa: ARG001
    """Health check: process, DB, LLM activity, data freshness, recent errors."""
    import os
    from datetime import UTC, datetime
    from pathlib import Path

    from shared import storage as storage_mod

    lines = ["*Bot health check*", ""]

    # Process
    pid = os.getpid()
    bot_start_iso = storage_mod.load_state().get("bot_start_ts", "?")
    try:
        bot_start = datetime.fromisoformat(bot_start_iso.replace("Z", "+00:00"))
        # Backward compat: legacy naive bot_state values treated as UTC
        if bot_start.tzinfo is None:
            bot_start = bot_start.replace(tzinfo=UTC)
        uptime_min = int((datetime.now(UTC) - bot_start).total_seconds() / 60)
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
        lines.append(
            f"*LLM:* {n_llm_24h} calls last 24h, {format_billing(cost_24h, decimals=2)}, last @ {last_llm or 'never'}"
        )
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
                f"SELECT COUNT(*) FROM predictions WHERE resolved_at IS NULL "
                f"AND {storage_mod.canonical_predictions_filter()}"
            ).fetchone()[0]
            active_theses = conn.execute(
                "SELECT COUNT(*) FROM theses WHERE COALESCE(status, 'active') = 'active'"
            ).fetchone()[0]
            open_pos = conn.execute("SELECT COUNT(*) FROM positions WHERE status = 'open'").fetchone()[0]
        lines.append(
            f"*Active state:* {open_pred} open predictions, {active_theses} active theses, {open_pos} open positions"
        )
    except Exception as e:
        lines.append(f"*Active state:* FAILED ({e})")

    # Recent handler usage (proves Telegram polling works)
    try:
        with storage_mod.db() as conn:
            row = conn.execute(
                "SELECT MAX(timestamp) as last FROM handler_calls WHERE timestamp > datetime('now', '-1 hour')"
            ).fetchone()
            last_handler = row["last"] if row and row["last"] else "no calls 1h"
        lines.append(f"*Telegram:* last handler call @ {last_handler}")
    except Exception:
        lines.append("*Telegram:* (no handler_calls table or empty)")

    lines.append("")
    lines.append("_Run /handler_stats for detailed call breakdown._")
    await update.message.reply_text("\n".join(lines))


async def cmd_handler_stats(update, ctx):
    """Phase Solidification P0 #3 — Show handler usage stats with Pareto curve.

    Usage: /handler_stats [days=30]

    M4 fix Day 9 audit: filters known registered CommandHandler.commands set
    via ctx.application.handlers introspection (PTB v21+) to exclude telemetry
    typos (e.g. 'porfolio', 'portfolio_drive', 'healthy') from Pareto curve.
    Typos displayed as separate footer for visibility without pollution.
    Graceful fallback to display-all if introspection fails.
    """
    parts = update.message.text.split()
    days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
    import sqlite3 as _sql

    from telegram.ext import CommandHandler as _CmdHandler

    from shared import storage as _storage

    # M4: introspect registered command names from app.handlers
    known_cmds: set[str] = set()
    try:
        if ctx is not None and hasattr(ctx, "application") and ctx.application is not None:
            for handler_list in ctx.application.handlers.values():
                for h in handler_list:
                    if isinstance(h, _CmdHandler):
                        for cmd in h.commands:
                            known_cmds.add(cmd)
    except Exception:
        known_cmds = set()

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

    if known_cmds:
        known_rows = [r for r in rows if r["handler_name"] in known_cmds]
        typo_rows = [r for r in rows if r["handler_name"] not in known_cmds]
    else:
        known_rows = list(rows)
        typo_rows = []

    total = sum(r["n"] for r in known_rows)
    typo_total = sum(r["n"] for r in typo_rows)

    if total == 0 and typo_total == 0:
        await update.message.reply_text(f"No handler calls in last {days} days.")
        return

    header_extra = ""
    if typo_rows:
        header_extra = f" (+ {typo_total} typo calls / {len(typo_rows)} variants filtered)"
    lines = [f"HANDLER USAGE — last {days}d ({total} known calls, {len(known_rows)} unique){header_extra}"]

    cumulative = 0
    for r in known_rows:
        cumulative += r["n"]
        pct = 100 * cumulative / total if total > 0 else 0
        last_dt = (r["last_used"] or "")[:10]
        lines.append(f"  {r['handler_name']:24s} n={r['n']:4d} cumul={pct:5.1f}%  last={last_dt}")

    if total > 0 and len(known_rows) > 1:
        pareto_80 = next(
            (i for i, _ in enumerate(known_rows) if sum(known_rows[j]["n"] for j in range(i + 1)) >= 0.8 * total),
            len(known_rows),
        )
        if pareto_80 < len(known_rows) - 1:
            lines.append(
                f"\nPareto: top {pareto_80 + 1} handlers = 80% calls. {len(known_rows) - pareto_80 - 1} handlers = long tail."
            )

    # M4 footer: surface typos detected (telemetry middleware logs failed cmds too)
    if typo_rows:
        lines.append("")
        sample_names = ", ".join(r["handler_name"] for r in typo_rows[:6])
        if len(typo_rows) > 6:
            sample_names += f", ...({len(typo_rows) - 6} more)"
        lines.append(f"Typos/untracked ({typo_total} calls, {len(typo_rows)} unique): {sample_names}")

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

    # KPI #1: Bot uptime (read from uptime.log, not DB)
    try:
        from shared.uptime import compute_kpi1

        out["kpi1"] = compute_kpi1(window_days=30)
    except Exception as _kpi1_err:
        out["kpi1"] = {
            "title": "KPI #1: Bot uptime (30d)",
            "target": ">95%",
            "current": f"compute error: {type(_kpi1_err).__name__}",
            "status": "🔍 ERROR — see logs",
            "enforcement": "Alert si <95%",
        }

    # KPI #2: predictions résolues 28d (target ≥5) + forecast 28d ahead
    # ADR 014 : filter canonique pour exclure v0/v1/rule_v1_*.
    from shared import storage as _stg_kpi
    r2 = conn.execute(
        "SELECT COUNT(*) AS resolved_28d FROM predictions "
        "WHERE resolved_at IS NOT NULL AND outcome != 'neutral' "
        f"AND {_stg_kpi.canonical_predictions_filter()} "
        "AND resolved_at >= datetime('now', '-28 days')"
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
    # ADR 014 : detection "v2 pas encore demarre" pour eviter silent zero
    # quand le compte canonique = 0 mais v1 substance existe.
    v1_resolved_28d = conn.execute(
        "SELECT COUNT(*) FROM predictions "
        "WHERE resolved_at IS NOT NULL AND outcome != 'neutral' "
        "AND methodology_version = 'v1' "
        "AND resolved_at >= datetime('now', '-28 days')"
    ).fetchone()[0]
    # Forecast at J+28: current resolutions in window won't all stay (rolling), but new ones come in
    # Simpler heuristic: projected = current + new resolutions expected in next 28d
    forecast_j28 = n2 + projected_28d  # upper bound
    if n2 >= target:
        s2 = "✅ GREEN"
    elif stuck > 0:
        s2 = f"🚨 RED — {stuck} predictions stuck (target date passé, resolve cron failing?)"
    elif n2 == 0 and v1_resolved_28d > 0:
        s2 = (
            f"🔍 V2 NOT YET STARTED — {v1_resolved_28d} v1 archive resolved 28d "
            "(hors headline canonique ADR 014). Headline v2 ouvre post-J-day 10/06."
        )
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
    from shared import storage as _storage_kpi3
    r3 = conn.execute(
        f"SELECT AVG(brier_score) AS brier_avg, COUNT(*) AS n FROM predictions "
        f"WHERE brier_score IS NOT NULL AND probability_at_creation != 0.5 "
        f"AND resolved_at >= datetime('now', '-90 days') "
        f"AND {_storage_kpi3.canonical_predictions_filter()}"
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

    # KPI #4: panic sells (factual signature, redesign 24/06).
    # AVANT (defectueux) : full_exit BEFORE triggered_partial_at + BEFORE triggered_stop_at.
    # Faux positifs structurels : SNOW redeploy +18.6% gain thesis concluded -> classifie panic.
    # APRES (signature factuelle non-contournable) : pas de keyword reasoning (qui creerait
    # une backdoor pour le biais #1 lock_in : ecrire "redeploiement" desarmerait le KPI).
    # Conditions panic basees uniquement sur faits DB :
    #   (a) full_exit OU partial_exit
    #   (b) ET (sortie sous l'entree EN PERTE OU stop touche AVANT la decision)
    #   (c) ET thesis statut != 'concluded' (thesis pas explicitement close)
    # SNOW exclu car (a) prix > entry (+18.6% gain) ET (b) thesis.status='concluded'.
    #
    # Garde-fous techniques :
    #   - Temporal anchor sur triggered_stop_at <= d.created_at (sinon stop futur false-flag
    #     les partial_exit anterieurs comme MU/ALAB 29/05 + stop 12/06).
    #   - Ratio price/entry > 0.1 pour eviter currency-mismatch L12 (decisions.price_at_decision
    #     stocke EUR pour foreign tickers vs theses.entry_price stocke native, cf memory
    #     project_currency_148_eur_invariant). Skip arithmetique inutile si units differents.
    # Cf memory [[bias-detectors-factual-not-keyword]] doctrine 24/06.
    r4 = conn.execute(
        "SELECT COUNT(*) AS n FROM decisions d "
        "LEFT JOIN theses t ON t.id = d.thesis_id "
        "WHERE d.decision_type IN ('full_exit','partial_exit') "
        "AND d.created_at >= datetime('now', '-30 days') "
        "AND ("
        "  (d.price_at_decision IS NOT NULL AND t.entry_price IS NOT NULL "
        "   AND d.price_at_decision < t.entry_price "
        "   AND (d.price_at_decision * 1.0 / t.entry_price) > 0.1)"
        "  OR (t.triggered_stop_at IS NOT NULL AND t.triggered_stop_at <= d.created_at)"
        ") "
        "AND COALESCE(t.status, '') != 'concluded'"
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
        "current": f"{n4} flagged (full-exit pre-partial-trigger)",
        "status": s4,
        "enforcement": "Pause + bias analysis si ≥1",
    }

    # KPI #5: Trade decisions journalisées (30d window)
    # Material scope (whitelist): entry, scale_in, partial_exit, full_exit
    # Excluded: no_action_flag (passive), thesis_add/set (thesis events, separate KPI),
    #           position_set/override (manual admin overrides, no journal req)
    # Journalisation criteria: reasoning >=30 chars AND bias_tags filled
    # Enforcement: blocks new thesis creation if <90% (prevents adding theses
    # without proper retrospective audit trail on recent trade behavior)
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
    if material == 0 or pct is None:
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
        "title": "KPI #5: Trade decisions journalisées (entry/scale/exit, 30d)",
        "target": "100%",
        "current": f"{journalised}/{material} = {p_str}",
        "status": s5,
        "enforcement": "No new thesis until backfill si <90%",
    }

    # KPI #6: portfolio return vs SPY/QQQ benchmarks (Day 9 P3 wired)
    try:
        from shared.portfolio_metrics import compute_kpi6 as _compute_kpi6

        out["kpi6"] = _compute_kpi6()
    except Exception as _kpi6_err:
        out["kpi6"] = {
            "title": "KPI #6: Portfolio return vs SPY/QQQ (EUR)",
            "target": ">-5pp",
            "current": f"compute error: {type(_kpi6_err).__name__}",
            "status": "🔍 ERROR — see logs",
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
    na_count = 0
    for key in ["kpi1", "kpi2", "kpi3", "kpi4", "kpi5", "kpi6"]:
        k = kpis[key]
        lines.append(f"*{k['title']}*")
        lines.append(f"  Target  : {k['target']}")
        lines.append(f"  Current : {k['current']}")
        lines.append(f"  Status  : {k['status']}")
        lines.append(f"  Enforce : _{k['enforcement']}_")
        lines.append("")
        if "🚨" in k["status"]:
            breach_count += 1
        elif "⚠️" in k["status"]:
            yellow_count += 1
        elif "✅" in k["status"] or "⏳" in k["status"]:
            green_count += 1
        elif "🔍" in k["status"] or "⏸" in k["status"]:
            na_count += 1
    lines.append("═══════════════════════")
    lines.append(f"Overall: {green_count} GREEN | {yellow_count} YELLOW/timer | {breach_count} RED | {na_count} N/A")
    if breach_count > 0:
        lines.append("⚠️ Breaches detected — action required.")
    return "\n".join(lines)


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
    lines.append(f"  Today      : {format_billing(data['today'], decimals=4)}")
    lines.append(f"  Yesterday  : {format_billing(data['yesterday'], decimals=4)}")
    lines.append(f"  7d window  : {format_billing(data['week7'], decimals=4)}")
    lines.append(f"  30d window : {format_billing(data['days30'], decimals=4)}")
    lines.append("")
    lines.append("*Month-to-Date*")
    lines.append(
        f"  Spent     : {format_billing(data['mtd'], decimals=4)} ({data['days_elapsed']}/{data['days_in_month']}j)"
    )
    lines.append(f"  Projected : {format_billing(data['projection'], decimals=2)} (linear extrapol.)")
    lines.append(f"  Budget    : {format_billing(BUDGET_MONTHLY_USD, decimals=0)}/mo target")
    lines.append(f"  Usage     : {data['budget_pct']:.1f}% of budget")
    lines.append(f"  Status    : {data['status']}")
    lines.append("")
    lines.append("*Top tier 30d*")
    for r in data["tier_rows"]:
        pct = 100 * r["spend"] / data["days30"] if data["days30"] > 0 else 0
        lines.append(f"  {r['tier']:12s} {format_billing(r['spend'], decimals=4)} ({pct:.0f}%, n={r['n']})")
    lines.append("")
    lines.append("*Top task 30d*")
    for r in data["task_rows"][:5]:
        lines.append(f"  {r['task'][:20]:20s} {format_billing(r['spend'], decimals=4)} (n={r['n']})")
    lines.append("")
    lines.append("*Daily 7d trend*")
    for r in data["daily_rows"]:
        bar_len = int(r["spend"] / max(0.01, max(d["spend"] for d in data["daily_rows"])) * 15)
        bar = "█" * bar_len
        lines.append(f"  {r['day']}  {format_billing(r['spend'], decimals=4)}  {bar}")
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

    await _llm_costs_impl(update, hours)


async def _llm_costs_impl(update, hours: int) -> None:
    """Internal: display LLM call costs + token usage by tier.

    Used by cmd_llm_costs (legacy alias) and cmd_bot_data (Sprint 1.2
    Phase J /bot_data llm_costs). Body extracted verbatim, no dedent.
    """
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
    lines.append(f"  Total: {total_calls} calls, {format_billing(total_cost, decimals=4)}")
    lines.append(f"  Tokens: {total_in:,} in ({total_cached:,} cached, {cache_pct:.1f}%) / {total_out:,} out")
    if errors:
        lines.append(f"  Errors: {errors}")
    lines.append("")
    lines.append("By tier/model:")
    for r in rows:
        cost = r.get("cost") or 0
        avg = r.get("avg_ms") or 0
        lines.append(
            f"  {r['tier']:11s} {r['model'][:30]:30s} n={r['n_calls']} {format_billing(cost, decimals=4)} avg={avg:.0f}ms"
        )
    msg = "\n".join(lines)
    await update.message.reply_text(msg)


async def cmd_kpi_status(update, ctx):  # noqa: ARG001
    """On-demand KPI status report (meme producer que le cron hebdo Sunday 22:30)."""
    kpis = _kpi_compute_all()
    msg = _format_kpi_report(kpis)
    await update.message.reply_text(msg)


async def cmd_bot_data(update, ctx):
    """Sprint 1.2 Phase J dispatcher - /bot_data family.

    Usage:
      /bot_data                       -> usage
      /bot_data health                -> bot health (process, DB, LLM, freshness)
      /bot_data costs                 -> strategic cost dashboard (MTD + projection)
      /bot_data llm_costs [hours]     -> LLM cost breakdown by tier (default 24h)

    Backward-compat aliases preserved 1 release cycle:
      /health, /cost_trajectory, /llm_costs

    Deleted: /kpi_status (Bloc 9 - cron Sunday 22:30 already posts weekly).
    """
    args = ctx.args or []
    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "  /bot_data health                 (process/DB/LLM/freshness)\n"
            "  /bot_data costs                  (MTD + projection vs budget)\n"
            "  /bot_data llm_costs [hours]      (LLM tier breakdown, default 24h)"
        )
        return
    action = args[0].lower()
    if action == "health":
        await cmd_health(update, ctx)
        return
    if action == "costs" or action == "cost_trajectory":
        await cmd_cost_trajectory(update, ctx)
        return
    if action == "llm_costs" or action == "llm":
        try:
            hours = int(args[1]) if len(args) > 1 else 24
        except (ValueError, IndexError):
            hours = 24
        await _llm_costs_impl(update, hours)
        return
    await update.message.reply_text(f"Unknown action: '{action}'\nValid: health, costs, llm_costs")
