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
    """
    try:
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
    alerts = [r for r in new_logged if r["severity"] in ("catastrophic", "high")]
    if alerts:
        msg = f"8-K ALERTS ({len(alerts)} high+catastrophic)\n\n"
        for r in alerts:
            msg += filings_8k.format_8k_alert(r) + "\n\n"
        notify.send_text(msg.strip())
    log.info(f"8-K scan: {len(new_logged)} new logged, {len(alerts)} alerted")
