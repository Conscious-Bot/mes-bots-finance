"""Daily cron jobs — extracted from bot/jobs.py Phase C (21/05/2026)."""

import logging

from intelligence import (
    calendar as calendar_mod,
    learning as learning_mod,
)
from intelligence.insider_digest import daily_insider_refresh, format_daily_insider_digest
from shared import config, crypto as crypto_mod, edgar as edgar_mod, notify, positions as positions_mod

log = logging.getLogger("bot")

CALENDAR_REFRESH_TICKERS = config.get_tickers("core") if hasattr(config, "get_tickers") else []


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

    Fix 30/05/2026 : le cwd pointait sur bot/ (parent.parent depuis bot/jobs/),
    donc subprocess cherchait bot/scripts/backup.sh (inexistant) -> FAILED chaque
    jour. Corrige a parent.parent.parent pour pointer au repo root.
    """
    try:
        import subprocess
        from pathlib import Path as _Path

        # bot/jobs/daily.py -> bot/jobs -> bot -> repo root
        proj = str(_Path(__file__).resolve().parent.parent.parent)
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


async def scheduled_insider_refresh_job():
    """Cron: 6h Paris daily — refresh + post if anything notable."""
    try:
        result = daily_insider_refresh()
        msg = format_daily_insider_digest(result)
        notify.send_text(msg)
        log.info(f"scheduled_insider_refresh: {result['refreshed']} tickers, {len(result['alerts'])} alerts")
    except Exception as e:
        log.error(f"scheduled_insider_refresh failed: {e}")


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
    # severity = filter heuristique low-latency pour push Telegram immediat (ADR 012).
    # Pas une mesure d'evidence_strength : un Item 2.02 earnings beat est classe
    # 'medium' ici mais V2 sur contenu peut sortir 'strong'. Pour la calibration
    # serieuse, la verite est en aval (signals -> V2 -> predictions).
    alerts = [r for r in new_logged if r["severity"] in ("catastrophic", "high")]
    if alerts:
        msg = f"8-K ALERTS ({len(alerts)} high+catastrophic)\n\n"
        for r in alerts:
            msg += filings_8k.format_8k_alert(r) + "\n\n"
        notify.send_text(msg.strip())
    log.info(f"8-K scan: {len(new_logged)} new logged, {len(alerts)} alerted")


async def weekly_user_profile_refresh_job():
    """Sprint 2 — Weekly Opus synthesis of the user's self-portrait.

    Reads 6 months of decisions/theses/predictions/biases/copilot_interventions
    and produces an evolving structured profile injected into every future
    copilot pressure-test (restraint at start when n is low, sharp later).
    """
    try:
        from intelligence import user_profile

        result, profile_id = user_profile.run_synthesis(months_window=6)
        if result is None:
            log.warning("weekly_user_profile_refresh : synthesis returned None")
            return
        conf = result.get("confidence_score", 0)
        archetype = (result.get("risk_archetype") or {}).get("label", "?")
        log.info(
            f"weekly_user_profile_refresh : profile_id={profile_id} confidence={conf}/100 "
            f"archetype={archetype} summary='{(result.get('summary_oneliner') or '')[:120]}'"
        )
    except Exception as e:
        log.exception(f"weekly_user_profile_refresh crashed: {e}")


async def resolve_copilot_interventions_30d_job():
    """Sprint 4 — Resolution loop : pour chaque copilot intervention >30j sans
    resolution, compute outcome_label depuis decisions.return_30d_pct.

    Labels :
    - copilot_proceed_outcome_good : verdict PROCEED + decision a bien marche
    - copilot_proceed_outcome_bad : PROCEED + decision a mal marche (alerte manquee)
    - copilot_pressure_outcome_good : PRESSURE/STRONG_OPPOSE + decision a mal marche (= copilot avait raison)
    - copilot_pressure_outcome_bad : PRESSURE/STRONG_OPPOSE + decision a bien marche (= false positive)
    - no_decision_linked : intervention sans decision_id (rare edge)

    "Good" depend du decision_type :
    - scale_in : return_30d > 0 = good (achat a bon niveau)
    - partial_exit / full_exit : return_30d < 0 = good (vente a evite la baisse)
    - override : return_30d > 0 = good (heuristique simple)

    Tourne quotidiennement apres daily_resolve_job (qui fill decisions.return_30d_pct).
    DB writes route via shared/storage.py (CONVENTIONS §5).
    """
    from shared import storage

    try:
        resolved = 0
        skipped_pending = 0
        skipped_no_decision = 0
        pending = storage.fetch_pending_copilot_resolutions(limit=100)
        for r in pending:
            iid = r["id"]
            verdict = r["verdict"]
            dtype = r["decision_type"]
            decision_id = r["decision_id"]
            ret_30d = r["return_30d_pct"]
            if decision_id is None:
                storage.resolve_copilot_intervention(iid, None, "no_decision_linked")
                skipped_no_decision += 1
                continue
            if ret_30d is None:
                skipped_pending += 1
                continue
            if dtype == "scale_in":
                outcome_good = ret_30d > 0
            elif dtype in ("partial_exit", "full_exit"):
                outcome_good = ret_30d < 0
            elif dtype == "override":
                outcome_good = ret_30d > 0
            else:
                storage.resolve_copilot_intervention(iid, ret_30d, "decision_type_unknown")
                continue
            if verdict == "PROCEED":
                label = "copilot_proceed_outcome_good" if outcome_good else "copilot_proceed_outcome_bad"
            elif verdict in ("PRESSURE", "STRONG_OPPOSE"):
                label = "copilot_pressure_outcome_good" if outcome_good else "copilot_pressure_outcome_bad"
            else:
                label = "verdict_unknown"
            storage.resolve_copilot_intervention(iid, ret_30d, label)
            resolved += 1
        log.info(
            f"resolve_copilot_interventions_30d : resolved={resolved} "
            f"skipped_pending={skipped_pending} skipped_no_decision={skipped_no_decision}"
        )
    except Exception as e:
        log.exception(f"resolve_copilot_interventions_30d crashed: {e}")


async def daily_portfolio_grade_job():
    """Sprint 5 — Snapshot quotidien de la qualite du portefeuille.

    Calcul deterministe (6 dimensions) + insert en DB via shared/storage.
    Append-only : 1 snapshot/jour. Trend 7j calcule par diff vs snapshot J-7.
    """
    log.info("Daily portfolio grade starting")
    try:
        from intelligence import portfolio_grade as _grade
        from shared import storage as _storage

        grade = _grade.compute_grade()
        gid = _storage.insert_portfolio_grade(grade)
        log.info(
            f"Portfolio grade snapshot id={gid} {grade['overall_grade']} ({grade['overall_score']}/100) "
            f"pos={grade['n_positions']} theses={grade['n_theses_active']}"
        )
    except Exception as e:
        log.error(f"Daily portfolio grade failed: {e}")


async def weekly_portfolio_narrative_synthesis_job():
    """Sprint 6 — Synthese LLM hebdo des clusters narratifs du portefeuille.

    Une fois par semaine (dimanche 20h30, avant user_profile a 21h).
    Snapshot append-only consomme par portfolio_grade._compute_T2_redundant et
    _compute_decorrelation_star pour raffiner les proxies Sprint 5.
    """
    log.info("Weekly portfolio narrative synthesis starting")
    try:
        from intelligence import portfolio_grade_llm as _grade_llm

        result, sid = _grade_llm.run_synthesis()
        log.info(
            f"Narrative synthesis snapshot id={sid} "
            f"clusters={len(result.get('narrative_clusters') or [])} "
            f"edges={len(result.get('edge_positions') or [])} "
            f"redundant={len(result.get('redundant_positions') or [])}"
        )
    except Exception as e:
        log.error(f"weekly_portfolio_narrative_synthesis failed: {e}")


async def weekly_bot_conceptions_synthesis_job():
    """Layer 2 — Sprint 10 : digest hebdo des conceptions bot per ticker actif.

    Synthese stable a partir de signaux soft chat + decisions + theses +
    interventions + signaux newsletter. Append-only ; query = MAX(id) per
    (kind, target_key). Cible : 1 conception par ticker actif.
    """
    log.info("Weekly bot conceptions synthesis starting")
    try:
        from intelligence import bot_conceptions as _bc

        out = _bc.synthesize_all_active_tickers(months_window=6)
        log.info(f"bot_conceptions weekly : ok={out['ok']} skip={out['skip']} fail={out['fail']}")
    except Exception as e:
        log.error(f"weekly_bot_conceptions_synthesis failed: {e}")


async def monthly_bot_preferences_synthesis_job():
    """Layer 3 — Sprint 11 : preferences mensuelles (ce qui MARCHE pour CE user).

    Calibration deterministe sur outcomes : conviction calibration, sector
    outcome, bias outcome, sizing outcome, archetype consistency, copilot
    verdict outcomes. Pas d'opinion modele, juste les chiffres bruts.
    """
    log.info("Monthly bot preferences synthesis starting")
    try:
        from intelligence import bot_preferences as _bp

        out = _bp.synthesize_all()
        log.info(
            f"bot_preferences monthly : ok={out['ok']} skip={out['skip']} fail={out['fail']} "
            f"details={out['details']}"
        )
    except Exception as e:
        log.error(f"monthly_bot_preferences_synthesis failed: {e}")


async def daily_kill_criteria_check_job():
    """Sprint 15 — Evalue les invalidation_triggers per these active.

    Status global per these : dormant | at_risk | triggered. Notify Telegram
    sur transition X -> triggered (action requise). Tourne quotidien matin
    pour laisser le temps a la decision dans la journee.
    """
    log.info("Daily kill-criteria check starting")
    try:
        from intelligence import kill_criteria_monitor as _kcm

        out = _kcm.check_all_active_theses()
        log.info(
            f"kill_criteria_check : triggered={out['triggered']} at_risk={out['at_risk']} "
            f"dormant={out['dormant']} skipped={out['skipped']} failed={out['failed']}"
        )
    except Exception as e:
        log.error(f"daily_kill_criteria_check failed: {e}")


async def weekly_data_clusters_synthesis_job():
    """Sprint 17 — Data-defined clusters par correlation rendements (hebdo).

    Fetch 120j daily prices via yfinance, compute correlation matrix,
    identify high-corr pairs + clusters mixed macro_factor. Snapshot persiste.
    """
    log.info("Weekly data clusters synthesis starting")
    try:
        import json as _json

        from intelligence import return_clustering as _rc
        from shared import storage as _storage

        r = _rc.run_analysis(days=120)
        sid = _storage.insert_data_clusters_snapshot(_json.dumps(r, ensure_ascii=False))
        log.info(
            f"data_clusters snapshot id={sid} pairs={r.get('n_pairs', 0)} "
            f"clusters={r.get('n_clusters', 0)} mixed={r.get('n_mixed_clusters', 0)}"
        )
    except Exception as e:
        log.error(f"weekly_data_clusters_synthesis failed: {e}")


async def daily_risk_signal_monitor_job():
    """Sprint 20.b — Daily check des surveillance_signals dans risk_watch.json.

    Scan signals table pour pattern matching (capex_hyperscaler, asml_bookings,
    tsm_monthly_rev, hbm_pricing, vix_credit, wafer_pricing) + Haiku evaluate
    status (monitoring/at_risk/triggered). Notify Telegram sur transition.
    Tourne 08h00 avant ouverture marche.
    """
    log.info("Daily risk signal monitor starting")
    try:
        from intelligence import risk_signal_monitor as _rsm

        out = _rsm.check_all_risks()
        log.info(
            f"risk_signal_monitor : {out.get('n_signals_evaluated', 0)} evalues, "
            f"{len(out.get('transitions', []))} transitions"
        )
    except Exception as e:
        log.error(f"daily_risk_signal_monitor failed: {e}")


async def daily_decision_anniversary_job():
    """Sprint 22 — Daily check des anniversaires de decisions (J+30/60/90/180/365).

    Pour chaque decision atteignant un anniversaire, push Telegram avec
    rationale historique + return actuel + prompt reflexion. Persiste en
    chat_extracted_signals pour nourrir user_profile.
    """
    log.info("Daily decision anniversary check starting")
    try:
        from intelligence import decision_anniversary as _da

        out = _da.check_today()
        log.info(
            f"decision_anniversary : {out.get('n_anniversaries', 0)} anniversaires, "
            f"{out.get('notified', 0)} notifies"
        )
    except Exception as e:
        log.error(f"daily_decision_anniversary failed: {e}")


async def daily_counterfactual_resolve_job():
    """Boucle-de-soi V0 — resout les ancres contrefactuelles dont J+30 est passe.

    Pour chaque ancre eligible : fetch prix actuel, calcule actual vs
    counterfactual (hold strict), insere counterfactual_resolution.

    V0 = J+30 seulement. V1 ajoutera J+60/90/180 via plusieurs cycles.

    Idempotent : UNIQUE index (decision_counterfactual_id, horizon_days)
    empeche les re-insertions. Skip si prix indispo.
    """
    log.info("Daily counterfactual resolve starting")
    try:
        from intelligence import self_loop as _sl

        out = _sl.resolve_due_anchors(horizon_days=30)
        log.info(
            f"counterfactual resolve J+30 : {out['resolved']} resolved, "
            f"{out['skipped']} skipped, {out['errors']} errors"
        )
    except Exception as e:
        log.error(f"daily_counterfactual_resolve failed: {e}")
