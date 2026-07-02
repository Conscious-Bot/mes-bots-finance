"""Entrypoint bot. Long-running async."""

import atexit
import contextlib
import fcntl
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

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


# Cron jobs extracted to bot/jobs (Phase A 21/05/2026, split par fréquence Phase C).
# Imports par sous-module : source de vérité = où le job est DÉFINI, pas un
# 2e référentiel de ré-exports dans bot/jobs/__init__.py. Cure #128 (12/06/2026) :
# les ré-exports eager dans __init__ tiraient pandas/yfinance/google/data_sources
# au package-level, cassant la storage-only-ness de tout sous-module (resolver,
# E2E pièce 6, etc.). Cure radicale : __init__ vidé, imports directs ici.
from bot.jobs.daily import (
    daily_backup_job,
    daily_calendar_refresh_job,
    daily_counterfactual_resolve_job,
    daily_crypto_zone_job,
    daily_decision_anniversary_job,
    daily_digest_job,
    daily_kill_criteria_check_job,
    daily_portfolio_grade_job,
    daily_resolve_job,
    daily_risk_signal_monitor_job,
    monthly_bot_preferences_synthesis_job,
    resolve_copilot_interventions_30d_job,
    resolve_journal_decisions_job,
    scheduled_8k_scan_job,
    scheduled_buy_cluster_scan_job,
    scheduled_insider_refresh_job,
    scheduled_resolve_buy_cluster_returns_job,
    weekly_bot_conceptions_synthesis_job,
    weekly_data_clusters_synthesis_job,
    weekly_portfolio_narrative_synthesis_job,
    weekly_user_profile_refresh_job,
)
from bot.jobs.intervals import (
    event_driven_erosion_check_job,
    heartbeat,
    ingest_gmail_job,
    price_monitor_job,
    scheduled_classify_signal_types_job,
    scheduled_materiality_v2_job,
    scheduled_recompute_materiality_boost_job,
    score_pending_signals_job,
    update_echo_clusters_job,
)
from bot.jobs.periodic import (
    monthly_track_record_snapshot_job,
    recalibrate_credibility_brier_job,
    refresh_source_half_lives_job,
    weekly_calibration_audit_job,
    weekly_cost_summary_job,
    weekly_handler_stats_job,
    weekly_kpi_status_job,
    weekly_thesis_erosion_floor_job,
    weekly_v2_vigilance_check_job,
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
    # GATE INVARIANTS au demarrage (point #9 brief : echec fort).
    # Si le book est incoherent on log + on continue en mode degrade,
    # mais on ne demarre pas silencieusement sur du sable.
    try:
        from shared import notify as _notify, storage as _stg

        violations = _stg.assert_book_invariants(strict=False)
        if violations:
            log.error(f"🚨 BOOK INVARIANTS VIOLATIONS au demarrage ({len(violations)}) :")
            for v in violations[:10]:
                log.error(f"  ❌ {v}")
            # Notif Telegram (fix audit 31/05 : silencieux avant -> log only)
            try:
                msg = (
                    f"🚨 PRESAGE bot startup : {len(violations)} gate violation(s) detectee(s).\n\n"
                    + "\n".join(f"• {v[:200]}" for v in violations[:5])
                    + (f"\n\n... +{len(violations) - 5} violations supplementaires" if len(violations) > 5 else "")
                    + "\n\nGate vert attendu. Investigation requise avant trade."
                )
                _notify.send_text(msg)
                log.info("Telegram alert envoyee pour gate red")
            except Exception as ne:
                log.warning(f"Telegram alert gate red failed: {ne}")
        else:
            log.info("🟢 Book invariants : tous verts au demarrage")
    except Exception as e:
        log.error(f"position_invariants gate crashed: {e}")

    try:
        n = seed_macro_events()
        log.info(f"Macro events seeded ({n} upcoming)")
    except Exception as e:
        log.warning(f"seed_macro_events failed: {e}")
    # job_defaults: coalesce=True ensures missed instances on laptop sleep
    # don't catch-up storm post-wake; misfire_grace_time=3600s = run if <1h late.
    # Critical cron jobs (backup, digest) override with larger grace below.
    from shared.env import env as _env_singleton
    sched = AsyncIOScheduler(
        timezone=_env_singleton.timezone,
        job_defaults={"coalesce": True, "misfire_grace_time": 3600},
    )
    # === JOBS AUTONOMES (intervals + cron sans dependance fonctionnelle) ===
    sched.add_job(heartbeat, "interval", hours=1)
    sched.add_job(ingest_gmail_job, "interval", hours=1)
    sched.add_job(price_monitor_job, "cron", hour="14-22", minute="*/15", day_of_week="mon-fri")
    # OBSOLÈTE depuis migration 0048 : positions est une VUE, last_price_*/fx_* viennent
    # de price_history + fx_history via JOIN. Le cron qui populait ces champs en UPDATE
    # positions n'a plus de raison d'être ET échouerait sur la VUE. Désactivé.
    # sched.add_job(_reconcile_positions_prices_job, "cron", ...)  # cf SPEC_LEDGER §2.2
    # Axe 4 QUALITY_BAR : stress-gate daily check + notify si breach.
    # Daily 7:00 : le book bouge lentement, in-session not needed.
    sched.add_job(_stress_gate_check_job, "cron", hour=7, minute=0)

    # Kill-condition disjoncteur grappe AI-compute (26/06/2026, doctrine V3).
    # 3 jobs : snapshot daily 21:50 (close US), check toutes les 15min (cache prix),
    # escalade 7:05 avant /brief.
    from risk import kill_switch
    sched.add_job(kill_switch.snapshot_cluster_value, "cron", hour=21, minute=50,
                  id="kill_snapshot", replace_existing=True)
    sched.add_job(kill_switch.check_and_fire, "interval", minutes=15,
                  id="kill_check", replace_existing=True)
    sched.add_job(kill_switch.escalate_unresolved, "cron", hour=7, minute=5,
                  id="kill_escalate", replace_existing=True)
    sched.add_job(daily_calendar_refresh_job, "cron", hour=5, minute=0)
    sched.add_job(daily_backup_job, "cron", hour=4, minute=0, misfire_grace_time=14400)
    # SOCLE S0 : OTS anchor chain-head daily 6h. Cf SPEC_SOCLE.md S5 + HANDOFF_SOCLE.md.
    # Lignage = integrite (Merkle-DAG). Track-record provable -- chaque jour compte.
    from bot.jobs.integrity_anchor import integrity_anchor_daily_job
    # Stagger 06:00 pile-up (cure 15/06/2026 audit cron) : morning_chain
    # garde 06:00, les autres jobs decales 06:03/06:05/06:07/06:10 pour
    # eviter contention DB write + LLM call simultanes au tick exact.
    sched.add_job(integrity_anchor_daily_job, "cron", hour=6, minute=3,
                  misfire_grace_time=7200)
    sched.add_job(daily_crypto_zone_job, "cron", hour=10, minute=0)
    sched.add_job(recalibrate_credibility_brier_job, "cron", day=1, hour=6, minute=7)
    # #89 cadence mensuelle : snapshot JSON + recal credibility V2 + digest Telegram
    sched.add_job(monthly_track_record_snapshot_job, "cron", day=1, hour=8, minute=0,
                  misfire_grace_time=86400)
    # #13 J-day 10/06 : SUPPRIME 14/06/2026 (date passee + execute one-shot).
    # APScheduler ignore deja le run_date past + outside grace, mais le code
    # garde un add_job zombie qui pollue. Cure : retirer. Si nouveau J-day
    # batch needed, ressusciter avec nouvelle date dans commit dedie.
    # V2 vigilances : check hebdo lundi 7h, push Telegram UNIQUEMENT si ALERT/WARN
    sched.add_job(weekly_v2_vigilance_check_job, "cron", day_of_week="mon", hour=7, minute=0,
                  misfire_grace_time=86400)
    # Couche 4 chantier #2 : weekly floor thesis_erosion lundi 6h Paris
    # (avant ouverture marche, donne verdicts frais pour la carte-decision).
    # Cout ~$0.60/run x 4 runs/mois = ~$2.40/mois. Pas spam Telegram si tout INTACT.
    sched.add_job(weekly_thesis_erosion_floor_job, "cron", day_of_week="mon", hour=6, minute=5,
                  misfire_grace_time=86400)  # 24h catchup post-downtime (cure 12/06)
    # Calibration audit scorer V2 : check hebdo dimanche 22h, push Telegram si transition status notable
    sched.add_job(weekly_calibration_audit_job, "cron", day_of_week="sun", hour=22, minute=0,
                  misfire_grace_time=86400)
    sched.add_job(monthly_bot_preferences_synthesis_job, "cron", day=1, hour=4, minute=0, misfire_grace_time=86400)
    # Tier1 4x/jour 06h/12h/18h/22h (user 06/06 "accuracy = basic").
    # VIX/USDJPY/TYX/MOVE/HY_OAS/DXY/Gold/BTC reagissent intra-day.
    sched.add_job(cron_tier1_daily, "cron", hour="6,12,18,22", minute=10,
                  misfire_grace_time=10800)  # 3h catchup. minute=10 = stagger post-morning_chain 06:00
    sched.add_job(cron_tier2_weekly, "cron", day_of_week="mon", hour=6, minute=30,
                  misfire_grace_time=86400)  # 24h catchup (cf cure 12/06 : missed lundi -> 6j stale)
    # Tier3 monthly retry pattern : 1er + 5 + 10 + 15 du mois pour rattraper
    # les FRED-pas-encore-publies (CPI publish ~mid-month). persist_signal
    # ne stomp plus NULL = derniere valeur valide preserved.
    sched.add_job(cron_tier3_monthly, "cron", day="1,5,10,15", hour=7, minute=0)
    # 06/06 Friction décision #2 : retrospective +30j/+90j sur position_decisions_context.
    # 9h30 = post market open EU + assez de marge pour cron_tier1 06h finir.
    from intelligence.retrospective_decisions import cron_retrospective_daily
    sched.add_job(cron_retrospective_daily, "cron", hour=9, minute=30)
    # 06/06 v5 audit pro : portfolio circuit breaker Elder (-6%/mois).
    # 9h45 = apres retrospective + apres market open.
    from intelligence.circuit_breaker import cron_circuit_breaker_daily
    sched.add_job(cron_circuit_breaker_daily, "cron", hour=9, minute=45)
    # 06/06 Phase B : audit_calibration_job 10j (evolutif refresh).
    # 8h00 = avant marche, faible charge cron. Daily check, fire si >= 10j.
    from intelligence.audit_calibration import cron_audit_calibration_daily
    sched.add_job(cron_audit_calibration_daily, "cron", hour=8, minute=0)
    sched.add_job(daily_digest_job, "cron", hour=19, minute=0, misfire_grace_time=7200)  # digest soir reste isole

    # === CHAINES SEQUENCEES (soudure ④ brief) ===
    # Avant : 22+ jobs independants par heure -> race conditions
    # Maintenant : 3 chaines orchestrent en sequence avec dependances explicites
    from bot.jobs.sequences import (
        evening_chain,
        morning_chain,
        weekly_chain_saturday,
        weekly_chain_sunday,
    )

    # Morning chain (6h-9h) : insiders -> filings -> score -> digest -> monitors -> resolves
    sched.add_job(morning_chain, "cron", hour=6, minute=0, misfire_grace_time=14400)
    # Evening chain (23h) : snapshot -> grade -> counterfactual_resolve
    sched.add_job(evening_chain, "cron", hour=23, minute=0, misfire_grace_time=14400)
    # Weekly chains
    sched.add_job(weekly_chain_saturday, "cron", day_of_week="sat", hour=18, minute=0,
                  misfire_grace_time=86400)
    sched.add_job(weekly_chain_sunday, "cron", day_of_week="sun", hour=19, minute=0,
                  misfire_grace_time=86400)
    # NOTE 14/06/2026 : tier1/2/3 add_job retires ici (etaient duplicates lignes 288-295).
    # Audit cron 14/06 a detecte : APScheduler genere UUID auto sans id= explicite =>
    # 2 instances independantes firaient en parallele => tier1 8x/jour au lieu de 4x
    # (2x LLM cost macro signals). Defini une fois pour toutes en debut de cette section.
    # 05/06 : espacements crons pour reduire pression LLM + DB write sans perte coverage.
    # classify 30min->2h, recompute_boost 1h->6h, materiality_v2 1h->6h.
    # safety-net : ingest_gmail_job chain materiality_v2 immediat apres ingestion,
    # donc le cron standalone est juste catch-up de stragglers.
    sched.add_job(scheduled_classify_signal_types_job, "interval", hours=2)
    sched.add_job(scheduled_recompute_materiality_boost_job, "interval", hours=6)
    sched.add_job(scheduled_materiality_v2_job, "interval", hours=6)
    # Etape 3 chantier #2 : event-driven trigger thesis_erosion 30min.
    # Complemente weekly floor (lundi 6h) avec latence reduite quand evidence
    # arrive en cours de semaine. Diff verdict notable -> push Telegram.
    # Cost ~$0.20/jour si flow normal (~10 signaux materiels/jour).
    sched.add_job(event_driven_erosion_check_job, "interval", minutes=30)
    sched.start()
    # Dump real scheduler state (pas une string hardcoded qui drift) -- au moindre
    # add_job manque ou en trop, le log le revele. Critique avant J-day 10/06.
    _job_lines = []
    for j in sched.get_jobs():
        _job_lines.append(f"  - {j.id} -> next_run={j.next_run_time}")
    log.info("Scheduler started with %d jobs:\n%s", len(_job_lines), "\n".join(_job_lines))
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


_LOCK_PATH = Path(__file__).resolve().parent.parent / "data" / "bot.pid"
_LOCK_FH = None


def _reconcile_positions_prices_job() -> None:
    """Axe 5 QUALITY_BAR : reconcile positions M1 columns via single gateway.

    Wrap scripts/reconcile_positions_prices.main() pour APScheduler. Pas
    d'exception remontee a APScheduler (sinon job stoppe), log + silence.
    """
    try:
        from scripts.reconcile_positions_prices import main as reconcile_main
        reconcile_main()
    except Exception as e:
        log.warning(f"reconcile_positions_prices_job failed: {e}")


from shared.scheduler_observability import scheduler_run_logged


@scheduler_run_logged("stress_gate_check_job")
def _stress_gate_check_job() -> None:
    """Axe 4 QUALITY_BAR : stress-gate daily check + notify si breach.

    Wrap intelligence.stress_gate_monitor.check_all_stress_transitions().
    Daily car le book bouge lentement ; in-session pas necessaire.
    """
    try:
        from intelligence import stress_gate_monitor
        out = stress_gate_monitor.check_all_stress_transitions()
        log.info(f"stress_gate_check : {out}")
    except Exception as e:
        log.warning(f"stress_gate_check_job failed: {e}")


def _acquire_mono_instance_lock() -> None:
    """Lock file PID-based pour empecher 2 instances PRESAGE bot en parallele.

    Cause connue : 2 `bot.main` simultanes => Telegram getUpdates Conflict
    (long-polling exclusif). Le tennis bot (`bot.py`, com.olivier.tennisbot
    launchd) est un PROCESS DIFFERENT, lock different, non affecte.

    Approche : fcntl.flock exclusif sur data/bot.pid. Si l'autre instance
    detient le lock -> EXIT 1 propre avec message. Si stale (instance
    crashed sans cleanup), le lock est release par l'OS au close FD.
    """
    global _LOCK_FH
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    # SIM115 noqa : fichier doit rester ouvert toute la duree du process pour
    # que fcntl.flock tienne le lock. Cleanup via atexit ci-dessous.
    _LOCK_FH = open(_LOCK_PATH, "w")  # noqa: SIM115
    try:
        fcntl.flock(_LOCK_FH.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Lock detenu par autre instance.
        try:
            with open(_LOCK_PATH) as f:
                other_pid = f.read().strip() or "?"
        except OSError:
            other_pid = "?"
        sys.stderr.write(
            f"[bot.main] Autre instance PRESAGE detient {_LOCK_PATH} (PID {other_pid}). "
            "Arrete-la d'abord (ou laisse-la tourner). Exit 1.\n"
        )
        sys.exit(1)
    _LOCK_FH.write(str(os.getpid()))
    _LOCK_FH.flush()
    atexit.register(_release_mono_instance_lock)


def _release_mono_instance_lock() -> None:
    """Cleanup au exit propre : release flock + supprime le PID file."""
    global _LOCK_FH
    if _LOCK_FH is None:
        return
    try:
        fcntl.flock(_LOCK_FH.fileno(), fcntl.LOCK_UN)
        _LOCK_FH.close()
    except OSError:
        pass
    with contextlib.suppress(OSError):
        _LOCK_PATH.unlink()
    _LOCK_FH = None


def _check_critical_env_or_refuse() -> None:
    """T0.6 (audit 17/07) : fail-closed au boot. Si ENV=prod et une clé critique
    manque/vide, refuse de démarrer plutôt que tourner en mode dégradé silencieux
    (L15/L21). Empêche 'feature dormante en prod sans signal' (divergence .env
    Mac↔VM invisible). Le flock ne couvre pas ça — c'est une barrière orthogonale."""
    env = (os.environ.get("ENV") or "").lower()
    if env not in ("prod", "production"):
        return
    critical = ["TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY"]
    missing = [k for k in critical if not (os.environ.get(k) or "").strip()]
    if missing:
        sys.stderr.write(
            f"[bot.main] ENV=prod mais clés critiques manquantes : {', '.join(missing)}. "
            "Refuse de démarrer (fail-closed T0.6). Exit 1.\n"
        )
        sys.exit(1)


def _refuse_if_conflicting_poller(token: str | None) -> None:
    """T0.4 (audit 17/07) : refuse de démarrer si une AUTRE instance poll déjà ce
    bot (Telegram Conflict 409). Le long-polling est exclusif CROSS-MACHINE, donc
    le flock local (_acquire_mono_instance_lock) ne peut pas l'attraper — c'est
    précisément le split-brain Mac↔VM du 13/06. Fail-closed : mieux ne pas booter
    qu'entrer dans un split-brain silencieux. Probe best-effort : une erreur réseau
    ne bloque pas le boot (seul un 409 explicite refuse)."""
    if not token:
        return
    import time as _t

    import requests

    def _probe() -> int | None:
        try:
            return requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"timeout": 0, "limit": 1}, timeout=10,
            ).status_code
        except Exception as e:
            log.warning(f"[bot.main] probe Conflict 409 échouée ({e}) — best-effort")
            return None

    # Retry sur 409 : un `systemctl restart` laisse l'ancienne instance relâcher
    # son long-poll pendant ~qq s → 409 TRANSITOIRE. On ne refuse que si le 409
    # PERSISTE (vrai split-brain cross-machine), sinon on bloquerait chaque deploy.
    if _probe() != 409:
        return
    _t.sleep(6)
    if _probe() != 409:
        return
    sys.stderr.write(
        "[bot.main] Telegram Conflict 409 PERSISTANT : une AUTRE instance poll déjà "
        "ce bot (split-brain Mac↔VM ?). Refuse de démarrer. Arrête l'autre poller. Exit 1.\n"
    )
    sys.exit(1)


def main():
    _acquire_mono_instance_lock()
    _check_critical_env_or_refuse()
    storage.log_event("startup", {"phase": "2"})
    config.load()
    log.info(
        f"Bot starting. Tickers: {len(config.get_tickers('core'))} core + {len(config.get_tickers('watch'))} watch + {len(config.get_tickers('extended'))} extended = {len(config.get_tickers('all'))} total"
    )

    _refuse_if_conflicting_poller(config.telegram_token())
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
