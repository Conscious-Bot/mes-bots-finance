"""Entrypoint bot. Long-running async."""

import contextlib
import logging
import os
from datetime import UTC

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.handlers.anti_erosion import _append_log_entry, cmd_log_friction, cmd_log_value
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
from bot.handlers.observability import (
    _cost_compute_trajectory,
    _cost_format_trajectory,
    _format_kpi_report,
    _kpi_compute_all,
    cmd_cost_trajectory,
    cmd_handler_stats,
    cmd_health,
    cmd_kpi_status,
    cmd_llm_costs,
)
from bot.handlers.portfolio_views import (
    cmd_portfolio_drift,
    cmd_portfolio_narratives,
    cmd_portfolio_sectors,
)
from bot.handlers.positions import (
    _portfolio_journal_ctx,
    cmd_portfolio,
    cmd_position_buy,
    cmd_position_sell,
)
from bot.handlers.signal_drilldown import cmd_signal_drilldown
from bot.handlers.signals_filings import (
    cmd_eight_k_history,
    cmd_insider_buy_cluster,
    cmd_insider_buy_cluster_stats,
    cmd_insider_cluster,
    cmd_insider_digest,
    cmd_recent_8k,
    cmd_signals_by_type,
)
from bot.handlers.sources_admin import (
    cmd_promote,
    cmd_sources_brier,
    cmd_sources_half_life,
    cmd_sources_health,
    cmd_tiers,
    cmd_tiers_watch,
)
from bot.handlers.thesis_analyze import (
    cmd_analyze,
    cmd_analyze_debate,
    cmd_debate_replay,
    cmd_risk_check,
    cmd_thesis_premortem,
)
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
from intelligence.insider_digest import daily_insider_refresh, format_daily_insider_digest
from intelligence.price_monitor import check_thesis_triggers, list_overrides, record_override
from shared import config, crypto as crypto_mod, edgar as edgar_mod, notify, positions as positions_mod, storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
log = logging.getLogger("bot")

THESIS_TEMPLATE = (
    "Format thesis_add (copie-colle, remplace les valeurs) :\n\n"
    "/thesis_add\n"
    "ticker: NVDA\n"
    "direction: long\n"
    "horizon: 24m\n"
    "conviction: 4\n"
    "drivers: AI capex growth >40%; HBM supply constraint; CUDA moat\n"
    "invalidation: revenue Q/Q <20%; major customer defection; CUDA alternative success\n"
    "profit_take: revenue growth peak; PE >55x; margin compression\n"
    "entry_price: 130\n"
    "target_partial: 250\n"
    "target_full: 350\n"
    "notes: AI infra primary play\n\n"
    "Multi-item: separer par ';'"
)

def _parse_thesis_template(text):
    out = {}
    for line in text.split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        val = val.strip()
        if val:
            out[key] = val
    return out

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = storage.load_state()
    await update.message.reply_text(
        f"alive\n"
        f"capital: ${state['current_capital']:.0f}\n"
        f"drawdown: {state['drawdown_pct']:.1%}\n"
        f"theses actives: {state['active_theses_count']}\n"
        f"paper_only: {state['paper_only']}"
    )

async def cmd_thesis_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    body_split = text.split(maxsplit=1)
    body = body_split[1] if len(body_split) > 1 else ""
    if not body.strip():
        await update.message.reply_text(THESIS_TEMPLATE)
        return
    params = _parse_thesis_template(body)
    if "ticker" not in params or "entry_price" not in params:
        await update.message.reply_text("Manque 'ticker' et/ou 'entry_price'. Tape /thesis_add seul pour le template.")
        return
    try:
        result = thesis_mod.add_thesis(
            ticker=params["ticker"],
            direction=params.get("direction", "long"),
            horizon=params.get("horizon", "12m"),
            conviction=int(params.get("conviction", 3)),
            key_drivers=params.get("drivers", ""),
            invalidation_triggers=params.get("invalidation", ""),
            entry_price=float(params["entry_price"]),
            target_partial=float(params["target_partial"]) if "target_partial" in params else None,
            target_full=float(params["target_full"]) if "target_full" in params else None,
            triggers_profit_take=params.get("profit_take", ""),
            notes=params.get("notes", ""),
        )
        msg = f"OK these #{result['thesis_id']} ajoutee pour {result['ticker']}"
        if result["warnings"]:
            msg += "\n\nWarnings:\n" + "\n".join(f"  - {w}" for w in result["warnings"])
        await update.message.reply_text(msg)
        if result.get("pre_mortem_display"):
            pm_msg = result["pre_mortem_display"]
            if len(pm_msg) > 3900:
                pm_msg = pm_msg[:3900] + "\n[truncated]"
            await update.message.reply_text(pm_msg)
    except (KeyError, ValueError) as e:
        await update.message.reply_text(f"Erreur: {e}\n\nTape /thesis_add seul pour le template.")

async def cmd_thesis_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = thesis_mod.list_active()
    # Telegram hard limit 4096 chars; chunk on paragraph boundaries if needed
    if len(msg) <= 3900:
        await update.message.reply_text(msg)
        return
    chunks = []
    cur = ""
    for para in msg.split("\n\n"):
        if len(cur) + len(para) + 2 < 3900:
            cur = cur + "\n\n" + para if cur else para
        else:
            if cur:
                chunks.append(cur)
            cur = para
    if cur:
        chunks.append(cur)
    for c in chunks:
        await update.message.reply_text(c)

async def cmd_thesis_revisit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    due = thesis_mod.get_revisit_due()
    if not due:
        await update.message.reply_text("Aucune these en attente de revisit mensuel.")
        return
    await update.message.reply_text(f"{len(due)} these(s) en attente de revisit :")
    for t in due:
        questions = thesis_mod.build_revisit_questions(t)
        await update.message.reply_text(questions)
        storage.update_thesis_revisit(t["id"])

async def cmd_exit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /exit TICKER [current_price]")
        return
    ticker = ctx.args[0].upper()
    current_price = None
    if len(ctx.args) > 1:
        try:
            current_price = float(ctx.args[1])
        except ValueError:
            await update.message.reply_text(f"Prix invalide: {ctx.args[1]}")
            return
    result = thesis_mod.check_exit_request(ticker, current_price)
    await update.message.reply_text(result["message"])

async def cmd_exit_force(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text("Usage: /exit_force TICKER <raison>")
        return
    ticker = ctx.args[0].upper()
    reason = " ".join(ctx.args[1:])
    t = storage.get_thesis_by_ticker(ticker, status="active")
    if not t:
        await update.message.reply_text(f"Pas de these active sur {ticker}.")
        return
    check = thesis_mod.check_exit_request(ticker)
    note_suffix = "[regret_driven]" if check["status"] == "no_trigger" else "[trigger_met]"
    storage.close_thesis(t["id"], status="realized", reason=f"{note_suffix} {reason}")
    await update.message.reply_text(f"OK these {ticker} fermee 'realized' {note_suffix}\nRaison: {reason}")

async def cmd_thesis_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text("Usage: /thesis_note <thesis_id> <ta note>")
        return
    try:
        thesis_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text(f"thesis_id invalide: {ctx.args[0]}")
        return
    note = " ".join(ctx.args[1:])
    storage.append_thesis_note(thesis_id, note)
    await update.message.reply_text(f"Note ajoutee a these #{thesis_id}.")

async def cmd_digest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split()
    hours = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 24
    await update.message.reply_text(f"Synthese unifiee en cours ({hours}h) ~30s...")
    try:
        from intelligence import digest as _digest_mod

        narrative = _digest_mod.generate_unified_digest(since_hours=hours, max_signals=40)
    except Exception as e:
        await update.message.reply_text(f"Digest failed: {type(e).__name__}: {e}")
        return
    if len(narrative) > 3900:
        chunks = []
        cur = ""
        for para in narrative.split("\n\n"):
            if len(cur) + len(para) + 2 < 3900:
                cur = cur + "\n\n" + para if cur else para
            else:
                if cur:
                    chunks.append(cur)
                cur = para
        if cur:
            chunks.append(cur)
        for c in chunks:
            await update.message.reply_text(c)
    else:
        await update.message.reply_text(narrative)

async def cmd_feedback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text(
            "Usage: /feedback <signal_id> <up|down>\nEx: /feedback 42 up\n(signal_id affiches dans le digest avec prefix #)"
        )
        return
    try:
        signal_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text(f"signal_id invalide: {ctx.args[0]}")
        return
    rating = ctx.args[1].lower()
    if rating not in ("up", "down"):
        await update.message.reply_text(f"rating doit etre up ou down, got: {rating}")
        return
    try:
        result = credibility_mod.apply_feedback(signal_id, rating)
        old = result.get("old_credibility") or 0.5
        new = result.get("new_credibility") or 0.5
        src = (result.get("source_name") or "?")[:40]
        msg = f"OK feedback {rating} sur signal #{signal_id}.\nSource: {src}\nCredibility: {old:.2f} -> {new:.2f} (delta {result['delta']:+.2f})"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Erreur: {type(e).__name__}: {e}")

async def cmd_credibility(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = credibility_mod.list_top_sources(n=10)
    msg += "\n\n" + credibility_mod.list_worst_sources(n=5)
    await update.message.reply_text(msg)

async def cmd_predictions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    preds = storage.get_recent_predictions(limit=15)
    if not preds:
        await update.message.reply_text("Aucune prediction enregistree.")
        return
    lines = ["Predictions recentes:"]
    for p in preds:
        ticker = p.get("ticker", "?")
        dir_ = (p.get("direction") or "?")[:4]
        baseline = p.get("baseline_price") or 0
        target = p.get("target_date", "?")
        outcome = p.get("outcome") or "pending"
        ret = p.get("return_pct")
        if ret is not None:
            lines.append(f"#{p['id']} {ticker} {dir_} ${baseline:.2f} -> {ret * 100:+.1f}% [{outcome}]")
        else:
            lines.append(f"#{p['id']} {ticker} {dir_} ${baseline:.2f} target {target} [pending]")
    await update.message.reply_text("\n".join(lines))

async def cmd_resolve_now(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Resolution en cours...")
    try:
        results = learning_mod.resolve_due_predictions()
        msg = learning_mod.format_resolve_report(results)
        await update.message.reply_text(msg[:4000])
    except Exception as e:
        await update.message.reply_text(f"Erreur: {type(e).__name__}: {e}")

async def resolve_journal_decisions_job():
    """Phase 18 Batch 3 — Daily cron: resolve J+30 and J+90 pending decisions.
    Computes current price + return + thesis_relative + auto-classifies mistake_tag.
    Notifies Telegram if any decisions resolved.
    """
    log.info("Resolve journal decisions starting")
    try:
        import sqlite3 as _sql

        import yfinance as yf

        from intelligence import journal as journal_mod
        from shared import storage as storage_mod

        total_30 = 0
        total_90 = 0
        summaries = []

        for horizon in (30, 90):
            unres = storage_mod.get_unresolved_decisions(horizon)
            for d in unres:
                ticker = d["ticker"]
                try:
                    info = yf.Ticker(ticker).info or {}
                    price_now = info.get("regularMarketPrice") or info.get("currentPrice")
                except Exception as e:
                    log.warning(f"resolve_journal: yfinance failed for {ticker}: {e}")
                    continue

                if not price_now or not d.get("price_at_decision"):
                    log.warning(f"resolve_journal: missing prices for #{d['id']} {ticker}")
                    continue

                p0 = d["price_at_decision"]
                ret = (price_now / p0) - 1.0

                thesis_rel = None
                if d.get("thesis_id"):
                    try:
                        conn = _sql.connect("data/bot.db")
                        conn.row_factory = _sql.Row
                        trow = conn.execute("SELECT * FROM theses WHERE id=?", (d["thesis_id"],)).fetchone()
                        conn.close()
                        if trow:
                            thesis_rel = journal_mod.thesis_relative_position(price_now, dict(trow))
                    except Exception as e:
                        log.warning(f"resolve_journal: thesis fetch failed: {e}")

                tag = journal_mod.auto_classify_mistake(d, price_now, horizon)

                try:
                    storage_mod.resolve_decision(d["id"], horizon, price_now, ret, thesis_rel, tag)
                except Exception as e:
                    log.error(f"resolve_journal: persist failed #{d['id']}: {e}")
                    continue

                if horizon == 30:
                    total_30 += 1
                else:
                    total_90 += 1

                summaries.append(
                    f"#{d['id']} {ticker} [{d['decision_type']}] J+{horizon}: "
                    f"${p0:.2f} -> ${price_now:.2f} ({ret * 100:+.1f}%) -> {tag}"
                )

        if total_30 + total_90 > 0:
            msg_parts = [f"Journal auto-resolved: {total_30} J+30 + {total_90} J+90"]
            msg_parts.extend(summaries[:10])
            if len(summaries) > 10:
                msg_parts.append(f"... ({len(summaries) - 10} more, use /journal_review)")
            try:
                notify.send_text("\n".join(msg_parts))
            except Exception as e:
                log.warning(f"resolve_journal: telegram send failed: {e}")

        log.info(f"Resolve journal decisions done: {total_30} J+30, {total_90} J+90 resolved")
    except Exception as e:
        log.exception(f"resolve_journal_decisions_job crashed: {e}")

async def daily_resolve_job():
    log.info("Daily resolve predictions starting")
    try:
        results = learning_mod.resolve_due_predictions()
        if results.get("resolved", 0) > 0:
            msg = learning_mod.format_resolve_report(results)
            notify.send_text(msg)
        log.info(f"Daily resolve done: {results.get('resolved', 0)} predictions")
    except Exception as e:
        log.error(f"Daily resolve failed: {e}")

async def cmd_regime(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Detection regime en cours (5-10s)...")
    try:
        r = regime_mod.detect_regime()
        msg = regime_mod.format_regime(r)
        await update.message.reply_text(msg[:4000])
    except Exception as e:
        await update.message.reply_text(f"Erreur: {type(e).__name__}: {e}")

# Phase Tickers Tiered — dynamic from config.yaml universe.core
CALENDAR_REFRESH_TICKERS = config.get_tickers("core") if hasattr(config, "get_tickers") else []

async def cmd_calendar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    events = storage.get_upcoming_events(days_ahead=60)
    msg = calendar_mod.format_calendar(events, days_ahead=60)
    alerts = calendar_mod.get_pre_event_thesis_alerts(days_ahead=14)
    alert_msg = calendar_mod.format_alerts(alerts)
    if alert_msg:
        msg = alert_msg + "\n\n---\n\n" + msg
    await update.message.reply_text(msg[:4000])

async def cmd_calendar_refresh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Refresh calendar sur {len(CALENDAR_REFRESH_TICKERS)} tickers (60-90s)...")
    try:
        n = calendar_mod.refresh_earnings_calendar(CALENDAR_REFRESH_TICKERS)
        events = storage.get_upcoming_events(days_ahead=60)
        msg = f"OK {n} events upserted.\n\n" + calendar_mod.format_calendar(events, days_ahead=60)
        await update.message.reply_text(msg[:4000])
    except Exception as e:
        await update.message.reply_text(f"Erreur: {type(e).__name__}: {e}")

async def daily_calendar_refresh_job():
    log.info("Daily calendar refresh starting")
    try:
        n = calendar_mod.refresh_earnings_calendar(CALENDAR_REFRESH_TICKERS)
        log.info(f"Calendar refreshed: {n} events")
        alerts = calendar_mod.get_pre_event_thesis_alerts(days_ahead=7)
        alert_msg = calendar_mod.format_alerts(alerts)
        if alert_msg:
            notify.send_text(alert_msg)
            log.info(f"Sent {len(alerts)} pre-event alerts")
    except Exception as e:
        log.error(f"Daily calendar refresh failed: {e}")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show categorized list of all 65 registered commands."""
    help_text = """mes-bots-finance — 65 commands (consolidation V4 spec'd Sprint 1.2)

DAILY RITUAL (6)
  /brief             Morning briefing (6 sections)
  /health            Bot health snapshot
  /ping              Liveness probe
  /digest            Run digest pipeline now
  /log_value <msg>   Log a moment the bot helped
  /log_friction <msg> Log a friction

THESES (8)
  /thesis_list       List active theses (chunked)
  /thesis_add        Create new thesis
  /thesis_set        Set thesis params
  /thesis_note       Add note
  /thesis_revisit    Monthly revisit
  /thesis_premortem  Pre-mortem analysis
  /exit TICKER       Check exit triggers
  /exit_force        Force-close (regret-tagged)

POSITIONS (8)
  /portfolio         View positions w/ PnL
  /position TICKER   Drill-down
  /position_buy      Record buy + journal
  /position_sell     Record sell + journal
  /position_set      Set position manually
  /position_history  Event log
  /orphan_tickers    Holdings w/o thesis
  /override          Manual override

ANALYSIS (6)
  /analyze TICKER    Deep analysis (Opus, $0.20)
  /analyze_debate    Multi-round debate
  /debate_replay     Replay debate
  /asymmetry TICKER  Anti-sell-too-early math
  /risk_check        Risk premortem (Opus reads journal+biases)
  /materiality       Materiality (no args=top5, INT=signal_id, TICKER=last 5)

JOURNAL (9)
  /journal           View decision journal
  /journal_review    Review unresolved
  /journal_unresolved List unresolved
  /journal_tag       Tag with bias
  /bias_review       Bias patterns
  /history TICKER    Position/thesis history
  /predictions       Pending predictions
  /resolve_now       Force-resolve due
  /feedback          Submit feedback

SIGNALS & SOURCES (9)
  /echo_recent       Recent echo clusters
  /signals_by_type   Filter signals
  /credibility       Source credibility
  /sources_brier     Brier per source
  /sources_half_life Source decay rates
  /sources_health    Source freshness
  /tiers             Source tier ranking
  /tiers_watch       Watch tier changes
  /promote           Promote tier

MARKET (7)
  /macro             Macro snapshot
  /regime            Current regime
  /credit            Credit / HY OAS
  /crypto            Crypto zone
  /price_check TICK  Live price
  /calendar          Upcoming events
  /calendar_refresh  Force refresh

INSIDERS (7)
  /insiders          Recent activity
  /insider_cluster   Cluster analysis
  /insider_buy_cluster      Buy-cluster only
  /insider_buy_cluster_stats Stats
  /insider_digest    Daily digest
  /recent_8k         Recent 8-K filings
  /eight_k_history   Historical 8-K

OPS & MONITORING (5)
  /kpi_status        KPI dashboard
  /cost_trajectory   LLM cost + budget
  /llm_costs         Operational LLM costs
  /handler_stats     Handler usage telemetry
  /help              This message

Spec V4: 65 -> 18 handlers in Sprint 1.2 (post 2026-06-10).
See docs/personal/handlers-consolidation-plan.md
"""
    await update.message.reply_text(help_text)

async def cmd_insiders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /insiders TICKER\nEx: /insiders NVDA")
        return
    ticker = ctx.args[0].upper()
    await update.message.reply_text(f"Fetching Form 4 insiders {ticker} (15-30s, sleep entre fetches)...")
    try:
        activity = edgar_mod.get_insider_activity(ticker, days=90)
        msg = edgar_mod.format_insider_summary(activity)
        await update.message.reply_text(msg[:4000])
    except Exception as e:
        await update.message.reply_text(f"Erreur: {type(e).__name__}: {e}")

# === Scheduled jobs ===

async def heartbeat():
    storage.update_state()
    log.info("heartbeat ok")

async def ingest_gmail_job():
    """Hourly Gmail ingestion + immediate materiality_v2 chaining.

    Phase Solidification P1 #2: rubric scoring runs RIGHT after ingestion to keep
    coverage high regardless of cron timing. The standalone cron materiality_v2 1h
    remains as catch-up safety net for any stragglers.
    """
    try:
        stats = gmail_.ingest_new_emails(max_results=50)
        if stats["new_ingested"]:
            log.info(f"gmail ingest: +{stats['new_ingested']} new emails")
            # Chain materiality_v2 immediately - score what was just ingested + small buffer
            try:
                from intelligence import materiality_v2

                target = min(stats["new_ingested"] + 5, 30)  # cap at 30 to avoid cost spike
                s, f, total = materiality_v2.score_pending_signals_v2(limit=target)
                if total > 0:
                    log.info(f"materiality_v2 chained: {s}/{total} scored, {f} failed")
            except Exception as e:
                log.warning(f"materiality_v2 chain error: {e}")
    except Exception as e:
        log.error(f"gmail ingest failed: {e}")

async def daily_digest_job():
    """Auto-trigger unified digest synthesis (12h interval = 2x/jour)."""
    try:
        from intelligence import digest as _digest_mod
        from shared import notify as _notify

        narrative = _digest_mod.generate_unified_digest(since_hours=12, max_signals=30)
        if narrative and not narrative.startswith("Aucun signal"):
            msg = "DIGEST AUTO (12h)\n\n" + narrative
            if len(msg) > 3900:
                msg = msg[:3900] + "\n[truncated]"
            _notify.send_text(msg)
    except Exception as e:
        log.warning(f"daily_digest_job error: {e}")

async def daily_backup_job():
    """Phase Solidification P0 #2 — Daily backup via scripts/backup.sh.
    Runs 04:00 Paris before any market activity. Tarball + DB snapshot + 14d rotation.
    """
    try:
        import os as _os
        import subprocess
        from pathlib import Path as _Path

        proj = str(_Path(__file__).resolve().parent.parent)
        result = subprocess.run(
            ["bash", "scripts/backup.sh"],
            cwd=proj,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode == 0:
            log.info("daily_backup_job: success")
        else:
            log.error(f"daily_backup_job FAILED code={result.returncode} stderr={result.stderr[:300]}")
    except Exception as e:
        log.error(f"daily_backup_job exception: {e}")

# ============ Phase Solidification P0 #3 — Handler usage telemetry ============

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

# ============ Phase Solidification P2 — KPI Status monitoring ============

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

# ============ Phase Solidification P2 — Cost trajectory dashboard ============

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

async def recalibrate_credibility_brier_job():
    """Phase A1 — Monthly cron: recalibrate sources.credibility from rolling Brier scores."""
    log.info("Brier credibility recalibration starting")
    try:
        from shared import storage as storage_mod

        updates = storage_mod.recalibrate_source_credibility_from_brier(min_n=10)
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

async def update_echo_clusters_job():
    """Phase A3 — Hourly: embed pending signals + compute echo clusters in 48h window."""
    log.info("Echo clusters update starting")
    try:
        from shared import echo as echo_mod, embeddings as emb_mod, storage as storage_mod

        pending = storage_mod.get_unembedded_signals(limit=100)
        if pending:
            txts = [(p.get("text_for_embed") or "")[:500] for p in pending]
            vecs = emb_mod.embed_batch(txts)
            for p, v in zip(pending, vecs):
                blob = emb_mod.serialize(v)
                storage_mod.store_signal_embedding(p["id"], blob, emb_mod.model_name())
            log.info(f"Embedded {len(pending)} pending signals")

        clusters = echo_mod.compute_clusters(window_hours=48, sim_threshold=0.85)
        echo_mod.persist_clusters(clusters)
        multi = [c for c in clusters if c["n_unique_sources"] >= 2]
        log.info(f"Echo clusters done: {len(clusters)} total, {len(multi)} multi-source")
    except Exception as e:
        log.exception(f"update_echo_clusters_job crashed: {e}")

async def score_pending_signals_job():
    """Phase data-quality fix — Hourly: score signals with entities IS NULL.
    Drains backlog of signals that the daily digest (limit=20/day) didn't cover.
    """
    log.info("Score pending signals starting")
    try:
        from intelligence import digest as digest_mod

        results = digest_mod.process_unprocessed(limit=50)
        if results:
            n_with_tickers = sum(1 for r in results if r.get("tickers"))
            n_errors = sum(1 for r in results if r.get("error"))
            log.info(
                f"Score pending: processed {len(results)} signals, {n_with_tickers} with tickers, {n_errors} LLM errors"
            )
    except Exception as e:
        log.exception(f"score_pending_signals_job crashed: {e}")

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

async def scheduled_8k_scan_job():
    """Phase C9 — Daily cron 6:30: scan watchlist for new 8-K filings, push high+catastrophic alerts."""
    from intelligence import filings_8k

    insider_list = None
    for name in ("INSIDER_TICKERS", "WATCHLIST_INSIDERS"):
        try:
            mod = __import__("shared.config", fromlist=[name])
            insider_list = getattr(mod, name)
            break
        except ImportError, AttributeError:
            pass
    if insider_list is None:
        from shared.config import WATCHLIST

        insider_list = WATCHLIST[:15]
    try:
        new_logged = filings_8k.scan_and_log_8k_filings(insider_list, days=7)
    except Exception as e:
        log.warning(f"8-K scan error: {e}")
        return
    alerts = [r for r in new_logged if r["severity"] in ("catastrophic", "high")]
    if alerts:
        msg = f"8-K ALERTS ({len(alerts)} high+catastrophic)\n\n"
        for r in alerts:
            msg += filings_8k.format_8k_alert(r) + "\n\n"
        notify.send_text(msg.strip())
    log.info(f"8-K scan: {len(new_logged)} new logged, {len(alerts)} alerted")

async def cmd_asymmetry(update, ctx):
    """Phase C13 — Show asymmetry ratio for thesis. Usage: /asymmetry [TICKER]"""
    parts = update.message.text.split()
    from intelligence import asymmetry as asym_mod
    from shared import storage as storage_mod

    if len(parts) >= 2:
        ticker = parts[1].upper()
        thesis = storage_mod.get_thesis_by_ticker(ticker, status="active")
        if not thesis:
            await update.message.reply_text(f"No active thesis for {ticker}.")
            return
        await update.message.reply_text(f"Computing asymmetry on {ticker}...")
        r = asym_mod.compute_thesis_asymmetry(thesis)
        msg = asym_mod.format_asymmetry_single(r)
    else:
        await update.message.reply_text("Computing portfolio-wide asymmetry...")
        results = asym_mod.compute_portfolio_asymmetry()
        msg = asym_mod.format_portfolio_asymmetry(results)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)

async def cmd_brief(update, ctx):
    """Phase Brief — Morning ritual aggregator."""
    await update.message.reply_text("Building morning brief (10-20s)...")
    try:
        from intelligence import morning_brief as mb

        brief = mb.build_brief()
        chunks = mb.format_brief(brief)
        for c in chunks:
            if len(c) > 3900:
                c = c[:3900] + "\n[truncated]"
            await update.message.reply_text(c)
    except Exception as e:
        log.warning(f"brief error: {e}")
        await update.message.reply_text(f"Brief failed: {e}")

async def scheduled_classify_signal_types_job():
    """Phase Digestion 3a — Classify signals with signal_type=NULL every 30min."""
    try:
        from intelligence import signal_classify

        n_classified, types = signal_classify.classify_pending_signals(limit=30)
        if n_classified > 0:
            log.info(f"signal_type classifier: {n_classified} classified, distribution={types}")
    except Exception as e:
        log.warning(f"classify_signal_types_job error: {e}")

async def scheduled_recompute_materiality_boost_job():
    """Phase Digestion 3b — Recompute corroboration multipliers after echo clusters update."""
    try:
        from intelligence import materiality_boost

        n = materiality_boost.recompute_boosts_for_clustered_signals()
        if n > 0:
            log.info(f"materiality_boost: {n} signals re-boosted")
    except Exception as e:
        log.warning(f"recompute_boost_job error: {e}")

async def scheduled_materiality_v2_job():
    """Phase Digestion 3c — Score signals with structured rubric every 1h."""
    try:
        from intelligence import materiality_v2

        s, f, total = materiality_v2.score_pending_signals_v2(limit=30)
        if total > 0:
            log.info(f"materiality_v2: {s} scored, {f} failed of {total}")
    except Exception as e:
        log.warning(f"materiality_v2_job error: {e}")

async def post_init(app):
    """Run AFTER event loop is started."""
    try:
        n = seed_macro_events()
        log.info(f"Macro events seeded ({n} upcoming)")
    except Exception as e:
        log.warning(f"seed_macro_events failed: {e}")
    sched = AsyncIOScheduler(timezone=os.environ.get("TZ", "Europe/Paris"))
    sched.add_job(heartbeat, "interval", hours=1)
    sched.add_job(ingest_gmail_job, "interval", hours=1)
    sched.add_job(daily_digest_job, "cron", hour="7,19", minute=0)
    sched.add_job(daily_calendar_refresh_job, "cron", hour=5, minute=0)
    sched.add_job(daily_resolve_job, "cron", hour=9, minute=0)
    sched.add_job(resolve_journal_decisions_job, "cron", hour=8, minute=0)
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
    sched.add_job(daily_backup_job, "cron", hour=4, minute=0)
    sched.add_job(weekly_handler_stats_job, "cron", day_of_week="sun", hour=23, minute=0)
    sched.add_job(weekly_kpi_status_job, "cron", day_of_week="sun", hour=22, minute=30)
    sched.add_job(weekly_cost_summary_job, "cron", day_of_week="sun", hour=22, minute=0)
    sched.add_job(scheduled_classify_signal_types_job, "interval", minutes=30)
    sched.add_job(scheduled_recompute_materiality_boost_job, "interval", hours=1)
    sched.add_job(scheduled_materiality_v2_job, "interval", hours=1)
    sched.start()
    log.info(
        "Scheduler started: heartbeat 1h, gmail 1h, calendar 5h, insider 6h, digest 7h+19h, journal_resolve 8h, resolve 9h, brier_recal 1st 6h, echo_clusters 1h, score_pending 1h, half_life Sun 5h, price_monitor 15min mkt hours, crypto 10h, buy_cluster_scan 6:20, resolve_buy_cluster 8:15, 8k_scan 6:30, backup 4:00, handler_stats Sun 23:00, cost Sun 22:00, kpi_status Sun 22:30, signal_classify 30min, materiality_boost 1h, materiality_v2 1h"
    )
    notify.send_text("Bot starting - Phase 2 actif (gmail + thesis + digest)")

async def scheduled_insider_refresh_job():
    """Cron: 6h Paris daily — refresh + post if anything notable."""
    try:
        result = daily_insider_refresh()
        msg = format_daily_insider_digest(result)
        notify.send_text(msg)
        log.info(f"scheduled_insider_refresh: {result['refreshed']} tickers, {len(result['alerts'])} alerts")
    except Exception as e:
        log.error(f"scheduled_insider_refresh failed: {e}")

async def price_monitor_job():
    """Cron 15min mkt hours: check active theses for price crossings."""
    try:
        r = check_thesis_triggers()
        if r["alerts"]:
            log.info(f"price_monitor: {len(r['alerts'])} alerts fired: {r['alerts']}")
        if r["fails"]:
            log.warning(f"price_monitor: failed tickers: {r['fails']}")
    except Exception as e:
        log.error(f"price_monitor_job: {e}")

async def daily_crypto_zone_job():
    """Cron daily 10h Paris : check crypto zone, alert if extreme. Includes position context."""
    try:
        z = crypto_mod.compute_crypto_zone()
        msg = crypto_mod.format_crypto_zone(z)

        # Add user's crypto exposure if any
        try:
            crypto_tickers = ["BTC-USD", "ETH-USD", "MSTR", "IBIT", "ETHA", "COIN"]
            holdings = []
            for tk in crypto_tickers:
                p = positions_mod.get_position(tk)
                if p and p.get("qty", 0) > 0:
                    holdings.append(p)
            if holdings:
                mv_total = sum(p.get("market_value") or 0 for p in holdings)
                msg += "\n\n📊 Your crypto exposure:"
                for p in holdings:
                    mv = p.get("market_value") or 0
                    msg += f"\n  {p['ticker']:8s} qty={p.get('qty', 0):.3f}  MV=${mv:,.0f}"
                msg += f"\n  Total: ${mv_total:,.0f}"
        except Exception as e:
            log.warning(f"crypto position lookup: {e}")

        if z.get("zone") in ("TOP-ZONE", "BOTTOM-ZONE"):
            notify.send_text(f"🚨 CRYPTO ALERT\n\n{msg}")
            log.info(f"crypto alert fired: {z['zone']}")
        else:
            log.info(f"crypto zone daily check: {z.get('zone', 'unknown')} — no alert")
    except Exception as e:
        log.error(f"daily_crypto_zone_job: {e}")

async def cmd_position_set(update, ctx):
    """Bootstrap position: /position_set TICKER QTY AVG_COST [notes]"""
    parts = update.message.text.split(maxsplit=4)
    if len(parts) < 4:
        await update.message.reply_text("Usage: /position_set <TICKER> <QTY> <AVG_COST> [notes]")
        return
    try:
        ticker, qty, avg = parts[1].upper(), float(parts[2]), float(parts[3])
        notes = parts[4] if len(parts) > 4 else None
        positions_mod.set_position(ticker, qty, avg, notes)
        await update.message.reply_text(f"✓ Position set: {ticker} qty={qty:.3f} @ ${avg:.2f}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def cmd_position(update, ctx):
    """Detail: /position TICKER"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /position <TICKER>")
        return
    try:
        ticker = parts[1].upper()
        p = positions_mod.get_position(ticker)
        if not p:
            await update.message.reply_text(f"No open position for {ticker}")
            return
        hist = positions_mod.get_history(ticker)
        await update.message.reply_text(positions_mod.format_position_detail(p, hist))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def cmd_thesis_set(update, ctx):
    """Edit a field on active thesis: /thesis_set TICKER field value"""
    parts = update.message.text.split(maxsplit=3)
    if len(parts) < 4:
        await update.message.reply_text(
            "Usage: /thesis_set <TICKER> <field> <value>\n\n"
            "Editable numeric: target_price, target_partial, target_full, stop_price, entry_price, conviction\n"
            "Editable text:    notes, horizon, key_drivers, invalidation_triggers, triggers_profit_take, status\n\n"
            "Examples:\n"
            "  /thesis_set NVDA target_partial 260\n"
            "  /thesis_set NVDA stop_price 175\n"
            "  /thesis_set NVDA notes 'Post-earnings re-eval'"
        )
        return
    ticker, field, value = parts[1].upper(), parts[2].lower(), parts[3]
    EDITABLE_NUM = {"target_price", "target_partial", "target_full", "stop_price", "entry_price", "conviction"}
    EDITABLE_TEXT = {
        "notes",
        "horizon",
        "key_drivers",
        "invalidation_triggers",
        "triggers_profit_take",
        "status",
        "direction",
    }
    if field not in EDITABLE_NUM | EDITABLE_TEXT:
        await update.message.reply_text(
            f"Field '{field}' not editable.\nAllowed: {sorted(EDITABLE_NUM | EDITABLE_TEXT)}"
        )
        return
    if field in EDITABLE_NUM:
        try:
            value = float(value) if field != "conviction" else int(value)
        except ValueError:
            await update.message.reply_text(f"'{parts[3]}' is not a valid number for {field}")
            return
    from shared.storage import db

    with db() as cx:
        r = cx.execute("SELECT id FROM theses WHERE ticker=? AND status='active'", (ticker,)).fetchone()
        if not r:
            await update.message.reply_text(f"No active thesis for {ticker}")
            return
        old = cx.execute(f"SELECT {field} FROM theses WHERE id=?", (r["id"],)).fetchone()
        old_val = old[0] if old else None
        cx.execute(f"UPDATE theses SET {field}=?, last_reviewed=CURRENT_TIMESTAMP WHERE id=?", (value, r["id"]))
        cx.commit()
    await update.message.reply_text(f"✓ {ticker} {field}: {old_val} → {value}")

async def scheduled_buy_cluster_scan_job():
    """Daily scan: detect + log + alert on new BUY clusters (CMP 30d window, 7d dedup)."""
    from intelligence import insider_buy_cluster as ibc

    insider_list = None
    for name in ("INSIDER_TICKERS", "WATCHLIST_INSIDERS"):
        try:
            mod = __import__("shared.config", fromlist=[name])
            insider_list = getattr(mod, name)
            break
        except ImportError, AttributeError:
            pass
    if insider_list is None:
        from shared.config import WATCHLIST

        insider_list = WATCHLIST[:15]
    try:
        found = ibc.detect_and_log_buy_clusters(insider_list, window_days=30, dedup_days=7)
    except Exception as e:
        log.warning("buy cluster scan error: " + str(e))
        return
    if found:
        msg = "INSIDER BUY CLUSTERS DETECTED (30d, CMP-grade)\n\n"
        for c in found:
            msg += edgar_mod.format_insider_cluster(c) + "\n\n"
        msg += "Tracked for empirical return at J+30, J+90. View: /insider_buy_cluster_stats"
        notify.send_text(msg)
    else:
        log.info("Daily buy cluster scan: no new clusters logged")

async def scheduled_resolve_buy_cluster_returns_job():
    """Daily cron: resolve return_30d and return_90d for pending BUY clusters."""
    from intelligence import insider_buy_cluster as ibc

    try:
        r30 = ibc.resolve_pending_returns(30)
        r90 = ibc.resolve_pending_returns(90)
        if r30 or r90:
            log.info(f"buy cluster resolve: J+30 n={len(r30)}, J+90 n={len(r90)}")
            if r30:
                lines = ["BUY clusters resolved J+30:"]
                for r in r30[:5]:
                    lines.append(f"  {r['ticker']} id={r['id']}: {r['return']:+.2%}")
                notify.send_text("\n".join(lines))
            if r90:
                lines = ["BUY clusters resolved J+90:"]
                for r in r90[:5]:
                    lines.append(f"  {r['ticker']} id={r['id']}: {r['return']:+.2%}")
                notify.send_text("\n".join(lines))
    except Exception as e:
        log.warning(f"resolve buy cluster returns error: {e}")

def main():
    storage.log_event("startup", {"phase": "2"})
    config.load()
    log.info(
        f"Bot starting. Tickers: {len(config.get_tickers('core'))} core + {len(config.get_tickers('watch'))} watch + {len(config.get_tickers('extended'))} extended = {len(config.get_tickers('all'))} total"
    )

    app = Application.builder().token(config.telegram_token()).post_init(post_init).build()
    # Phase Solidification P0 #3 — handler usage telemetry (middleware in group=-1)
    from telegram.ext import MessageHandler, filters

    app.add_handler(MessageHandler(filters.COMMAND, log_handler_call_middleware), group=-1)
    app.add_handler(CommandHandler("log_value", cmd_log_value))
    app.add_handler(CommandHandler("log_friction", cmd_log_friction))
    app.add_handler(CommandHandler("find", cmd_find))
    app.add_handler(CommandHandler("portfolio_sectors", cmd_portfolio_sectors))
    app.add_handler(CommandHandler("portfolio_narratives", cmd_portfolio_narratives))
    app.add_handler(CommandHandler("portfolio_drift", cmd_portfolio_drift))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("handler_stats", cmd_handler_stats))
    app.add_handler(CommandHandler("kpi_status", cmd_kpi_status))
    app.add_handler(CommandHandler("cost_trajectory", cmd_cost_trajectory))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("thesis_add", cmd_thesis_add))
    app.add_handler(CommandHandler("thesis_list", cmd_thesis_list))
    app.add_handler(CommandHandler("thesis_revisit", cmd_thesis_revisit))
    app.add_handler(CommandHandler("thesis_set", cmd_thesis_set))
    app.add_handler(CommandHandler("exit", cmd_exit))
    app.add_handler(CommandHandler("exit_force", cmd_exit_force))
    app.add_handler(CommandHandler("thesis_note", cmd_thesis_note))
    app.add_handler(CommandHandler("thesis_premortem", cmd_thesis_premortem))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("feedback", cmd_feedback))
    app.add_handler(CommandHandler("credibility", cmd_credibility))
    app.add_handler(CommandHandler("predictions", cmd_predictions))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("resolve_now", cmd_resolve_now))
    app.add_handler(CommandHandler("regime", cmd_regime))
    app.add_handler(CommandHandler("credit", cmd_credit))
    app.add_handler(CommandHandler("materiality", cmd_materiality))
    app.add_handler(CommandHandler("sources_health", cmd_sources_health))
    app.add_handler(CommandHandler("orphan_tickers", cmd_orphan_tickers))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("journal", cmd_journal))
    app.add_handler(CommandHandler("journal_review", cmd_journal_review))
    app.add_handler(CommandHandler("journal_audit", cmd_journal_audit))
    app.add_handler(CommandHandler("signal_drilldown", cmd_signal_drilldown))
    app.add_handler(CommandHandler("journal_unresolved", cmd_journal_unresolved))
    app.add_handler(CommandHandler("journal_tag", cmd_journal_tag))
    app.add_handler(CommandHandler("sources_brier", cmd_sources_brier))
    app.add_handler(CommandHandler("llm_costs", cmd_llm_costs))
    app.add_handler(CommandHandler("echo_recent", cmd_echo_recent))
    app.add_handler(CommandHandler("sources_half_life", cmd_sources_half_life))
    app.add_handler(CommandHandler("position_buy", cmd_position_buy))
    app.add_handler(CommandHandler("position_sell", cmd_position_sell))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("position_history", cmd_position_history))
    app.add_handler(CommandHandler("bias_review", cmd_bias_review))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    app.add_handler(CommandHandler("calendar_refresh", cmd_calendar_refresh))
    app.add_handler(CommandHandler("insiders", cmd_insiders))
    app.add_handler(CommandHandler("macro", cmd_macro))
    app.add_handler(CommandHandler("insider_digest", cmd_insider_digest))
    app.add_handler(CommandHandler("insider_cluster", cmd_insider_cluster))
    app.add_handler(CommandHandler("insider_buy_cluster", cmd_insider_buy_cluster))
    app.add_handler(CommandHandler("insider_buy_cluster_stats", cmd_insider_buy_cluster_stats))
    app.add_handler(CommandHandler("recent_8k", cmd_recent_8k))
    app.add_handler(CommandHandler("eight_k_history", cmd_eight_k_history))
    app.add_handler(CommandHandler("analyze_debate", cmd_analyze_debate))
    app.add_handler(CommandHandler("debate_replay", cmd_debate_replay))
    app.add_handler(CommandHandler("risk_check", cmd_risk_check))
    app.add_handler(CommandHandler("tiers", cmd_tiers))
    app.add_handler(CommandHandler("tiers_watch", cmd_tiers_watch))
    app.add_handler(CommandHandler("promote", cmd_promote))
    app.add_handler(CommandHandler("asymmetry", cmd_asymmetry))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("signals_by_type", cmd_signals_by_type))
    app.add_handler(CommandHandler("price_check", cmd_price_check))
    app.add_handler(CommandHandler("override", cmd_override))
    app.add_handler(CommandHandler("crypto", cmd_crypto))
    app.add_handler(CommandHandler("position_set", cmd_position_set))
    app.add_handler(CommandHandler("position", cmd_position))
    app.add_handler(CommandHandler("analyze", cmd_analyze))

    log.info("Polling Telegram...")
    app.run_polling()

if __name__ == "__main__":
    main()
