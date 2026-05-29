"""Echo + crypto + macro + materiality + orphan + override + price_check handlers.

Extracted from bot/main.py Sprint 1.1 chunk 9 (2026-05-16, Day 5).
Mechanical move only, zero logic change.

Module exports (8 handlers):
- cmd_orphan_tickers : /orphan_tickers — universe/portfolio mismatch
- cmd_echo_recent    : /echo_recent — recent signal clusters
- cmd_macro          : /macro — upcoming macro calendar
- cmd_price_check    : /price_check — thesis trigger gates
- cmd_override       : /override — manage thesis override list
- cmd_crypto         : /crypto — BTC/ETH zones
- cmd_credit         : /credit — HY credit regime
- cmd_materiality    : /materiality — materiality_v2 breakdown debug

DEPS migrated (top-level):
- from intelligence.calendar import format_macro_calendar (for cmd_macro)
- from intelligence.price_monitor import check_thesis_triggers, list_overrides, record_override
"""

from __future__ import annotations

import contextlib

from intelligence.calendar import format_macro_calendar
from intelligence.price_monitor import check_thesis_triggers, list_overrides, record_override
from shared import crypto as crypto_mod

__all__ = [
    "cmd_credit",
    "cmd_crypto",
    "cmd_echo_recent",
    "cmd_macro",
    "cmd_materiality",
    "cmd_orphan_tickers",
    "cmd_override",
    "cmd_price_check",
]


async def cmd_orphan_tickers(update, ctx):  # noqa: ARG001
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
    counter: Counter[str] = Counter()
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


async def cmd_echo_recent(update, ctx):  # noqa: ARG001
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


async def cmd_macro(update, context):
    """Sprint 1.2 Phase G dispatcher — /macro family.

    Usage:
      /macro              → TL;DR upcoming FOMC/NFP/CPI events (90d)
      /macro regime       → detect macro regime (delegates cmd_regime)
      /macro credit       → credit regime view (delegates cmd_credit)
      /macro calendar     → earnings calendar 60d + alerts (delegates cmd_calendar)

    Backward-compat aliases preserved 1 release cycle:
      /regime, /credit, /calendar
    """
    args = context.args or []
    if args:
        action = args[0].lower()
        if action == "regime":
            from bot.handlers.regime_calendar import cmd_regime

            await cmd_regime(update, context)
            return
        if action == "credit":
            await cmd_credit(update, context)
            return
        if action == "calendar":
            from bot.handlers.regime_calendar import cmd_calendar

            await cmd_calendar(update, context)
            return
        await update.message.reply_text(
            f"Unknown action: '{action}'\n"
            "Valid: regime, credit, calendar\n"
            "See /macro for default (TL;DR upcoming events)."
        )
        return

    # Default: TL;DR upcoming macro events 90d
    try:
        msg = format_macro_calendar(90)
    except Exception as e:
        msg = f"Error fetching macro calendar: {e}"
    await update.message.reply_text(msg)


async def cmd_price_check(update, ctx):  # noqa: ARG001
    """Legacy alias: /price_check -> /thesis check_triggers."""
    await _price_check_impl(update)


async def _price_check_impl(update) -> None:
    """Internal: trigger price check. Used by /price_check and /thesis check_triggers."""
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


async def cmd_override(update, ctx):  # noqa: ARG001
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

    # Sprint 3 — Adversarial copilot pressure-test BEFORE recording override
    # (override = strong intent to deviate from thesis defined exits, prime target)
    _copilot_response = None
    _copilot_intervention_id = None
    try:
        from intelligence import decision_copilot
        from shared import storage as _storage_cp

        # Map level → copilot decision_type for context
        _cp_dtype = {"partial": "partial_exit", "full": "full_exit", "stop": "override"}.get(level, "override")

        # Use last known price from thesis if available (override has no price arg)
        _thesis_for_price = _storage_cp.get_thesis_by_ticker(ticker, status="active") or {}
        _cp_price = _thesis_for_price.get("last_price") or _thesis_for_price.get("entry_price") or 0.0

        _copilot_response, _copilot_intervention_id = decision_copilot.run_pre_trade_copilot(
            ticker=ticker, decision_type=_cp_dtype, reasoning=reason, price=_cp_price,
        )
    except Exception as cp_err:
        import logging as _cp_logging

        _cp_logging.getLogger("bot.override").warning(
            f"copilot pre-trade failed for /override {ticker}: {type(cp_err).__name__}: {cp_err}"
        )

    try:
        oid = record_override(ticker, level, reason)
        msg_lines = [
            f"OK Override #{oid} captured: {ticker}/{level}",
            f"  Reason: {reason}",
            "  Stored for BiasDetector training.",
        ]
        if _copilot_response:
            from intelligence.decision_copilot import format_brief_for_telegram

            cp_text = format_brief_for_telegram(_copilot_response)
            if cp_text:
                msg_lines.append(cp_text)
        await update.message.reply_text("\n".join(msg_lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_crypto(update, ctx):  # noqa: ARG001
    """Show crypto cycle indicators (funding, OI, Mayer Multiple)."""
    try:
        z = crypto_mod.compute_crypto_zone()
        msg = crypto_mod.format_crypto_zone(z)
    except Exception as e:
        msg = f"Error: {e}"
    await update.message.reply_text(msg)


async def cmd_credit(update, ctx):  # noqa: ARG001
    """Regime de credit macro (HY spreads, conditions)."""
    try:
        from shared import macro

        r = macro.get_credit_regime()
        await update.message.reply_text(macro.format_credit_regime(r))
    except Exception as e:
        await update.message.reply_text("Error: " + str(e))


async def cmd_materiality(update, ctx):  # noqa: ARG001
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
            "  regime: "
            + str(m.get("regime_snapshot") or "?")
            + " | credit: "
            + str(m.get("credit_regime_snapshot") or "?"),
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
