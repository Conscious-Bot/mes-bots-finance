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


async def weekly_calibration_audit_job():
    """Cron weekly : check calibration_audit scorer V2 (reliability + Brier moyen).

    Push Telegram UNIQUEMENT si :
    - status devient != INSUFFICIENT_DATA pour la 1ere fois (= seuil n>=30 atteint, premier verdict)
    - status change vs precedent run (ex: OK -> WARN, INSUFFICIENT_DATA -> ALERT)
    - status reste ALERT (rappel chaque semaine tant que pas resolu)

    Etat persiste dans data/calibration_last_status.txt (= simple texte, 1 ligne).
    Pas de spam si tout sain ou si toujours INSUFFICIENT_DATA stable.

    Cf intelligence/calibration_audit.py + CONVENTIONS section "Discipline statistique".
    Aligne pattern weekly_v2_vigilance_check_job (silent-success).
    """
    log.info("Calibration audit check starting")
    try:
        import sqlite3
        from pathlib import Path

        from intelligence import calibration_audit
        from shared import storage as _stg

        cx = sqlite3.connect(_stg.DB_PATH)
        cx.row_factory = sqlite3.Row
        result = calibration_audit.check_scorer_calibration(cx)
        cx.close()

        current_status = result["status"]
        n_total = result.get("n_total", 0)
        log.info(f"calibration_audit status={current_status} n={n_total}")

        # Read last status (state file simple texte 1 ligne)
        state_file = Path(__file__).resolve().parent.parent.parent / "data" / "calibration_last_status.txt"
        last_status = state_file.read_text().strip() if state_file.exists() else None

        # Decide if push Telegram (anti-spam : seulement transitions notables)
        should_push = False
        push_reason = ""
        if current_status == "ALERT":
            should_push = True
            push_reason = "ALERT persistant ou nouvelle alerte"
        elif current_status != last_status:
            if last_status == "INSUFFICIENT_DATA" and current_status != "INSUFFICIENT_DATA":
                should_push = True
                push_reason = f"SEUIL n>=30 ATTEINT premier verdict={current_status}"
            elif current_status in ("WARN", "ALERT"):
                should_push = True
                push_reason = f"status change {last_status} -> {current_status}"
            elif last_status in ("WARN", "ALERT") and current_status == "OK":
                should_push = True
                push_reason = f"recovery {last_status} -> OK"

        if should_push:
            brier = result.get("avg_brier")
            brier_str = f"{brier:.4f}" if brier is not None else "—"
            max_gap = result.get("max_gap_pp", 0)
            msg = (
                f"📊 Calibration scorer V2 — {push_reason}\n"
                f"Status: {current_status}\n"
                f"N résolus: {n_total}\n"
                f"Brier moyen: {brier_str}\n"
                f"Max gap reliability: {max_gap:+.1f}pp\n\n"
                f"{result.get('message', '')}"
            )
            try:
                notify.send_text(msg)
                log.info(f"calibration_audit telegram envoye : {push_reason}")
            except Exception as e:
                log.warning(f"calibration_audit: telegram send failed: {e}")
        else:
            log.info(f"calibration_audit : pas de push ({current_status} stable)")

        # Persist current status
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(current_status)
    except Exception as e:
        log.exception(f"weekly_calibration_audit_job crashed: {e}")


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


async def monthly_track_record_snapshot_job():
    """#89 cadence mensuelle (1er du mois) -- snapshot JSON + recal credibility +
    digest Telegram.

    Coupe la duplication avec recalibrate_credibility_brier_job historique
    (which uses storage layer recalibration). Ce nouveau job utilise
    intelligence.calibration_audit.recalibrate_source_credibility +
    aggregator + timeseries + snapshot JSON dated.

    Idempotent : skip si data/track_record/snapshots/YYYY-MM.json existe.
    Output : digest Telegram court avec posture_global + cumul bias delta.
    """
    log.info("monthly_track_record_snapshot_job starting")
    try:
        import sqlite3 as _sqlite3

        from intelligence.monthly_track_record import run_monthly_track_record_job
        from shared.storage import DB_PATH

        cx = _sqlite3.connect(DB_PATH)
        try:
            result = run_monthly_track_record_job(cx)
        finally:
            cx.close()

        if result.get("skipped"):
            log.info(f"monthly_track_record SKIP {result.get('reason')}")
            return

        # Digest Telegram court
        agg = result.get("aggregator_summary", {})
        recal = result.get("recal_summary", {})
        lines = [
            f"📊 Track record snapshot {result['year_month']}",
            f"Posture: {agg.get('posture_global', '—')}",
            f"Predictions résolues: {agg.get('n_resolved_predictions', 0)}",
            f"Bias delta cumulé: {agg.get('bias_total_delta_eur', 0):+.0f} €",
            f"Thèses actives: {agg.get('n_active_theses', 0)}",
            f"Credibility updates: {recal.get('n_applied', 0)} sources",
            f"Snapshot: {result['snapshot_path']}",
        ]
        try:
            notify.send_text("\n".join(lines))
        except Exception as e:
            log.warning(f"monthly_track_record: telegram send failed: {e}")
        log.info(
            f"monthly_track_record done {result['year_month']} "
            f"posture={agg.get('posture_global')} recal_applied={recal.get('n_applied')}"
        )
    except Exception as e:
        log.exception(f"monthly_track_record_snapshot_job crashed: {e}")
