"""Entrypoint bot. Long-running async."""

import contextlib
import logging
import os
from datetime import UTC

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

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
    await update.message.reply_text(msg)


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
    """Show categorized list of all available commands."""
    help_text = """mes-bots-finance — Commands (61 handlers)

=== DAILY RITUAL ===
/brief             Morning briefing (6 sections)
/health            Bot health snapshot
/ping              Liveness probe
/log_value <msg>   Log a moment the bot helped
/log_friction <msg> Log a friction
/digest            Run digest pipeline now

=== THESES ===
/thesis_add        Create a new thesis
/thesis_list       List active theses
/thesis_set        Set thesis params
/thesis_note       Add note to thesis
/thesis_revisit    Trigger monthly revisit
/thesis_premortem  Pre-mortem analysis

=== POSITIONS ===
/position_buy      Record a buy + journal
/position_sell     Record a sell + journal
/portfolio         View positions w/ concentration & PnL
/position TICKER   Drill-down single ticker + history
/position_set      Set position params manually
/position_history  Position event log
/orphan_tickers    Holdings without thesis
/exit TICKER       Check exit trigger status
/exit_force TICKER reason  Force-close thesis (regret-tagged)

=== ANALYSIS DEEP-WORK ===
/analyze TICKER    Deep ticker analysis (Opus)
/analyze_debate    Multi-round debate
/debate_replay     Replay previous debate
/asymmetry TICKER  Anti-sell-too-early math
/risk_check TICKER SIDE USD  Risk premortem
/materiality       Materiality (no args=top5, INT=signal_id, TICKER=last 5)

=== DECISIONS & JOURNAL ===
/journal           View decision journal
/journal_review    Review unresolved decisions
/journal_tag       Tag a decision with bias
/journal_unresolved  List unresolved decisions
/bias_review       Bias patterns
/history TICKER    Position/thesis history
/predictions       Pending predictions
/resolve_now       Force-resolve due predictions
/feedback          Submit feedback

=== SIGNALS & SOURCES ===
/echo_recent       Recent echo clusters
/signals_by_type   Filter signals by type
/credibility       Source credibility scores
/sources_brier     Brier score per source
/sources_half_life Source decay rates
/sources_health    Source freshness
/tiers             Source tier ranking (S/A/B)
/tiers_watch       Watch tier changes
/promote TICKER tier  Promote tier

=== MARKET CONTEXT ===
/macro             Macro snapshot
/regime            Current regime
/credit            Credit spread / HY OAS
/crypto            Crypto zone
/price_check TICKER  Live price
/calendar          Upcoming events
/calendar_refresh  Force refresh

=== INSIDERS & FILINGS ===
/insiders          Recent insider activity
/insider_cluster   Cluster analysis (full)
/insider_buy_cluster  Buy-cluster only
/insider_buy_cluster_stats  Stats
/insider_digest    Daily insider digest
/recent_8k         Recent 8-K filings

=== MONITORING & OPS ===
/kpi_status        KPI dashboard
/cost_trajectory   LLM cost over time
/handler_stats     Handler usage stats
/llm_costs         LLM cost breakdown

=== ADMIN ===
/override [TICKER level reason]  List or create override
/help              This help

----
J+28 cleanup remaining: insider_cluster vs buy_cluster merge,
journal_unresolved -> /journal flag, cost duplicates,
exit naming clarity, LOW-conf telemetry-driven deletions."""
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




def _append_log_entry(filename: str, message: str) -> None:
    """Append a timestamped entry to a log file at the repo root."""
    from datetime import datetime
    from pathlib import Path as _Path
    repo_root = _Path(__file__).resolve().parent.parent
    log_path = repo_root / filename
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {message}\n")


async def cmd_log_value(update, ctx):
    """Append entry to VALUE_LOG.md. Usage: /log_value <message>"""
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text(
            "Usage: /log_value <message>\n"
            "Exemple: /log_value bot m'a alerte sur 8K NVDA avant que je le rate"
        )
        return
    try:
        _append_log_entry("VALUE_LOG.md", text)
        await update.message.reply_text(f"OK logged to VALUE_LOG.md:\n  {text[:300]}")
    except Exception as e:
        await update.message.reply_text(f"Error writing VALUE_LOG.md: {e}")


async def cmd_log_friction(update, ctx):
    """Append entry to friction.md. Usage: /log_friction <message>"""
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text(
            "Usage: /log_friction <message>\n"
            "Exemple: /log_friction /brief lent ce matin (15s)"
        )
        return
    try:
        _append_log_entry("friction.md", text)
        await update.message.reply_text(f"OK logged to friction.md:\n  {text[:300]}")
    except Exception as e:
        await update.message.reply_text(f"Error writing friction.md: {e}")


async def cmd_health(update, ctx):
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


async def cmd_handler_stats(update, ctx):
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


async def cmd_kpi_status(update, ctx):
    """Phase Solidification P2 — Show KPI status with breach detection."""
    try:
        kpis = _kpi_compute_all()
        msg = _format_kpi_report(kpis)
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        log.error(f"cmd_kpi_status error: {e}")
        await update.message.reply_text(f"KPI status error: {e}")


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

BUDGET_MONTHLY_USD = 50.0  # Target monthly LLM spend (per FICHE_TECHNIQUE)


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


async def cmd_cost_trajectory(update, ctx):
    """Phase Solidification P2 — Strategic cost dashboard avec MTD + projection + budget."""
    try:
        data = _cost_compute_trajectory()
        msg = _cost_format_trajectory(data)
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        log.error(f"cmd_cost_trajectory error: {e}")
        await update.message.reply_text(f"Error: {e}")


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
                f"⚠️ ALERT: Projected month-end ${data['projection']:.2f} exceeds 90% of ${BUDGET_MONTHLY_USD:.0f} budget"
            )
    except Exception as e:
        log.warning(f"weekly_cost_summary_job error: {e}")


async def cmd_sources_health(update, ctx):
    """Health check newsletter sources."""
    import sqlite3
    from datetime import datetime, timezone

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


async def cmd_orphan_tickers(update, ctx):
    """Tickers in signals (30d) NOT in watchlist."""
    import json
    import re
    import sqlite3
    from collections import Counter

    watchlist = set()
    # Strategy 1: shared.config exposed function
    for fn_name in ["load", "get", "get_config"]:
        try:
            from shared import config as cfg_mod

            fn = getattr(cfg_mod, fn_name, None)
            if fn:
                cfg = fn()
                wl = (cfg or {}).get("universe", {}).get("watchlist")
                if wl:
                    watchlist = {t.upper() for t in wl}
                    break
        except Exception:
            continue
    # Strategy 2: cached _config singleton
    if not watchlist:
        try:
            from shared import config as cfg_mod

            cfg = getattr(cfg_mod, "_config", None)
            if cfg:
                wl = cfg.get("universe", {}).get("watchlist")
                if wl:
                    watchlist = {t.upper() for t in wl}
        except Exception:
            pass
    # Strategy 3: direct YAML read
    if not watchlist:
        try:
            from pathlib import Path

            import yaml

            here = Path(__file__).parent
            for parent in [here, here.parent, here.parent.parent]:
                candidate = parent / "config.yaml"
                if candidate.exists():
                    cfg = yaml.safe_load(candidate.read_text())
                    wl = (cfg or {}).get("universe", {}).get("watchlist")
                    if wl:
                        watchlist = {t.upper() for t in wl}
                    break
        except Exception:
            pass
    if not watchlist:
        await update.message.reply_text("Could not load watchlist from any source")
        return
    BLACKLIST = {
        "AI",
        "IA",
        "USD",
        "HTML",
        "JSON",
        "OK",
        "OS",
        "CEO",
        "CFO",
        "GPU",
        "CPU",
        "AGI",
        "ML",
        "DL",
        "API",
        "TPU",
        "CN",
        "US",
        "EU",
        "UK",
        "FED",
        "ETF",
        "IPO",
        "PE",
        "ROE",
        "NA",
        "ON",
    }
    conn = sqlite3.connect("data/bot.db")
    try:
        rows = conn.execute("""
            SELECT entities FROM signals
            WHERE entities IS NOT NULL AND entities != '[]'
              AND timestamp > datetime('now', '-30 days')
        """).fetchall()
    finally:
        conn.close()
    counter = Counter()
    for (entities_json,) in rows:
        try:
            ts = json.loads(entities_json) if entities_json else []
            for t in ts:
                t = t.upper().strip()
                if not re.match(r"^[A-Z]{1,5}(-USD)?$", t):
                    continue
                if t in watchlist or t in BLACKLIST:
                    continue
                counter[t] += 1
        except Exception:
            continue
    if not counter:
        await update.message.reply_text("No orphan tickers detected (last 30d)")
        return
    top = counter.most_common(15)
    lines = ["Orphan tickers (in signals, NOT in watchlist, 30d):\n"]
    for ticker, count in top:
        lines.append(f"  {ticker:<8} {count} mention(s)")
    lines.append(f"\nTotal distinct orphans: {len(counter)}")
    await update.message.reply_text("\n".join(lines))


async def cmd_history(update, ctx):
    """Historical context for a ticker."""
    import sqlite3

    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /history TICKER")
        return
    ticker = parts[1].upper().strip()
    conn = sqlite3.connect("data/bot.db")
    try:
        theses = conn.execute(
            """
            SELECT direction, entry_price, target_partial, target_full, stop_price,
                   status, opened_at, last_price, conviction
            FROM theses WHERE ticker=? ORDER BY opened_at DESC LIMIT 3
        """,
            (ticker,),
        ).fetchall()
        ins_90 = conn.execute(
            """
            SELECT net_m, total_buys_m, total_sells_m, n_buys, n_sells, snapshot_date
            FROM insider_snapshots
            WHERE ticker=? AND snapshot_date > date('now', '-90 days')
            ORDER BY snapshot_date DESC LIMIT 1
        """,
            (ticker,),
        ).fetchone()
        ins_365 = conn.execute(
            """
            SELECT SUM(net_m), SUM(total_buys_m), SUM(total_sells_m)
            FROM insider_snapshots
            WHERE ticker=? AND snapshot_date > date('now', '-365 days')
        """,
            (ticker,),
        ).fetchone()
        preds = conn.execute(
            """
            SELECT direction, horizon_days, baseline_price, final_price, return_pct,
                   outcome, baseline_date
            FROM predictions WHERE ticker=? ORDER BY baseline_date DESC LIMIT 5
        """,
            (ticker,),
        ).fetchall()
        sig_30 = conn.execute(
            """
            SELECT COUNT(*) FROM signals
            WHERE entities LIKE ? AND timestamp > datetime('now', '-30 days')
        """,
            (f'%"{ticker}"%',),
        ).fetchone()[0]
        sig_90 = conn.execute(
            """
            SELECT COUNT(*) FROM signals
            WHERE entities LIKE ? AND timestamp > datetime('now', '-90 days')
        """,
            (f'%"{ticker}"%',),
        ).fetchone()[0]
        material = conn.execute(
            """
            SELECT s.id, ch.materiality, s.title
            FROM signals s
            JOIN conviction_history ch ON s.id = ch.signal_id
            WHERE ch.primary_ticker = ?
              AND ch.id IN (SELECT MAX(id) FROM conviction_history GROUP BY signal_id)
              AND ch.is_noise = 0
            ORDER BY ch.materiality DESC LIMIT 5
        """,
            (ticker,),
        ).fetchall()
    finally:
        conn.close()
    lines = [f"History {ticker}\n"]
    if theses:
        lines.append("== Thesis ==")
        for direction, entry, partial, full, stop, status, opened_at, lp, conv in theses:

            def fm(v):
                return f"${v:.0f}" if v else "?"

            opd = (opened_at or "")[:10]
            lp_s = f"${lp:.2f}" if lp else "?"
            lines.append(
                f"  [{direction or '?'}] entry {fm(entry)} / partial {fm(partial)} / full {fm(full)} / stop {fm(stop)}"
            )
            lines.append(f"  Opened {opd} status={status} last={lp_s} conv={conv or '?'}")
        lines.append("")
    if ins_90 and ins_90[0] is not None:
        net_m, buys_m, sells_m, n_b, n_s, snap_date = ins_90
        lines.append("== Insider (90d snapshot) ==")
        lines.append(f"  Snapshot: {snap_date}")
        lines.append(f"  Net: ${net_m:+.1f}M (buys ${buys_m or 0:.1f}M / sells ${sells_m or 0:.1f}M)")
        lines.append(f"  N: {n_b or 0} buys / {n_s or 0} sells")
        if ins_365 and ins_365[0] is not None:
            n365, _b365, _s365 = ins_365
            lines.append(f"  365d cumul net: ${n365:+.1f}M")
        lines.append("")
    if preds:
        lines.append("== Predictions ==")
        for direction, hd, baseline, final, ret, outcome, bd in preds:
            ret_s = f"{ret * 100:+.1f}%" if ret is not None else "pending"
            final_s = f"${final:.2f}" if final else "open"
            base_s = f"${baseline:.2f}" if baseline else "?"
            lines.append(
                f"  [{direction} {hd}d] {(bd or '')[:10]}: {base_s} -> {final_s} ({ret_s}) {outcome or 'pending'}"
            )
        lines.append("")
    lines.append("== Signal mentions ==")
    lines.append(f"  30d: {sig_30}  /  90d: {sig_90}")
    lines.append("")
    if material:
        lines.append("== Top material signals ==")
        for sid, mat, title in material:
            t = (title or "")[:60]
            lines.append(f"  #{sid} mat={mat:.3f}: {t}")
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[...truncated...]"
    await update.message.reply_text(msg)


async def cmd_journal(update, ctx):
    """Log a decision. Usage: /journal <TICKER> <type> <confidence_1_5> <reasoning>
    Types: entry, scale_in, partial_exit, full_exit, override, no_action_flag
    Abbrev: e, si, pe, fe, o, nf
    """
    from datetime import date, timedelta

    text = update.message.text
    parts = text.split(None, 4)
    if len(parts) < 5:
        await update.message.reply_text(
            "Usage: /journal <TICKER> <type> <confidence_1_5> <reasoning>\n"
            "Types: entry|scale_in|partial_exit|full_exit|override|no_action_flag\n"
            "Abbrev: e|si|pe|fe|o|nf\n"
            "Example: /journal NVDA nf 3 Won't add at 52w high before earnings"
        )
        return

    _, ticker_raw, type_raw, conf_raw, reasoning = parts
    ticker = ticker_raw.upper()

    ALIASES = {
        "e": "entry",
        "entry": "entry",
        "si": "scale_in",
        "scale_in": "scale_in",
        "scalein": "scale_in",
        "pe": "partial_exit",
        "partial_exit": "partial_exit",
        "fe": "full_exit",
        "full_exit": "full_exit",
        "exit": "full_exit",
        "o": "override",
        "override": "override",
        "nf": "no_action_flag",
        "no_action_flag": "no_action_flag",
        "noaction": "no_action_flag",
        "flag": "no_action_flag",
    }
    dtype = ALIASES.get(type_raw.lower())
    if not dtype:
        await update.message.reply_text(f"Unknown type: {type_raw}\nValid: {sorted(set(ALIASES.values()))}")
        return

    try:
        confidence = int(conf_raw)
        if not 1 <= confidence <= 5:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"Confidence must be 1-5, got: {conf_raw}")
        return

    price = None
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
        price = info.get("regularMarketPrice") or info.get("currentPrice")
    except Exception:
        pass

    regime_str = None
    try:
        from intelligence import regime as regime_mod

        r = regime_mod.detect_regime()
        regime_str = r.get("overall") if isinstance(r, dict) else None
    except Exception:
        pass

    credit_str = None
    try:
        from shared import macro

        cr = macro.get_credit_regime()
        if cr and not cr.get("error") and cr.get("hy"):
            hy = cr["hy"]
            bp = hy.get("bp")
            klass = hy.get("classification")
            chg = hy.get("change_1m_bp")
            if bp and klass:
                chg_s = f" (1m {chg:+.0f}bp)" if chg is not None else ""
                credit_str = f"{klass} {bp:.0f}bp{chg_s}"
    except Exception:
        pass

    thesis_id = None
    direction = None
    try:
        import sqlite3

        conn = sqlite3.connect("data/bot.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, direction FROM theses WHERE ticker=? AND status='active' ORDER BY opened_at DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        conn.close()
        if row:
            thesis_id = row["id"]
            direction = row["direction"]
    except Exception:
        pass

    if not direction and dtype in ("entry", "scale_in"):
        direction = "long"

    materiality_top = None
    try:
        from shared import storage as storage_mod

        tops = storage_mod.get_top_material_signals(n=10, since_hours=72)
        ticker_tops = [t["id"] for t in tops if t.get("primary_ticker") == ticker][:3]
        materiality_top = ticker_tops if ticker_tops else None
    except Exception:
        pass

    try:
        from shared import storage as storage_mod

        did = storage_mod.log_decision(
            ticker=ticker,
            decision_type=dtype,
            confidence=confidence,
            reasoning=reasoning,
            direction=direction,
            thesis_id=thesis_id,
            price_at_decision=price,
            regime=regime_str,
            credit_regime=credit_str,
            materiality_top=materiality_top,
        )
    except Exception as e:
        await update.message.reply_text(f"Error logging decision: {e}")
        return

    bias_tags = []
    try:
        from intelligence import bias_tagger

        decision_full = storage_mod.get_decision(did) or {}
        position = storage_mod.get_position_by_ticker(ticker)
        bias_tags = bias_tagger.auto_tag_biases(
            decision_full, position=position, regime_str=regime_str, top_signals=materiality_top
        )
        if bias_tags:
            storage_mod.update_decision_bias_tags(did, bias_tags)
    except Exception:
        pass

    msg = [f"Decision #{did} logged"]
    msg.append(f"  {ticker} [{dtype}] conf={confidence} dir={direction or '?'}")
    if price:
        msg.append(f"  price ${price:.2f} | regime={regime_str or '?'} | credit={credit_str or '?'}")
    if thesis_id:
        msg.append(f"  linked to active thesis #{thesis_id}")
    if materiality_top:
        msg.append(f"  top material signals: {materiality_top}")
    resolve_30 = (date.today() + timedelta(days=30)).isoformat()
    resolve_90 = (date.today() + timedelta(days=90)).isoformat()
    msg.append(f"  J+30 resolution = {resolve_30}, J+90 = {resolve_90}")
    await update.message.reply_text("\n".join(msg))


async def cmd_journal_review(update, ctx):
    """Review journal stats + recent decisions. Usage: /journal_review [TICKER]"""
    from intelligence import journal
    from shared import storage as storage_mod

    parts = update.message.text.split()
    ticker_filter = parts[1].upper() if len(parts) > 1 else None

    stats = storage_mod.get_journal_stats()
    by_m = stats["by_mistake"]
    by_t = stats["by_type"]

    lines = ["Journal review"]
    if ticker_filter:
        lines[0] += f" (filter: {ticker_filter})"
    lines.append("")

    if not by_m and not by_t:
        lines.append("No resolved decisions yet.")
        lines.append("Need J+30+ since first /journal entry. Auto-resolve via cron (Batch 3).")
    else:
        lines.append("Stats by mistake_tag (resolved only):")
        for r in by_m:
            tag, n, avg30, avg90 = r
            avg30_s = f"{avg30 * 100:+.1f}%" if avg30 is not None else "n/a"
            avg90_s = f"{avg90 * 100:+.1f}%" if avg90 is not None else "n/a"
            lines.append(f"  {tag:25s} n={n} avg30={avg30_s} avg90={avg90_s}")
        lines.append("")
        lines.append("Stats by decision_type:")
        for r in by_t:
            dtype, n, avg30 = r
            avg30_s = f"{avg30 * 100:+.1f}%" if avg30 is not None else "n/a"
            lines.append(f"  {dtype:20s} n={n} avg30={avg30_s}")
        lines.append("")

    recent = storage_mod.get_recent_decisions(n=10, ticker=ticker_filter)
    if recent:
        lines.append(f"Recent decisions ({len(recent)}):")
        for d in recent[:5]:
            lines.append(journal.format_decision_summary(d))
            lines.append("")

    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_journal_unresolved(update, ctx):
    """List decisions awaiting J+30 or J+90 resolution."""
    from intelligence import journal
    from shared import storage as storage_mod

    unres_30 = storage_mod.get_unresolved_decisions(30)
    unres_90 = storage_mod.get_unresolved_decisions(90)

    lines = ["Unresolved decisions:"]
    if not unres_30 and not unres_90:
        lines.append("  None (all decisions still within resolution window).")

    if unres_30:
        lines.append(f"\nJ+30 ready to resolve ({len(unres_30)}):")
        for d in unres_30[:5]:
            lines.append(journal.format_decision_summary(d))
            lines.append("")

    if unres_90:
        lines.append(f"\nJ+90 ready to resolve ({len(unres_90)}):")
        for d in unres_90[:5]:
            lines.append(journal.format_decision_summary(d))
            lines.append("")

    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_journal_tag(update, ctx):
    """Manually override mistake tag. Usage: /journal_tag <id> <tag>"""
    parts = update.message.text.split()
    if len(parts) < 3:
        await update.message.reply_text(
            "Usage: /journal_tag <decision_id> <new_tag>\nExample: /journal_tag 12 sold_too_early"
        )
        return
    try:
        did = int(parts[1])
    except ValueError:
        await update.message.reply_text(f"Invalid id: {parts[1]}")
        return
    new_tag = " ".join(parts[2:])

    from shared import storage as storage_mod

    d = storage_mod.get_decision(did)
    if not d:
        await update.message.reply_text(f"Decision #{did} not found")
        return

    storage_mod.override_mistake_tag(did, new_tag)
    await update.message.reply_text(
        f"OK decision #{did}: mistake_tag_manual='{new_tag}'\n  (was auto: {d.get('mistake_tag_auto') or 'pending'})"
    )


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


async def cmd_sources_brier(update, ctx):
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


async def cmd_llm_costs(update, ctx):
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


async def cmd_echo_recent(update, ctx):
    """Phase A3 — Show recent multi-source echo clusters. Usage: /echo_recent [hours]"""
    parts = update.message.text.split()
    window = 48
    if len(parts) > 1:
        with contextlib.suppress(ValueError):
            window = int(parts[1])

    from shared import echo as echo_mod

    clusters = echo_mod.get_recent_multi_source_clusters(window_hours=window, min_unique_sources=2)

    if not clusters:
        await update.message.reply_text(
            f"No multi-source echo clusters in last {window}h.\n"
            "Clusters appear when >=2 distinct sources discuss similar content."
        )
        return

    lines = [f"Echo clusters last {window}h ({len(clusters)} corroborated)"]
    for c in clusters[:10]:
        srcs_str = ", ".join(s[:18] for s in c["sources"][:3])
        if len(c["sources"]) > 3:
            srcs_str += f" +{len(c['sources']) - 3}"
        lines.append(f"\nCluster #{c['cluster_id']}: {c['n_unique_sources']} sources, {len(c['signals'])} signals")
        lines.append(f"  Sources: {srcs_str}")
        for s in c["signals"][:3]:
            title = (s.get("title") or "")[:55]
            src = (s.get("source_name") or "?")[:18]
            lines.append(f"    #{s['id']} {src}: {title}")
        if len(c["signals"]) > 3:
            lines.append(f"    ... ({len(c['signals']) - 3} more)")

    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


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


async def cmd_sources_half_life(update, ctx):
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


def _portfolio_journal_ctx(ticker):
    """Phase B5 — Auto-context for journal log_decision: price, regime, credit, thesis_id, materiality_top."""
    ticker = ticker.upper()
    price = None
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
        price = info.get("regularMarketPrice") or info.get("currentPrice")
    except Exception:
        pass
    regime_str = None
    try:
        from intelligence import regime as regime_mod

        r = regime_mod.detect_regime()
        regime_str = r.get("overall") if isinstance(r, dict) else None
    except Exception:
        pass
    credit_str = None
    try:
        from shared import macro

        cr = macro.get_credit_regime()
        if cr and not cr.get("error") and cr.get("hy"):
            hy = cr["hy"]
            bp = hy.get("bp")
            klass = hy.get("classification")
            chg = hy.get("change_1m_bp")
            if bp and klass:
                chg_s = f" (1m {chg:+.0f}bp)" if chg is not None else ""
                credit_str = f"{klass} {bp:.0f}bp{chg_s}"
    except Exception:
        pass
    thesis_id = None
    direction = None
    try:
        import sqlite3

        conn = sqlite3.connect("data/bot.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, direction FROM theses WHERE ticker=? AND status='active' ORDER BY opened_at DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        conn.close()
        if row:
            thesis_id = row["id"]
            direction = row["direction"]
    except Exception:
        pass
    materiality_top = None
    try:
        from shared import storage as storage_mod

        tops = storage_mod.get_top_material_signals(n=10, since_hours=72)
        ticker_tops = [t["id"] for t in tops if t.get("primary_ticker") == ticker][:3]
        materiality_top = ticker_tops if ticker_tops else None
    except Exception:
        pass
    return price, regime_str, credit_str, thesis_id, direction, materiality_top


async def cmd_portfolio(update, ctx):
    """Phase B5 — Show active positions + concentration + unrealized PnL."""
    from shared import storage as storage_mod

    positions = storage_mod.get_active_positions()
    if not positions:
        await update.message.reply_text("No active positions.\n\nUse /position_buy <TICKER> <qty> <price> to open one.")
        return

    total_cost = sum(p["qty"] * p["avg_cost"] for p in positions)
    enriched = []
    total_mv = 0
    for p in positions:
        ticker = p["ticker"]
        cur_price = None
        try:
            import yfinance as yf

            info = yf.Ticker(ticker).info or {}
            cur_price = info.get("regularMarketPrice") or info.get("currentPrice")
        except Exception:
            pass
        mv = (cur_price * p["qty"]) if cur_price else (p["avg_cost"] * p["qty"])
        unreal = (mv - p["qty"] * p["avg_cost"]) if cur_price else 0.0
        enriched.append({**p, "current_price": cur_price, "market_value": mv, "unrealized_pnl": unreal})
        total_mv += mv

    lines = [f"Portfolio — {len(positions)} active positions"]
    lines.append(f"  Cost basis: ${total_cost:,.2f}")
    lines.append(f"  Market value: ${total_mv:,.2f}")
    if total_cost > 0:
        lines.append(f"  Unrealized PnL: {total_mv - total_cost:+,.2f} ({(total_mv / total_cost - 1) * 100:+.1f}%)")
    lines.append("")
    lines.append("Positions (% of book):")
    for p in sorted(enriched, key=lambda x: x["market_value"], reverse=True):
        pct = (p["market_value"] / total_mv * 100) if total_mv else 0
        cur = f"${p['current_price']:.2f}" if p.get("current_price") else "?"
        avg = p["avg_cost"]
        upnl = p["unrealized_pnl"]
        upnl_pct = (upnl / (p["qty"] * avg) * 100) if avg else 0
        lines.append(
            f"  {p['ticker']:6s} {p['qty']:g}@${avg:.2f} now {cur} upnl={upnl:+,.0f} ({upnl_pct:+.1f}%) [{pct:.1f}%]"
        )
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_position_history(update, ctx):
    """Phase B5 — Show position history. Usage: /position_history [TICKER]"""
    from shared import storage as storage_mod

    parts = update.message.text.split()
    ticker = parts[1].upper() if len(parts) > 1 else None
    positions = storage_mod.get_positions_history(ticker=ticker, limit=20)
    if not positions:
        await update.message.reply_text("No position history" + (f" for {ticker}" if ticker else "") + ".")
        return
    lines = ["Position history" + (f" — {ticker}" if ticker else "")]
    for p in positions:
        state = "CLOSED" if (p.get("status") == "closed") else f"OPEN ({p['qty']:g})"
        rpnl = p.get("realized_pnl") or 0
        lines.append(f"  #{p['id']} {p['ticker']} {state} entry={p['qty']:g}@${p['avg_cost']:.2f} rpnl={rpnl:+,.2f}")
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_bias_review(update, ctx):
    """Phase B6 — Show aggregated bias frequencies. Usage: /bias_review [TICKER]"""
    parts = update.message.text.split()
    ticker = parts[1].upper() if len(parts) > 1 else None
    from shared import storage as storage_mod

    stats = storage_mod.get_bias_stats(ticker=ticker, since_days=180)
    if stats["total_decisions_analyzed"] == 0:
        await update.message.reply_text(
            "No tagged decisions" + (f" for {ticker}" if ticker else "") + " in last 180 days."
        )
        return

    lines = ["Bias review" + (f" — {ticker}" if ticker else "") + " (last 180d)"]
    lines.append(f"  Decisions with bias tags: {stats['total_with_tags']}/{stats['total_decisions_analyzed']}")
    lines.append("")
    if stats["bias_counts"]:
        total = sum(c for _, c in stats["bias_counts"])
        lines.append("Bias frequencies:")
        for tag, n in stats["bias_counts"]:
            pct = (n / total * 100) if total else 0
            lines.append(f"  {tag:25s} n={n:3d}  ({pct:.1f}%)")
        lines.append("")
    if stats["by_decision_type"]:
        lines.append("By decision type:")
        for dtype, biases in stats["by_decision_type"].items():
            top = sorted(biases.items(), key=lambda x: -x[1])[:3]
            top_str = ", ".join(f"{t}({n})" for t, n in top)
            lines.append(f"  {dtype:20s} {top_str}")
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_thesis_premortem(update, ctx):
    """Phase B7 — Display pre-mortem for a thesis. Usage: /thesis_premortem <id>"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /thesis_premortem <thesis_id>")
        return
    try:
        tid = int(parts[1])
    except ValueError:
        await update.message.reply_text(f"Invalid id: {parts[1]}")
        return
    from shared import storage as storage_mod

    pm_json = storage_mod.get_thesis_pre_mortem(tid)
    if not pm_json:
        await update.message.reply_text(
            f"No pre-mortem for thesis #{tid}.\nOnly theses created after Phase B7 (12/05/2026) have pre-mortems."
        )
        return
    from intelligence import pre_mortem as pm_mod

    display = pm_mod.format_pre_mortem_display(pm_json)
    if not display:
        await update.message.reply_text("Pre-mortem stored but parse failed.")
        return
    if len(display) > 3900:
        display = display[:3900] + "\n[truncated]"
    await update.message.reply_text(display)


async def cmd_insider_buy_cluster(update, ctx):
    """Phase C7 — List BUY clusters. Usage: /insider_buy_cluster [TICKER]"""
    from shared import storage as storage_mod

    parts = update.message.text.split()
    ticker = parts[1].upper() if len(parts) > 1 else None
    if ticker:
        rows = storage_mod.get_buy_clusters_for_ticker(ticker, limit=20)
        if not rows:
            await update.message.reply_text(f"No BUY clusters logged for {ticker}.")
            return
        lines = [f"BUY CLUSTERS — {ticker} (last 20)"]
        for r in rows:
            ret30 = f"{r['return_30d']:+.2%}" if r["return_30d"] is not None else "pending"
            ret90 = f"{r['return_90d']:+.2%}" if r["return_90d"] is not None else "pending"
            lines.append(
                f"\n#{r['id']} {r['detected_at'][:10]} | {r['cluster_strength']:8s} | "
                f"{r['distinct_buyers']} buyers ${r['total_buy_m']:.1f}M @ ${r['price_at_detection'] or 0:.2f}"
            )
            lines.append(f"   J+30: {ret30}  |  J+90: {ret90}")
        msg = "\n".join(lines)
    else:
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=90)).strftime("%Y-%m-%d")
        import sqlite3

        conn = sqlite3.connect(storage_mod._DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM insider_buy_clusters_log WHERE date(detected_at) >= ? ORDER BY detected_at DESC LIMIT 20",
            (cutoff,),
        ).fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text("No BUY clusters logged in last 90 days.")
            return
        lines = ["BUY CLUSTERS — last 90 days"]
        for r in rows:
            ret30 = f"{r['return_30d']:+.2%}" if r["return_30d"] is not None else "pending"
            lines.append(
                f"\n{r['ticker']:6s} {r['detected_at'][:10]} {r['cluster_strength']:8s} "
                f"n={r['distinct_buyers']} ${r['total_buy_m']:.1f}M J+30={ret30}"
            )
        msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_insider_buy_cluster_stats(update, ctx):
    """Phase C7 — Empirical alpha summary across all logged BUY clusters."""
    from intelligence import insider_buy_cluster as ibc
    from shared import storage as storage_mod

    stats = storage_mod.get_buy_cluster_stats(since_days=365)
    if stats["n_total"] == 0:
        await update.message.reply_text(
            "No BUY clusters logged yet (last 365d).\nFirst clusters will appear after cron 6:20."
        )
        return
    msg = ibc.format_stats(stats)
    await update.message.reply_text(msg)


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


async def cmd_recent_8k(update, ctx):
    """Phase C9 — List recent 8-Ks. Usage: /recent_8k [TICKER] [severity]"""
    parts = update.message.text.split()
    ticker = None
    severity = None
    for p in parts[1:]:
        p_up = p.upper()
        if p_up in ("CATASTROPHIC", "HIGH", "MEDIUM", "LOW"):
            severity = p.lower()
        else:
            ticker = p_up
    from intelligence import filings_8k
    from shared import storage as storage_mod

    rows = storage_mod.get_recent_8k_filings_db(ticker=ticker, severity=severity, days=60, limit=30)
    msg = filings_8k.format_8k_list(rows)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_eight_k_history(update, ctx):
    """Phase C9 — Full 8-K history for ticker. Usage: /eight_k_history TICKER"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /eight_k_history <TICKER>")
        return
    ticker = parts[1].upper()
    from intelligence import filings_8k
    from shared import storage as storage_mod

    rows = storage_mod.get_recent_8k_filings_db(ticker=ticker, days=365, limit=50)
    if not rows:
        await update.message.reply_text(f"No 8-K filings logged for {ticker} in last 365d.")
        return
    msg = filings_8k.format_8k_list(rows)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_analyze_debate(update, ctx):
    """Phase C11 — Multi-round Bull/Bear debate. Usage: /analyze_debate TICKER"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /analyze_debate <TICKER>")
        return
    ticker = parts[1].upper()
    await update.message.reply_text(f"Running 3-round adversarial debate on {ticker} (~30-60s, ~$0.10)...")
    try:
        from intelligence import analyze as analyze_mod_local, debate as debate_mod
        from shared import storage as storage_mod

        data = analyze_mod_local.fetch_stock_data(ticker)
        if not data:
            await update.message.reply_text(f"No data available for {ticker}.")
            return
        context_text = analyze_mod_local.build_prompt(data)[:3500]
        result = debate_mod.run_multi_round_debate(ticker, context_text)
        if not result.get("rounds"):
            await update.message.reply_text("Debate produced no rounds. Aborting.")
            return
        debate_id = storage_mod.save_debate_transcript(
            ticker=ticker,
            transcript_dict=result,
            convergence_score=result.get("convergence_score"),
            verdict=result.get("verdict"),
        )
        chunks = debate_mod.format_debate_for_telegram(result)
        for c in chunks:
            if len(c) > 3900:
                c = c[:3900] + "\n[truncated]"
            await update.message.reply_text(c)
        await update.message.reply_text(f"Debate #{debate_id} saved. Replayable via /debate_replay {debate_id}")
    except Exception as e:
        log.warning(f"analyze_debate error: {e}")
        await update.message.reply_text(f"Error: {e}")


async def cmd_debate_replay(update, ctx):
    """Phase C11 — Replay stored debate by id. Usage: /debate_replay <id>"""
    import json

    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /debate_replay <debate_id>")
        return
    try:
        did = int(parts[1])
    except ValueError:
        await update.message.reply_text("Invalid id.")
        return
    from intelligence import debate as debate_mod
    from shared import storage as storage_mod

    rows = storage_mod.get_recent_debates(limit=50)
    target = next((r for r in rows if r["id"] == did), None)
    if not target:
        await update.message.reply_text(f"Debate #{did} not found.")
        return
    transcript = json.loads(target["transcript_json"])
    chunks = debate_mod.format_debate_for_telegram(transcript)
    for c in chunks:
        if len(c) > 3900:
            c = c[:3900] + "\n[truncated]"
        await update.message.reply_text(c)


async def cmd_risk_check(update, ctx):
    """Phase C12 — Pre-commit discipline check on proposed trade.
    Usage: /risk_check TICKER SIDE USD_AMOUNT [reasoning]
    Example: /risk_check NVDA long 5000 Adding before earnings May 21"""
    text = update.message.text or ""
    parts = text.split(maxsplit=4)
    if len(parts) < 4:
        await update.message.reply_text(
            "Usage: /risk_check TICKER SIDE USD_AMOUNT [reasoning]\n"
            "Example: /risk_check NVDA long 5000 Adding before earnings"
        )
        return
    ticker = parts[1].upper()
    side = parts[2].lower()
    try:
        proposed_usd = float(parts[3])
    except ValueError:
        await update.message.reply_text(f"Invalid USD amount: {parts[3]}")
        return
    reasoning = parts[4] if len(parts) > 4 else ""
    await update.message.reply_text(f"Running risk check on {ticker} {side.upper()} ${proposed_usd:,.0f} (~15-30s)...")
    try:
        from intelligence import risk_manager
        from shared import storage as storage_mod

        result = risk_manager.run_risk_check(ticker, side, proposed_usd, reasoning)
        positions = storage_mod.get_active_positions() or []
        thesis = storage_mod.get_thesis_by_ticker(ticker, status="active")
        snapshot = {"positions": positions, "thesis": thesis}
        rcid = storage_mod.save_risk_check(
            ticker=ticker,
            side=side,
            proposed_usd=proposed_usd,
            verdict=result.get("verdict", "unknown"),
            risk_check_dict=result,
            portfolio_snapshot=snapshot,
        )
        msg = risk_manager.format_risk_check_display(result, ticker, side, proposed_usd)
        msg += f"\n\nRisk check #{rcid} saved."
        if len(msg) > 3900:
            msg = msg[:3900] + "\n[truncated]"
        await update.message.reply_text(msg)
    except Exception as e:
        log.warning(f"risk_check error: {e}")
        await update.message.reply_text(f"Error: {e}")


async def cmd_tiers(update, ctx):
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


async def cmd_tiers_watch(update, ctx):
    """Full list of T2 watch tickers."""
    from shared import config as cfg_mod

    watch = cfg_mod.get_tickers("watch")
    msg = f"T2 WATCH ({len(watch)} tickers):\n\n" + ", ".join(watch)
    await update.message.reply_text(msg)


async def cmd_promote(update, ctx):
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


async def cmd_signals_by_type(update, ctx):
    """Phase Digestion 3a — Usage: /signals_by_type catalyst|data|narrative|opinion [hours]"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "Usage: /signals_by_type catalyst|data|narrative|opinion [hours=72]\n"
            "Returns signals sorted by adjusted materiality (score x corroboration boost)."
        )
        return
    sig_type = parts[1].lower()
    if sig_type not in ("catalyst", "data", "narrative", "opinion"):
        await update.message.reply_text(f"Invalid type: {sig_type}. Use catalyst|data|narrative|opinion.")
        return
    hours = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 72
    from shared import storage as storage_mod

    rows = storage_mod.get_signals_by_type(sig_type, since_hours=hours, limit=20)
    if not rows:
        await update.message.reply_text(f"No '{sig_type}' signals in last {hours}h.")
        return
    lines = [f"SIGNALS [{sig_type.upper()}] — last {hours}h ({len(rows)} found)"]
    for r in rows:
        boost = r.get("materiality_boost") or 1.0
        score = r.get("score") or 0
        adj = score * boost
        title = (r.get("title") or "?")[:100]
        src = r.get("source_name") or "?"
        lines.append(f"\n[adj={adj:.1f} raw={score} boost={boost:.1f}x] {src}")
        lines.append(f"  {title}")
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


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


async def cmd_macro(update, context):
    """Show FOMC / NFP / CPI macro events for next 90 days."""
    try:
        msg = format_macro_calendar(90)
    except Exception as e:
        msg = f"Error fetching macro calendar: {e}"
    await update.message.reply_text(msg)


async def cmd_insider_digest(update, context):
    """Manual: refresh insider snapshots and post digest."""
    await update.message.reply_text("⏳ Refreshing 13 tickers via SEC EDGAR (~30-60s)...")
    try:
        result = daily_insider_refresh()
        msg = format_daily_insider_digest(result)
    except Exception as e:
        msg = f"Error: {e}"
    await update.message.reply_text(msg, parse_mode="Markdown")


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


async def cmd_price_check(update, ctx):
    """Manual trigger : check all active theses for crossings right now."""
    await update.message.reply_text("Checking active theses...")
    try:
        r = check_thesis_triggers()
        if r["theses_checked"] == 0:
            await update.message.reply_text("No active theses.")
        elif r["alerts"]:
            await update.message.reply_text(
                f"{r['theses_checked']} theses checked, {len(r['alerts'])} alerts fired (see above)."
            )
        else:
            await update.message.reply_text(f"{r['theses_checked']} theses checked, no crossings.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_override(update, ctx):
    """Override capture/list: /override (list) | /override TICKER level reason (create)"""
    parts = update.message.text.split(maxsplit=3)

    # No args: list mode (former /overrides behavior)
    if len(parts) == 1:
        rows = list_overrides(limit=15)
        if not rows:
            await update.message.reply_text("No overrides recorded yet.")
            return
        lines = ["Recent overrides:"]
        for o in rows:
            reason = (o["reason"] or "")[:55]
            lines.append(f"#{o['id']:3d} {o['ticker']:6s} {o['level']:7s} | {reason}")
            lines.append(f"    {o['created_at']}")
        await update.message.reply_text("\n".join(lines))
        return

    # Create mode: needs TICKER + level + reason
    if len(parts) < 4:
        await update.message.reply_text(
            "Usage:\n  /override                          (list recent)\n"
            "  /override <TICKER> <partial|full|stop> <reason>  (create)"
        )
        return
    ticker, level, reason = parts[1].upper(), parts[2].lower(), parts[3]
    if level not in ("partial", "full", "stop"):
        await update.message.reply_text("level must be: partial / full / stop")
        return
    try:
        oid = record_override(ticker, level, reason)
        await update.message.reply_text(
            f"OK Override #{oid} captured: {ticker}/{level}\n  Reason: {reason}\n  Stored for BiasDetector training."
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_crypto(update, ctx):
    """Show crypto cycle indicators (funding, OI, Mayer Multiple)."""
    try:
        z = crypto_mod.compute_crypto_zone()
        msg = crypto_mod.format_crypto_zone(z)
    except Exception as e:
        msg = f"Error: {e}"
    await update.message.reply_text(msg)


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


async def cmd_position_buy(update, ctx):
    """Buy + Phase B5 journal logging + bias tagging (auto).
    Usage: /position_buy <TICKER> <QTY> <PRICE> [reasoning]
    """
    parts = update.message.text.split(maxsplit=4)
    if len(parts) < 4:
        await update.message.reply_text("Usage: /position_buy <TICKER> <QTY> <PRICE> [reasoning]")
        return
    try:
        ticker, qty, price = parts[1].upper(), float(parts[2]), float(parts[3])
        reasoning = parts[4] if len(parts) > 4 else "Buy via /position_buy"

        # 0. B2: Risk validation gate (feature-flagged, default OFF)
        from shared import config as _cfg_b2_mod, storage as _storage_b2_mod

        _cfg_b2 = _cfg_b2_mod.load()
        if _cfg_b2.get("risk", {}).get("validate_enabled", False):
            from risk import risk_engine

            _state_b2 = _storage_b2_mod.load_state()
            _capital_b2 = _state_b2.get("capital_paper", 10000) or 10000
            _size_pct_b2 = (qty * price) / _capital_b2
            _thesis_b2 = _storage_b2_mod.get_thesis_by_ticker(ticker, status="active")
            _conviction_b2 = (_thesis_b2.get("conviction", 3) if _thesis_b2 else 3)
            _decision_b2 = {
                "ticker": ticker,
                "action": "buy",
                "size_pct": _size_pct_b2,
                "conviction": _conviction_b2,
                "execute_real": False,
            }
            _result_b2 = risk_engine.validate(_decision_b2)
            if not _result_b2.ok and _result_b2.severity == "block":
                _msg_b2 = "BLOCKED by risk.validate():\n" + "\n".join(
                    f"  - {r}" for r in _result_b2.reasons
                )
                _msg_b2 += "\n  Override: toggle risk.validate_enabled in config.yaml"
                with contextlib.suppress(Exception):
                    _storage_b2_mod.log_decision(
                        ticker=ticker,
                        decision_type="buy_blocked_by_risk",
                        confidence=_conviction_b2,
                        reasoning=f"BLOCKED: {'; '.join(_result_b2.reasons)}",
                        direction="long",
                        price_at_decision=price,
                    )
                await update.message.reply_text(_msg_b2)
                return

        # 1. Detect entry vs scale_in BEFORE update
        existing_before = positions_mod.get_position(ticker)
        dtype = "scale_in" if (existing_before and existing_before.get("qty", 0) > 0) else "entry"

        # 2. Update position via positions_mod (writes positions + position_events)
        p = positions_mod.add_buy(ticker, qty, price, reasoning)

        # 3. Phase B5 journal context + auto log_decision
        from shared import storage as storage_mod
        _px_ctx, regime, credit, thesis_id, thesis_dir, mat_top = _portfolio_journal_ctx(ticker)
        decision_id = None
        try:
            decision_id = storage_mod.log_decision(
                ticker=ticker, decision_type=dtype, confidence=3,
                reasoning=reasoning, direction=(thesis_dir or "long"),
                thesis_id=thesis_id, price_at_decision=price,
                regime=regime, credit_regime=credit, materiality_top=mat_top,
            )
        except Exception as e:
            await update.message.reply_text(f"Position updated but journal failed: {e}")

        # 4. Auto-tag biases
        bias_tags = []
        if decision_id:
            try:
                from intelligence import bias_tagger
                decision_full = storage_mod.get_decision(decision_id) or {}
                position_now = storage_mod.get_position_by_ticker(ticker)
                bias_tags = bias_tagger.auto_tag_biases(
                    decision_full, position=position_now, regime_str=regime, top_signals=mat_top
                )
                if bias_tags:
                    storage_mod.update_decision_bias_tags(decision_id, bias_tags)
            except Exception:
                pass

        # 5. Compose response
        msg = [f"✓ Bought {qty:.3f} {ticker} @ ${price:.2f} [{dtype}]"]
        msg.append(f"  New qty: {p['qty']:.3f}, avg cost: ${p['avg_cost']:.2f}")
        if decision_id:
            tags_str = f", biases: {','.join(bias_tags)}" if bias_tags else ""
            msg.append(f"  -> auto-logged decision #{decision_id} thesis={thesis_id or '-'}{tags_str}")
        await update.message.reply_text("\n".join(msg))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_position_sell(update, ctx):
    """Sell + Phase B5 journal logging + bias tagging (auto).
    Usage: /position_sell <TICKER> <QTY> <PRICE> [reasoning]
    """
    parts = update.message.text.split(maxsplit=4)
    if len(parts) < 4:
        await update.message.reply_text("Usage: /position_sell <TICKER> <QTY> <PRICE> [reasoning]")
        return
    try:
        ticker, qty, price = parts[1].upper(), float(parts[2]), float(parts[3])
        reasoning = parts[4] if len(parts) > 4 else "Sell via /position_sell"

        # 1. Update position (writes positions + position_events)
        r = positions_mod.add_sell(ticker, qty, price, reasoning)
        dtype = "full_exit" if r["closed"] else "partial_exit"

        # 2. Phase B5 journal context + auto log_decision
        from shared import storage as storage_mod
        _px_ctx, regime, credit, thesis_id, thesis_dir, mat_top = _portfolio_journal_ctx(ticker)
        decision_id = None
        try:
            decision_id = storage_mod.log_decision(
                ticker=ticker, decision_type=dtype, confidence=3,
                reasoning=reasoning, direction=(thesis_dir or "long"),
                thesis_id=thesis_id, price_at_decision=price,
                regime=regime, credit_regime=credit, materiality_top=mat_top,
            )
        except Exception as e:
            await update.message.reply_text(f"Position updated but journal failed: {e}")

        # 3. Auto-tag biases
        bias_tags = []
        if decision_id:
            try:
                from intelligence import bias_tagger
                decision_full = storage_mod.get_decision(decision_id) or {}
                position_now = storage_mod.get_position_by_ticker(ticker)
                bias_tags = bias_tagger.auto_tag_biases(
                    decision_full, position=position_now, regime_str=regime, top_signals=mat_top
                )
                if bias_tags:
                    storage_mod.update_decision_bias_tags(decision_id, bias_tags)
            except Exception:
                pass

        # 4. Compose response
        msg_lines = [f"✓ Sold {r['sold_qty']:.3f} {r['ticker']} @ ${r['sold_price']:.2f} [{dtype}]"]
        msg_lines.append(f"  Avg cost was: ${r['avg_cost']:.2f}")
        msg_lines.append(f"  Realized PnL (event): ${r['realized_pnl_event']:+,.2f}")
        msg_lines.append(f"  Realized PnL (total): ${r['realized_pnl_total']:+,.2f}")
        msg_lines.append(f"  Remaining: {r['remaining_qty']:.3f}" + ("  [CLOSED]" if r["closed"] else ""))
        if decision_id:
            tags_str = f", biases: {','.join(bias_tags)}" if bias_tags else ""
            msg_lines.append(f"  -> auto-logged decision #{decision_id} thesis={thesis_id or '-'}{tags_str}")
        await update.message.reply_text("\n".join(msg_lines))
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


async def cmd_analyze(update, ctx):
    """Full company analysis fiche: /analyze TICKER"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /analyze <TICKER>  (e.g. /analyze NVDA, /analyze BTC-USD)")
        return
    ticker = parts[1].upper()
    await update.message.reply_text(f"⏳ Generating analysis for {ticker} (~15-30s)...")
    try:
        result = analyze_mod.analyze_stock(ticker)
        chunks = analyze_mod.format_for_telegram(result)
        for chunk in chunks:
            await update.message.reply_text(chunk)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_insider_cluster(update, ctx):
    """Detect cluster buying/selling: /insider_cluster TICKER [days]"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /insider_cluster <TICKER> [days=14]")
        return
    ticker = parts[1].upper()
    days = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 14
    await update.message.reply_text("Scanning " + ticker + " insider cluster (" + str(days) + "d)...")
    try:
        cluster = edgar_mod.get_insider_cluster(ticker, days=days)
        await update.message.reply_text(edgar_mod.format_insider_cluster(cluster))
    except Exception as e:
        await update.message.reply_text("Error: " + str(e))


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


async def cmd_credit(update, ctx):
    try:
        from shared import macro

        r = macro.get_credit_regime()
        await update.message.reply_text(macro.format_credit_regime(r))
    except Exception as e:
        await update.message.reply_text("Error: " + str(e))


async def cmd_materiality(update, ctx):
    """Materiality views: /materiality (top 5) | /materiality SIGNAL_ID | /materiality TICKER"""
    import json
    import sqlite3

    from intelligence import materiality_v2
    from shared import storage as storage_mod

    parts = update.message.text.split()

    # Mode 1: no args -> top 5 last 24h
    if len(parts) == 1:
        tops = storage_mod.get_top_material_signals(n=5, since_hours=24)
        if not tops:
            await update.message.reply_text("No material signals in last 24h")
            return
        lines = ["Top 5 material signals (last 24h):\n"]
        for t in tops:
            title = (t.get("title") or t.get("summary") or "")[:55]
            mat = t.get("materiality") or 0
            lines.append("#" + str(t["id"]) + " [" + (t.get("primary_ticker") or "-") + "] m=" + (f"{mat:.3f}"))
            lines.append("  " + title)
            if t.get("why_this_matters"):
                lines.append("  --> " + t["why_this_matters"])
            lines.append("")
        await update.message.reply_text("\n".join(lines))
        return

    arg = parts[1].strip()

    # Mode 2: integer arg -> signal_id breakdown
    try:
        sid = int(arg)
        m = storage_mod.get_materiality(sid)
        if not m:
            await update.message.reply_text("No materiality data for signal #" + str(sid))
            return
        lines = [
            "Materiality #" + str(sid) + ":",
            "  composite:      " + ("%.3f" % (m.get("materiality") or 0)),
            "  quality:        " + ("%.3f" % (m.get("quality") or 0)),
            "  novelty:        " + ("%.2f" % (m.get("novelty") or 0)),
            "  cross-conf:     " + ("%.2f" % (m.get("cross_confirmation") or 0)),
            "  market_impact:  " + ("%.2f" % (m.get("market_impact") or 0)),
            "  regime_fit:     " + ("%.2f" % (m.get("regime_relevance") or 0)),
            "  type: " + str(m.get("signal_type") or "?") + " | polarity: " + str(m.get("polarity") or "?"),
            "  primary: " + str(m.get("primary_ticker") or "-") + " | noise: " + str(bool(m.get("is_noise"))),
            "  regime: " + str(m.get("regime_snapshot") or "?") + " | credit: " + str(m.get("credit_regime_snapshot") or "?"),
        ]
        if m.get("why_this_matters"):
            lines.append("")
            lines.append("Why this matters:")
            lines.append("  " + m["why_this_matters"])
        await update.message.reply_text("\n".join(lines))
        return
    except ValueError:
        pass

    # Mode 3: non-numeric arg -> ticker (last 5 signals mentioning ticker, former /materiality_debug)
    ticker = arg.upper()
    conn = sqlite3.connect(storage_mod._DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT s.id, s.title, s.score, s.signal_type, s.impact_magnitude, "
        "       s.reversibility, s.time_to_realization, s.materiality_breakdown, "
        "       s.materiality_boost, src.name AS source "
        "FROM signals s LEFT JOIN sources src ON s.source_id = src.id "
        "WHERE s.entities LIKE ? "
        "ORDER BY s.timestamp DESC LIMIT 5",
        (f"%{ticker}%",),
    ).fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text(f"No signals mention {ticker} in DB.")
        return
    lines = [f"MATERIALITY BREAKDOWN - {ticker} (last 5)"]
    for r in rows:
        lines.append(f"\n[#{r['id']}] {(r['title'] or '?')[:80]}")
        lines.append(f"  src={r['source']} | type={r['signal_type'] or '?'} | raw_score={r['score']}")
        if r["impact_magnitude"] is not None:
            composite = materiality_v2.compute_composite_score(dict(r))
            reasoning = ""
            try:
                if r["materiality_breakdown"]:
                    b = json.loads(r["materiality_breakdown"])
                    reasoning = b.get("reasoning", "")[:120]
            except Exception:
                pass
            boost = r["materiality_boost"] or 1.0
            adj = composite * boost if composite else "na"
            lines.append(
                f"  impact={r['impact_magnitude']:.0f}/5 | reversibility={r['reversibility']:.0f}/5 | "
                f"time={r['time_to_realization']} | composite={composite}/10 | boost={boost:.1f}x | adj={adj}"
            )
            if reasoning:
                lines.append(f"  -> {reasoning}")
        else:
            lines.append("  [v2 scoring pending - runs hourly cron]")
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)

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
    app.add_handler(CommandHandler("position_buy", cmd_position_buy))
    app.add_handler(CommandHandler("position_sell", cmd_position_sell))
    app.add_handler(CommandHandler("position", cmd_position))
    app.add_handler(CommandHandler("analyze", cmd_analyze))

    log.info("Polling Telegram...")
    app.run_polling()


if __name__ == "__main__":
    main()
