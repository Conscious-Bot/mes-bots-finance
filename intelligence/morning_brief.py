"""Morning brief — v3 (2026-05-16): vision instantanee, <= 20 lines.

Designed for daily ritual: lisible en 5 secondes max.
TL;DR top (regime + capital). URGENT section explicit. Top 5 positions
by conviction with PnL. Footer compact.

Removed from v2:
- Active theses section (was empty due to direction=watch asymmetry uncomputable)
- Theses revisit due (bug 21/21, filter <30d old needed)
- "Open positions" raw list (too long, replaced by top 5 by conviction)
- Catalysts section (no macro_events table)

Added:
- KPI #2 timer (predictions resolved 30d / due in cluster J+28)
- Top 5 positions joined with theses.conviction
- Live PnL via yfinance fallback when theses.last_price missing
- "URGENT: nothing urgent" explicit when nothing to action
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime

from shared.display import Currency, format_billing, format_brief_position_line
from shared.sql_observability import query

log = logging.getLogger("bot")


def _macro_section():
    """Macro + credit regime (no catalysts: no macro_events table)."""
    macro_regime = "unknown"
    credit_regime = "unknown"
    try:
        from intelligence import regime as regime_mod

        r = regime_mod.detect_regime()
        macro_regime = r.get("overall", "unknown")
    except Exception as e:
        log.warning(f"macro regime fetch failed: {e}")
    try:
        from shared import macro

        cr = macro.get_credit_regime()
        credit_regime = cr.get("overall", "unknown") if isinstance(cr, dict) else str(cr)
    except Exception as e:
        log.warning(f"credit regime fetch failed: {e}")
    return {"macro_regime": macro_regime, "credit_regime": credit_regime}


def _signals_section():
    """Top materiality signals 24h + echo clusters."""
    from shared import storage

    top_signals = []
    echo_clusters = []
    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = query(
            conn,
            "SELECT s.id, COALESCE(src.name, 'unknown') AS source, s.title, s.impact_magnitude AS score "
            "FROM signals s "
            "LEFT JOIN sources src ON src.id = s.source_id "
            "WHERE s.timestamp >= datetime('now', '-24 hours') "
            "  AND s.impact_magnitude IS NOT NULL "
            "ORDER BY s.impact_magnitude DESC LIMIT 5",
            tag="morning_brief.top_signals_24h",
            fetch="all",
        )
        top_signals = [dict(r) for r in rows]
    except Exception as e:
        log.warning(f"top signals query failed: {e}")
    try:
        # echo_clusters derived from signals.echo_cluster_id distinct values 24h
        rows = query(
            conn,
            "SELECT echo_cluster_id, COUNT(*) AS n FROM signals "
            "WHERE timestamp >= datetime('now', '-24 hours') "
            "  AND echo_cluster_id IS NOT NULL "
            "GROUP BY echo_cluster_id "
            "ORDER BY n DESC LIMIT 5",
            tag="morning_brief.top_echo_clusters_24h",
            fetch="all",
        )
        echo_clusters = [{"cluster_id": r["echo_cluster_id"], "size": r["n"]} for r in rows]
    except Exception as e:
        log.warning(f"echo clusters query failed: {e}")
    conn.close()
    return {"top_signals": top_signals, "echo_clusters": echo_clusters}


def _filings_insider_section():
    """8-K HIGH/CATASTROPHIC + insider BUY clusters last 7d."""
    from shared import storage

    high_8k = []
    buy_clusters = []
    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = query(
            conn,
            "SELECT ticker, filed_at, severity, items_raw FROM filings_8k_log "
            "WHERE filed_at >= datetime('now', '-7 days') "
            "  AND severity IN ('high', 'catastrophic') "
            "ORDER BY filed_at DESC LIMIT 5",
            tag="morning_brief.high_8k_7d",
            fetch="all",
        )
        high_8k = [dict(r) for r in rows]
    except Exception as e:
        log.warning(f"8-K query failed: {e}")
    try:
        rows = query(
            conn,
            "SELECT ticker, detected_at, cluster_strength, distinct_buyers, return_30d "
            "FROM insider_buy_clusters_log "
            "WHERE detected_at >= datetime('now', '-7 days') "
            "ORDER BY detected_at DESC LIMIT 5",
            tag="morning_brief.insider_clusters_7d",
            fetch="all",
        )
        buy_clusters = [dict(r) for r in rows]
    except Exception as e:
        log.warning(f"insider clusters query failed: {e}")
    conn.close()
    return {"high_8k": high_8k, "buy_clusters": buy_clusters}


def _portfolio_section():
    """Count active positions (for header n_pos display)."""
    from shared import storage

    positions = storage.get_active_positions() or []
    return {"positions": positions}


def _discipline_section():
    """Unresolved decisions (>30 days = j30_due, >90 = overdue)."""
    from shared import storage

    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    unresolved = []
    try:
        rows = query(
            conn,
            "SELECT id, ticker, decision_type, created_at "
            "FROM decisions "
            "WHERE resolved_30d_at IS NULL OR resolved_90d_at IS NULL "
            "ORDER BY created_at ASC LIMIT 10",
            tag="morning_brief.unresolved_decisions",
            fetch="all",
        )
        for r in rows:
            try:
                created = datetime.strptime(r["created_at"][:10], "%Y-%m-%d").replace(tzinfo=UTC)
                days_old = (datetime.now(UTC) - created).days
                if days_old > 90:
                    due_status = "overdue"
                elif days_old >= 30:
                    due_status = "j30_due"
                else:
                    due_status = "pending"
            except Exception:
                due_status = "pending"
            unresolved.append(
                {
                    "id": r["id"],
                    "ticker": r["ticker"],
                    "decision_type": r["decision_type"],
                    "created_at": r["created_at"][:10],
                    "due_status": due_status,
                }
            )
    except Exception as e:
        log.warning(f"discipline section: {e}")
    conn.close()
    return {"unresolved": unresolved}


def _stats_section():
    """LLM cost today + predictions resolved last 24h."""
    from shared import storage

    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    llm_cost_today = 0.0
    try:
        row = query(
            conn,
            "SELECT SUM(cost_usd) AS total FROM llm_calls WHERE created_at >= datetime('now', '-24 hours')",
            tag="morning_brief.llm_cost_today",
            fetch="one",
        )
        llm_cost_today = float(row["total"]) if row and row["total"] else 0.0
    except Exception as e:
        log.warning(f"LLM cost query failed: {e}")
    resolved_24h = 0
    try:
        row = query(
            conn,
            "SELECT COUNT(*) AS n FROM predictions "
            "WHERE resolved_at IS NOT NULL "
            "AND datetime(resolved_at) >= datetime('now', '-24 hours')",
            tag="morning_brief.predictions_resolved_24h",
            fetch="one",
        )
        resolved_24h = int(row["n"]) if row and row["n"] else 0
    except Exception as e:
        log.warning(f"resolved-24h query failed: {e}")
    conn.close()
    return {"llm_cost_today": llm_cost_today, "predictions_resolved_24h": resolved_24h}


def _kpi_timer_section():
    """KPI #2 timer: predictions due in 28d cluster + resolved last 30d."""
    from shared import storage

    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    result = {"due_in_window": 0, "resolved_30d": 0, "days_to_cluster": 0}
    try:
        row = query(
            conn,
            "SELECT COUNT(*) AS n FROM predictions "
            "WHERE resolved_at IS NULL AND target_date <= date('now', '+28 days')",
            tag="morning_brief.predictions_due_in_window",
            fetch="one",
        )
        result["due_in_window"] = int(row["n"]) if row and row["n"] else 0
        row = query(
            conn,
            "SELECT COUNT(*) AS n FROM predictions "
            "WHERE resolved_at IS NOT NULL "
            "AND datetime(resolved_at) >= datetime('now', '-30 days')",
            tag="morning_brief.predictions_resolved_30d",
            fetch="one",
        )
        result["resolved_30d"] = int(row["n"]) if row and row["n"] else 0
        row = query(
            conn,
            "SELECT MIN(target_date) AS earliest FROM predictions WHERE resolved_at IS NULL",
            tag="morning_brief.earliest_unresolved_target",
            fetch="one",
        )
        if row and row["earliest"]:
            earliest = datetime.strptime(row["earliest"][:10], "%Y-%m-%d").replace(tzinfo=UTC)
            result["days_to_cluster"] = (earliest - datetime.now(UTC)).days
    except Exception as e:
        log.warning(f"kpi timer section: {e}")
    conn.close()
    return result


def _positions_top5_section():
    """Top 5 positions by conviction (join theses) + live PnL via yfinance."""
    from shared import storage

    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    top5 = []
    try:
        rows = query(
            conn,
            "SELECT p.ticker, p.qty, p.avg_cost, "
            "       t.conviction, t.direction "
            "FROM positions p "
            "LEFT JOIN theses t ON t.ticker = p.ticker AND t.status='active' "
            "WHERE p.status='open' "
            "ORDER BY COALESCE(t.conviction, 0) DESC, p.ticker ASC "
            "LIMIT 10",
            tag="morning_brief.top_positions_with_conviction",
            fetch="all",
        )
        for r in rows:
            ticker = r["ticker"]
            try:
                from shared.ticker_names import get_short_name

                name = get_short_name(ticker) or ticker
            except Exception:
                name = ticker
            # Day 13 Bug FX-2 fix: avg_cost stored in EUR (Day 7 migration),
            # NOT native as ADR 004 Batch 5 comment suggested. Storage migration
            # to native canonical never completed -- only code was changed.
            # Empirical: SK hynix avg_cost=1043 (matches EUR per share, not KRW).
            # Fix: uniform EUR -> USD conversion for both avg_cost and last_price.
            try:
                from shared.prices import get_current_price_in_usd, get_fx_rate

                fx_eur_to_usd = get_fx_rate("EUR", "USD") or 1.1655
            except Exception:
                fx_eur_to_usd = 1.1655
            # 21/05/2026: dropped t.last_price stale-cache read (caused /brief
            # vs /portfolio divergence up to -7% on 6920.T after laptop sleep
            # missed price_monitor cron). Now uses canonical fresh-yfinance
            # path, same as bot/handlers/positions.py:148 in cmd_portfolio.
            try:
                last_price = get_current_price_in_usd(ticker)
            except Exception:
                last_price = None
            avg_cost_usd = r["avg_cost"] * fx_eur_to_usd if r["avg_cost"] else None
            pnl_pct = None
            if last_price and avg_cost_usd:
                pnl_pct = (last_price / avg_cost_usd - 1) * 100
            value = (r["qty"] * last_price) if (last_price and r["qty"]) else None
            top5.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "qty": r["qty"],
                    "avg_cost": avg_cost_usd,
                    "last_price": last_price,
                    "conviction": r["conviction"],
                    "pnl_pct": pnl_pct,
                    "value": value,
                }
            )
    except Exception as e:
        log.warning(f"positions top5 section: {e}")
    conn.close()
    return top5


def _movers_24h_section() -> dict | None:
    """Top 3 positions by absolute 24h price move magnitude.

    Returns:
        list[dict] sorted by |pct| desc, filtered to |pct| > 0.5%, max 3 items
            keys: ticker, pct, prev_usd, now_usd, conviction
        Empty list [] if no movers >0.5% (quiet day or weekend)
        None if yfinance batch call fails (display "data unavailable")

    Uses yfinance batch download (single API call for all positions) to
    minimize rate-limit risk. Pct computed from native-currency close
    (FX-invariant). USD values for display via get_current_price_in_usd
    (canonical, matches /portfolio + /brief top5 post commit 666863f).
    """
    from shared import storage

    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = query(
            conn,
            "SELECT p.ticker, t.conviction FROM positions p "
            "LEFT JOIN theses t ON t.ticker = p.ticker AND t.status='active' "
            "WHERE p.status='open'",
            tag="morning_brief.movers_24h_positions",
            fetch="all",
        )
    except Exception as e:
        log.warning(f"movers 24h DB fetch fail: {e}")
        conn.close()
        return None
    conn.close()

    if not rows:
        return {"up": [], "down": []}

    tickers = [r["ticker"] for r in rows]
    conviction_map = {r["ticker"]: r["conviction"] for r in rows}

    try:
        import yfinance as yf

        hist = yf.download(tickers, period="2d", interval="1d", progress=False, group_by="ticker")
    except Exception as e:
        log.warning(f"movers 24h yfinance batch fail: {e}")
        return None

    try:
        from shared.prices import get_current_price_in_usd
    except Exception:
        return None

    movers: list[dict] = []
    for ticker in tickers:
        try:
            ticker_data = hist[ticker] if len(tickers) > 1 else hist
            closes = ticker_data["Close"].dropna()
            if len(closes) < 2:
                continue
            prev_native = float(closes.iloc[-2])
            now_native = float(closes.iloc[-1])
            if prev_native <= 0:
                continue
            pct = (now_native - prev_native) / prev_native * 100
            if abs(pct) < 0.5:
                continue
            now_usd = get_current_price_in_usd(ticker)
            if not now_usd:
                continue
            prev_usd = now_usd / (1 + pct / 100) if pct != -100 else 0
            movers.append(
                {
                    "ticker": ticker,
                    "pct": pct,
                    "prev_usd": prev_usd,
                    "now_usd": now_usd,
                    "conviction": conviction_map.get(ticker),
                }
            )
        except Exception as e:
            log.warning(f"movers 24h compute fail for {ticker}: {e}")
            continue

    if not movers:
        return {"up": [], "down": []}
    ups = sorted([m for m in movers if m["pct"] > 0], key=lambda m: -m["pct"])[:3]
    downs = sorted([m for m in movers if m["pct"] < 0], key=lambda m: m["pct"])[:3]
    return {"up": ups, "down": downs}


def _format_movers(movers_data: dict | None) -> list[str]:
    """Format movers section (UP + DOWN) for /brief display.

    Args:
        movers_data: from _movers_24h_section()
            None → fetch failed
            {"up": [], "down": []} → quiet day
            {"up": [...], "down": [...]} → render sections

    Severity emoji rules:
        UP: >+4% green 🟢, 0 to +4% yellow 🟡
        DOWN: -4% to 0% orange 🟠, <-4% red 🔴
    """
    if movers_data is None:
        return ["━ MOVERS 24h ━", "data unavailable"]

    ups = movers_data.get("up", [])
    downs = movers_data.get("down", [])

    if not ups and not downs:
        return ["━ MOVERS 24h ━", "calme (aucun mover >0.5%)"]

    lines = []

    if ups:
        lines.append(f"━ MOVERS UP 24h (top {len(ups)}) ━")
        for m in ups:
            pct = m["pct"]
            emoji = "🟢" if pct > 4 else "🟡"
            ticker = m["ticker"]
            conv = m["conviction"]
            conv_str = f"c{conv}" if conv else "c?"
            pct_str = f"+{pct:.1f}%"
            lines.append(f"{emoji} {ticker:9} {conv_str:<3}  {pct_str:>7}   ${m['prev_usd']:.0f} → ${m['now_usd']:.0f}")

    if downs:
        if ups:
            lines.append("")
        lines.append(f"━ MOVERS DOWN 24h (top {len(downs)}) ━")
        for m in downs:
            pct = m["pct"]
            emoji = "🔴" if pct < -4 else "🟠"
            ticker = m["ticker"]
            conv = m["conviction"]
            conv_str = f"c{conv}" if conv else "c?"
            pct_str = f"{pct:.1f}%"
            lines.append(f"{emoji} {ticker:9} {conv_str:<3}  {pct_str:>7}   ${m['prev_usd']:.0f} → ${m['now_usd']:.0f}")

    return lines


def build_brief():
    return {
        "date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        "macro": _macro_section(),
        "signals": _signals_section(),
        "filings_insider": _filings_insider_section(),
        "portfolio": _portfolio_section(),
        "discipline": _discipline_section(),
        "stats": _stats_section(),
        "kpi_timer": _kpi_timer_section(),
        "positions_top5": _positions_top5_section(),
        "movers": _movers_24h_section(),
    }


def format_brief(brief):
    """Brief canonical (TG output spec 21/05/2026): header + sections with severity emoji."""
    lines = []
    m = brief["macro"]
    lines.append(f"☀️ MORNING BRIEF — {brief['date']}")
    lines.append(f"Regime: {m['macro_regime']}  |  Credit: {m['credit_regime']}")
    lines.append("")

    top10 = brief.get("positions_top5", [])  # key preserved for backward-compat
    p = brief["portfolio"]
    n_pos = len(p.get("positions", []))
    if top10:
        lines.append(f"━ POSITIONS ({n_pos} active) — top {len(top10)} by conviction ━")
        for pos in top10:
            lines.append(
                format_brief_position_line(
                    ticker=pos["ticker"],
                    name=pos.get("name"),
                    conviction=pos["conviction"],
                    value=pos.get("value"),
                    pnl_pct=pos["pnl_pct"],
                    currency=Currency.USD,
                )
            )
    else:
        lines.append(f"━ POSITIONS ({n_pos} active) — no conviction data ━")
    lines.append("")

    # URGENT section with severity emoji by item type
    urgent_items = []
    kpi = brief.get("kpi_timer", {})
    if kpi.get("due_in_window", 0) > 0:
        days = kpi.get("days_to_cluster", 0)
        resolved = kpi.get("resolved_30d", 0)
        urgent_items.append(f"🟡 KPI #2: {resolved}/5 resolved 30d  |  {kpi['due_in_window']} in 28d, next J-{days}")
    d = brief["discipline"]
    n_unresolved = len(d.get("unresolved", []))
    if n_unresolved > 0:
        tickers = ", ".join(sorted({r["ticker"] for r in d["unresolved"][:5]}))
        urgent_items.append(f"🟡 Unresolved decisions: {n_unresolved} ({tickers})")
    fi = brief["filings_insider"]
    n_8k = len(fi.get("high_8k", []))
    if n_8k > 0:
        urgent_items.append(f"🔴 NEW 8-K HIGH/CATASTROPHIC: {n_8k}")
    n_buy_clusters = len(fi.get("buy_clusters", []))
    if n_buy_clusters > 0:
        urgent_items.append(f"🟢 NEW insider BUY clusters: {n_buy_clusters}")

    if urgent_items:
        lines.append(f"━ URGENT ({len(urgent_items)}) ━")
        for item in urgent_items:
            lines.append(item)
    else:
        lines.append("━ URGENT (0) ━")
        lines.append("nothing urgent")
    lines.append("")

    # MOVERS 24h section (UP + DOWN, severity emoji built in _format_movers)
    movers = brief.get("movers")
    lines.extend(_format_movers(movers))
    lines.append("")

    # SIGNALS & COST section
    s = brief["stats"]
    sig = brief["signals"]
    n_sig = len(sig.get("top_signals", []))
    n_echo = len(sig.get("echo_clusters", []))
    lines.append("━ SIGNALS & COST ━")
    lines.append(f"Signals 24h:  {n_sig} top, {n_echo} echo")
    lines.append(f"LLM 24h:      {format_billing(s['llm_cost_today'])}")

    return ["\n".join(lines)]
