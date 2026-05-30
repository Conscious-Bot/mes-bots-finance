"""Periodic cron jobs — extracted from bot/jobs.py Phase C (21/05/2026)."""

import logging

from bot.handlers.observability import (
    _cost_compute_trajectory,
    _cost_format_trajectory,
    _format_kpi_report,
    _kpi_compute_all,
)
from shared import config, notify

log = logging.getLogger("bot")

CALENDAR_REFRESH_TICKERS = config.get_tickers("core") if hasattr(config, "get_tickers") else []


async def weekly_handler_stats_job():
    """Phase Solidification P0 #3 — Weekly handler usage summary, Sunday 23:00 Paris."""
    try:
        import sqlite3 as _sql

        from shared import notify as _notify, storage as _storage

        conn = _sql.connect(_storage._DB_PATH)
        conn.row_factory = _sql.Row
        rows = conn.execute(
            "SELECT handler_name, COUNT(*) AS n FROM handler_calls "
            "WHERE timestamp >= datetime('now', '-7 days') "
            "GROUP BY handler_name ORDER BY n DESC"
        ).fetchall()
        conn.close()
        if not rows:
            return
        total = sum(r["n"] for r in rows)
        lines = [f"WEEKLY HANDLER STATS — {total} calls / {len(rows)} unique"]
        for r in rows[:15]:
            lines.append(f"  {r['handler_name']:24s} {r['n']:4d}")
        # Optional: detect handlers never called
        _notify.send_text("\n".join(lines))
    except Exception as e:
        log.warning(f"weekly_handler_stats_job error: {e}")


async def weekly_kpi_status_job():
    """Phase Solidification P2 — Weekly KPI status, Sunday 23:00 Paris."""
    try:
        from shared import notify as _notify

        kpis = _kpi_compute_all()
        msg = _format_kpi_report(kpis)
        _notify.send_text(msg)
        log.info("weekly_kpi_status_job: posted")
    except Exception as e:
        log.warning(f"weekly_kpi_status_job error: {e}")


async def weekly_cost_summary_job():
    """Phase Solidification P2 — Weekly cost summary, Sunday 22:00 Paris."""
    try:
        from shared import notify as _notify

        data = _cost_compute_trajectory()
        msg = _cost_format_trajectory(data)
        _notify.send_text(msg)
        log.info(f"weekly_cost_summary_job: posted (projection ${data['projection']:.2f})")
        # Alert if RED
        if "🚨 RED" in data["status"]:
            _notify.send_text(
                f"⚠️ ALERT: Projected month-end ${data['projection']:.2f} exceeds 90% of ${config.BUDGET_MONTHLY_USD:.0f} budget"
            )
    except Exception as e:
        log.warning(f"weekly_cost_summary_job error: {e}")


async def refresh_source_half_lives_job():
    """Phase A4 — Weekly: refresh half-life per source from forward price windows."""
    log.info("Refresh source half-lives starting")
    try:
        from intelligence import half_life as hl_mod

        results = hl_mod.refresh_all_source_half_lives(min_samples=3)
        persisted = sum(1 for r in results.values() if r.get("persisted"))
        log.info(f"Half-lives refreshed: {persisted}/{len(results)} sources updated")
    except Exception as e:
        log.exception(f"refresh_source_half_lives_job crashed: {e}")


async def weekly_v2_vigilance_check_job():
    """Cron weekly : check les 3 vigilances V2 (watch-rate, prob spread, insider clusters alive).

    Push Telegram UNIQUEMENT si une vigilance ALERT/WARN -- pas de spam si tout sain.
    Cf intelligence/v2_vigilance.py + decision_log/01_calibration_unanchored.md
    sections 'Trois vigilances pour la suite'.
    """
    log.info("V2 vigilance check starting")
    try:
        from intelligence import v2_vigilance

        results = v2_vigilance.run_all_vigilances()
        msg = v2_vigilance.format_vigilance_report(results)

        # Log toutes les vigilances (status detail) pour debug
        for r in results:
            log.info(f"vigilance {r['name']} status={r['status']} -- {r['message']}")

        if msg:
            try:
                notify.send_text(msg)
                log.info(f"V2 vigilance alert envoyee (length={len(msg)})")
            except Exception as e:
                log.warning(f"v2_vigilance: telegram send failed: {e}")
        else:
            log.info("V2 vigilance : tout sain, pas de push")
    except Exception as e:
        log.exception(f"weekly_v2_vigilance_check_job crashed: {e}")


async def recalibrate_credibility_brier_job():
    """Phase A1 — Monthly cron: recalibrate sources.credibility from rolling Brier scores."""
    log.info("Brier credibility recalibration starting")
    try:
        from shared import storage as storage_mod

        updates = storage_mod.recalibrate_source_credibility_from_hitrate(min_n=10)
        if updates:
            lines = [f"Brier recalibration: {len(updates)} sources updated"]
            for name, (old, new, n) in sorted(updates.items(), key=lambda x: x[1][1], reverse=True):
                delta = new - old
                arrow = "↑" if delta > 0.01 else ("↓" if delta < -0.01 else "→")
                lines.append(f"  {name}: {old:.2f} {arrow} {new:.2f} (Δ{delta:+.2f}, n={n})")
            try:
                notify.send_text("\n".join(lines))
            except Exception as e:
                log.warning(f"brier_recal: telegram send failed: {e}")
        log.info(f"Brier recalibration done: {len(updates)} sources updated")
    except Exception as e:
        log.exception(f"recalibrate_credibility_brier_job crashed: {e}")
