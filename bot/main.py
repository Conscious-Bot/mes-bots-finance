"""Entrypoint bot. Long-running async."""

import contextlib
import logging
import os
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.handlers.anti_erosion import _append_log_entry, cmd_log_friction, cmd_log_value
from bot.handlers.bias_pattern import cmd_bias_pattern
from bot.handlers.debt_crisis import cmd_debt_alerts, cmd_debt_history, cmd_debt_status
from bot.handlers.digest import cmd_digest
from bot.handlers.echo_crypto_macro import (
    cmd_credit,
    cmd_crypto,
    cmd_echo_recent,
    cmd_macro,
    cmd_materiality,
    cmd_orphan_tickers,
    cmd_override,
    cmd_price_check,
)
from bot.handlers.find import cmd_find
from bot.handlers.journal_audit import cmd_journal_audit
from bot.handlers.journal_bias import (
    cmd_bias_review,
    cmd_history,
    cmd_journal,
    cmd_journal_review,
    cmd_journal_tag,
    cmd_journal_unresolved,
    cmd_position_history,
)
from bot.handlers.misc import cmd_asymmetry, cmd_brief, cmd_position, cmd_thesis_set
from bot.handlers.observability import (
    _cost_compute_trajectory,
    _cost_format_trajectory,
    _format_kpi_report,
    _kpi_compute_all,
    cmd_bot_data,
    cmd_cost_trajectory,
    cmd_handler_stats,
    cmd_health,
    cmd_llm_costs,
)
from bot.handlers.portfolio_views import cmd_portfolio_drift, cmd_portfolio_narratives, cmd_portfolio_sectors
from bot.handlers.positions import _portfolio_journal_ctx, cmd_portfolio, cmd_position_buy, cmd_position_sell
from bot.handlers.predictions import cmd_credibility, cmd_feedback, cmd_predictions, cmd_resolve_now
from bot.handlers.regime_calendar import cmd_calendar, cmd_regime
from bot.handlers.signal_drilldown import cmd_signal_drilldown
from bot.handlers.signals_filings import (
    cmd_eight_k_history,
    cmd_insider_buy_cluster,
    cmd_insider_cluster,
    cmd_insider_digest,
    cmd_insiders,
    cmd_recent_8k,
)
from bot.handlers.sources_admin import (
    cmd_sources,
    cmd_sources_brier,
    cmd_sources_health,
)
from bot.handlers.system import cmd_help, cmd_ping
from bot.handlers.thesis_analyze import (
    cmd_analyze,
    cmd_analyze_debate,
    cmd_risk_check,
    cmd_thesis_premortem,
)
from bot.handlers.thesis_crud import (
    cmd_exit,
    cmd_exit_force,
    cmd_thesis,
    cmd_thesis_add,
    cmd_thesis_list,
    cmd_thesis_note,
    cmd_thesis_revisit,
)
from bot.handlers.thesis_health import cmd_thesis_health
from bot.registry import register_command_handlers
from data_sources import gmail_
from intelligence import (
    analyze as analyze_mod,
    calendar as calendar_mod,
    credibility as credibility_mod,
    digest as digest_mod,
    learning as learning_mod,
    regime as regime_mod,
    thesis as thesis_mod,
)
from intelligence.calendar import format_macro_calendar, seed_macro_events
from intelligence.debt_monitor import cron_tier1_daily, cron_tier2_weekly, cron_tier3_monthly
from intelligence.insider_digest import daily_insider_refresh, format_daily_insider_digest
from intelligence.price_monitor import check_thesis_triggers, list_overrides, record_override
from shared import config, crypto as crypto_mod, edgar as edgar_mod, notify, positions as positions_mod, storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
log = logging.getLogger("bot")

CALENDAR_REFRESH_TICKERS = config.get_tickers("core") if hasattr(config, "get_tickers") else []


# Cron jobs extracted to bot/jobs.py (Phase A refactor 21/05/2026)
from bot.jobs import (
    daily_backup_job,
    daily_calendar_refresh_job,
    daily_crypto_zone_job,
    daily_digest_job,
    daily_kill_criteria_check_job,
    daily_portfolio_grade_job,
    daily_resolve_job,
    heartbeat,
    ingest_gmail_job,
    monthly_bot_preferences_synthesis_job,
    price_monitor_job,
    recalibrate_credibility_brier_job,
    refresh_source_half_lives_job,
    resolve_copilot_interventions_30d_job,
    resolve_journal_decisions_job,
    scheduled_8k_scan_job,
    scheduled_buy_cluster_scan_job,
    scheduled_classify_signal_types_job,
    scheduled_insider_refresh_job,
    scheduled_materiality_v2_job,
    scheduled_recompute_materiality_boost_job,
    scheduled_resolve_buy_cluster_returns_job,
    score_pending_signals_job,
    update_echo_clusters_job,
    weekly_bot_conceptions_synthesis_job,
    weekly_cost_summary_job,
    weekly_data_clusters_synthesis_job,
    weekly_handler_stats_job,
    weekly_kpi_status_job,
    weekly_portfolio_narrative_synthesis_job,
    weekly_user_profile_refresh_job,
)


async def log_handler_call_middleware(update, ctx):
    """Pre-handler middleware: log every command call to handler_calls table.

    Registered in group=-1 to run before all real handlers. Non-blocking failure mode:
    telemetry exceptions never propagate to break the actual command processing.
    """
    try:
        if not (update.message and update.message.text and update.message.text.startswith("/")):
            return
        cmd_text = update.message.text
        handler_name = cmd_text.split()[0].lstrip("/").split("@")[0].lower()
        user_id = update.effective_user.id if update.effective_user else None
        chat_id = update.effective_chat.id if update.effective_chat else None
        args_summary = cmd_text[:200]
        import sqlite3 as _sql

        from shared import storage as _storage

        conn = _sql.connect(_storage._DB_PATH)
        try:
            conn.execute(
                "INSERT INTO handler_calls (handler_name, user_id, chat_id, args_summary) VALUES (?, ?, ?, ?)",
                (handler_name, user_id, chat_id, args_summary),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        log.warning(f"handler telemetry failed: {e}")


async def post_init(app):
    """Run AFTER event loop is started."""
    try:
        n = seed_macro_events()
        log.info(f"Macro events seeded ({n} upcoming)")
    except Exception as e:
        log.warning(f"seed_macro_events failed: {e}")
    # job_defaults: coalesce=True ensures missed instances on laptop sleep
    # don't catch-up storm post-wake; misfire_grace_time=3600s = run if <1h late.
    # Critical cron jobs (backup, digest) override with larger grace below.
    sched = AsyncIOScheduler(
        timezone=os.environ.get("TZ", "Europe/Paris"),
        job_defaults={"coalesce": True, "misfire_grace_time": 3600},
    )
    sched.add_job(heartbeat, "interval", hours=1)
    sched.add_job(ingest_gmail_job, "interval", hours=1)
    sched.add_job(daily_digest_job, "cron", hour="7,19", minute=0, misfire_grace_time=7200)
    sched.add_job(daily_calendar_refresh_job, "cron", hour=5, minute=0)
    sched.add_job(daily_resolve_job, "cron", hour=9, minute=0)
    sched.add_job(resolve_journal_decisions_job, "cron", hour=8, minute=0)
    sched.add_job(resolve_copilot_interventions_30d_job, "cron", hour=9, minute=15)
    sched.add_job(recalibrate_credibility_brier_job, "cron", day=1, hour=6, minute=0)
    sched.add_job(update_echo_clusters_job, "interval", hours=1)
    sched.add_job(score_pending_signals_job, "interval", hours=1)
    sched.add_job(refresh_source_half_lives_job, "cron", day_of_week="sun", hour=5, minute=0)
    sched.add_job(scheduled_insider_refresh_job, "cron", hour=6, minute=0)
    sched.add_job(price_monitor_job, "cron", hour="14-22", minute="*/15", day_of_week="mon-fri")
    sched.add_job(daily_crypto_zone_job, "cron", hour=10, minute=0)
    sched.add_job(scheduled_buy_cluster_scan_job, "cron", hour=6, minute=20)
    sched.add_job(scheduled_resolve_buy_cluster_returns_job, "cron", hour=8, minute=15)
    sched.add_job(scheduled_8k_scan_job, "cron", hour=6, minute=30)
    sched.add_job(daily_backup_job, "cron", hour=4, minute=0, misfire_grace_time=14400)
    from intelligence.snapshot import daily_snapshot_job

    sched.add_job(daily_snapshot_job, "cron", hour=23, minute=0, misfire_grace_time=14400)
    sched.add_job(daily_portfolio_grade_job, "cron", hour=23, minute=15, misfire_grace_time=14400)
    sched.add_job(daily_kill_criteria_check_job, "cron", hour=7, minute=30, misfire_grace_time=14400)
    sched.add_job(weekly_handler_stats_job, "cron", day_of_week="sun", hour=23, minute=0, misfire_grace_time=86400)
    sched.add_job(weekly_kpi_status_job, "cron", day_of_week="sun", hour=22, minute=30, misfire_grace_time=86400)
    sched.add_job(weekly_cost_summary_job, "cron", day_of_week="sun", hour=22, minute=0, misfire_grace_time=86400)
    sched.add_job(weekly_user_profile_refresh_job, "cron", day_of_week="sun", hour=21, minute=0, misfire_grace_time=86400)
    sched.add_job(weekly_portfolio_narrative_synthesis_job, "cron", day_of_week="sun", hour=20, minute=30, misfire_grace_time=86400)
    sched.add_job(weekly_bot_conceptions_synthesis_job, "cron", day_of_week="sun", hour=19, minute=0, misfire_grace_time=86400)
    sched.add_job(weekly_data_clusters_synthesis_job, "cron", day_of_week="sat", hour=18, minute=0, misfire_grace_time=86400)
    sched.add_job(monthly_bot_preferences_synthesis_job, "cron", day=1, hour=4, minute=0, misfire_grace_time=86400)
    sched.add_job(cron_tier1_daily, "cron", hour=6, minute=0)
    sched.add_job(cron_tier2_weekly, "cron", day_of_week="mon", hour=6, minute=30)
    sched.add_job(cron_tier3_monthly, "cron", day=1, hour=7, minute=0)
    sched.add_job(scheduled_classify_signal_types_job, "interval", minutes=30)
    sched.add_job(scheduled_recompute_materiality_boost_job, "interval", hours=1)
    sched.add_job(scheduled_materiality_v2_job, "interval", hours=1)
    sched.start()
    log.info(
        "Scheduler started: heartbeat 1h, gmail 1h, calendar 5h, insider 6h, digest 7h+19h, journal_resolve 8h, resolve 9h, brier_recal 1st 6h, echo_clusters 1h, score_pending 1h, half_life Sun 5h, price_monitor 15min mkt hours, crypto 10h, buy_cluster_scan 6:20, resolve_buy_cluster 8:15, 8k_scan 6:30, backup 4:00, handler_stats Sun 23:00, cost Sun 22:00, kpi_status Sun 22:30, signal_classify 30min, materiality_boost 1h, materiality_v2 1h, debt_tier1 6:00, debt_tier2 Mon 6:30, debt_tier3 1st 7:00, snapshot 23:00"
    )
    notify.send_text("Bot starting - Phase 2 actif (gmail + thesis + digest)")


async def error_handler(update, ctx):
    """Catche toute exception handler/Telegram (sinon swallow silencieux): loggue + notifie."""
    log.error("Telegram handler error", exc_info=ctx.error)
    try:
        chat = getattr(getattr(update, "effective_chat", None), "id", None)
        if chat is not None:
            msg = f"[BOT ERREUR] {type(ctx.error).__name__}: {ctx.error}"
            await ctx.bot.send_message(chat, msg[:3500])
    except Exception:
        log.error("error_handler: echec notification user", exc_info=True)


def main():
    storage.log_event("startup", {"phase": "2"})
    config.load()
    log.info(
        f"Bot starting. Tickers: {len(config.get_tickers('core'))} core + {len(config.get_tickers('watch'))} watch + {len(config.get_tickers('extended'))} extended = {len(config.get_tickers('all'))} total"
    )

    app = Application.builder().token(config.telegram_token()).post_init(post_init).build()
    app.add_error_handler(error_handler)
    # Phase Solidification P0 #3 — handler usage telemetry (middleware in group=-1)
    from telegram.ext import MessageHandler, filters

    app.add_handler(MessageHandler(filters.COMMAND, log_handler_call_middleware), group=-1)
    # Phase B refactor 21/05/2026: 80 command handlers extracted to bot/registry.py
    register_command_handlers(app)

    log.info("Polling Telegram...")
    storage.update_state(bot_start_ts=datetime.now(UTC).isoformat())
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
