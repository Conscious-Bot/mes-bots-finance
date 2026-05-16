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
from datetime import datetime

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
        rows = conn.execute(
            "SELECT s.id, COALESCE(src.name, 'unknown') AS source, s.title, s.impact_magnitude AS score "
            "FROM signals s "
            "LEFT JOIN sources src ON src.id = s.source_id "
            "WHERE s.timestamp >= datetime('now', '-24 hours') "
            "  AND s.impact_magnitude IS NOT NULL "
            "ORDER BY s.impact_magnitude DESC LIMIT 5"
        ).fetchall()
        top_signals = [dict(r) for r in rows]
    except Exception as e:
        log.warning(f"top signals query failed: {e}")
    try:
        # echo_clusters derived from signals.echo_cluster_id distinct values 24h
        rows = conn.execute(
            "SELECT echo_cluster_id, COUNT(*) AS n FROM signals "
            "WHERE timestamp >= datetime('now', '-24 hours') "
            "  AND echo_cluster_id IS NOT NULL "
            "GROUP BY echo_cluster_id "
            "ORDER BY n DESC LIMIT 5"
        ).fetchall()
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
        rows = conn.execute(
            "SELECT ticker, filed_at, severity, items_raw FROM filings_8k_log "
            "WHERE filed_at >= datetime('now', '-7 days') "
            "  AND severity IN ('high', 'catastrophic') "
            "ORDER BY filed_at DESC LIMIT 5"
        ).fetchall()
        high_8k = [dict(r) for r in rows]
    except Exception as e:
        log.warning(f"8-K query failed: {e}")
    try:
        rows = conn.execute(
            "SELECT ticker, detected_at, cluster_strength, distinct_buyers, return_30d "
            "FROM insider_buy_clusters_log "
            "WHERE detected_at >= datetime('now', '-7 days') "
            "ORDER BY detected_at DESC LIMIT 5"
        ).fetchall()
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
        rows = conn.execute(
            "SELECT id, ticker, decision_type, created_at "
            "FROM decisions "
            "WHERE resolved_30d_at IS NULL OR resolved_90d_at IS NULL "
            "ORDER BY created_at ASC LIMIT 10"
        ).fetchall()
        for r in rows:
            try:
                created = datetime.strptime(r["created_at"][:10], "%Y-%m-%d")
                days_old = (datetime.now() - created).days
                if days_old > 90:
                    due_status = "overdue"
                elif days_old >= 30:
                    due_status = "j30_due"
                else:
                    due_status = "pending"
            except Exception:
                due_status = "pending"
            unresolved.append({
                "id": r["id"],
                "ticker": r["ticker"],
                "decision_type": r["decision_type"],
                "created_at": r["created_at"][:10],
                "due_status": due_status,
            })
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
        row = conn.execute(
            "SELECT SUM(cost_usd) AS total FROM llm_calls "
            "WHERE date(created_at) = date('now')"
        ).fetchone()
        llm_cost_today = float(row["total"]) if row and row["total"] else 0.0
    except Exception as e:
        log.warning(f"LLM cost query failed: {e}")
    resolved_24h = 0
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM predictions "
            "WHERE resolved_at IS NOT NULL "
            "AND datetime(resolved_at) >= datetime('now', '-24 hours')"
        ).fetchone()
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
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM predictions "
            "WHERE resolved_at IS NULL AND target_date <= date('now', '+28 days')"
        ).fetchone()
        result["due_in_window"] = int(row["n"]) if row and row["n"] else 0
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM predictions "
            "WHERE resolved_at IS NOT NULL "
            "AND datetime(resolved_at) >= datetime('now', '-30 days')"
        ).fetchone()
        result["resolved_30d"] = int(row["n"]) if row and row["n"] else 0
        row = conn.execute(
            "SELECT MIN(target_date) AS earliest FROM predictions WHERE resolved_at IS NULL"
        ).fetchone()
        if row and row["earliest"]:
            earliest = datetime.strptime(row["earliest"][:10], "%Y-%m-%d")
            result["days_to_cluster"] = (earliest - datetime.now()).days
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
        rows = conn.execute(
            "SELECT p.ticker, p.qty, p.avg_cost, "
            "       t.conviction, t.direction, t.last_price "
            "FROM positions p "
            "LEFT JOIN theses t ON t.ticker = p.ticker AND t.status='active' "
            "WHERE p.status='open' "
            "ORDER BY COALESCE(t.conviction, 0) DESC, p.ticker ASC "
            "LIMIT 5"
        ).fetchall()
        for r in rows:
            ticker = r["ticker"]
            try:
                from shared.ticker_names import get_short_name
                name = get_short_name(ticker) or ticker
            except Exception:
                name = ticker
            last_price = r["last_price"]
            if last_price is None:
                try:
                    from shared.prices import get_current_price_in_eur
                    last_price = get_current_price_in_eur(ticker)
                except Exception:
                    last_price = None
            pnl_pct = None
            if last_price and r["avg_cost"]:
                pnl_pct = (last_price / r["avg_cost"] - 1) * 100
            value_eur = (r["qty"] * last_price) if (last_price and r["qty"]) else None
            top5.append({
                "ticker": ticker,
                "name": name,
                "qty": r["qty"],
                "avg_cost": r["avg_cost"],
                "last_price": last_price,
                "conviction": r["conviction"],
                "pnl_pct": pnl_pct,
                "value_eur": value_eur,
            })
    except Exception as e:
        log.warning(f"positions top5 section: {e}")
    conn.close()
    return top5


def build_brief():
    return {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "macro": _macro_section(),
        "signals": _signals_section(),
        "filings_insider": _filings_insider_section(),
        "portfolio": _portfolio_section(),
        "discipline": _discipline_section(),
        "stats": _stats_section(),
        "kpi_timer": _kpi_timer_section(),
        "positions_top5": _positions_top5_section(),
    }


def format_brief(brief):
    """Brief v3: vision instantanee, <= 20 lines."""
    lines = []
    m = brief["macro"]
    lines.append(f"BRIEF {brief['date']}")
    lines.append(f"Regime: {m['macro_regime']}  |  Credit: {m['credit_regime']}")
    lines.append("")

    top5 = brief.get("positions_top5", [])
    p = brief["portfolio"]
    n_pos = len(p.get("positions", []))
    if top5:
        lines.append(f"POSITIONS ({n_pos} active) - top 5 by conviction")
        for pos in top5:
            tk = pos["ticker"]
            name = pos.get("name", tk)[:22]
            conv = pos["conviction"]
            conv_str = f"c{conv}" if conv else "c-"
            pnl = pos["pnl_pct"]
            value = pos.get("value_eur")
            if value is None:
                lines.append(f"  {tk:9s} {name:22s} {conv_str}  (price n/a)")
            elif pnl is not None and abs(pnl) > 200:
                # Currency mismatch guard (legacy, should not fire post-A2-1)
                lines.append(f"  {tk:9s} {name:22s} {conv_str}  (check fx)")
            else:
                pnl_str = f"{pnl:+.1f}%" if pnl is not None else "n/a"
                lines.append(
                    f"  {tk:9s} {name:22s} {conv_str}  €{value:>6,.0f}  {pnl_str}"
                )
    else:
        lines.append(f"POSITIONS ({n_pos} active) - no conviction data")
    lines.append("")

    urgent_items = []
    kpi = brief.get("kpi_timer", {})
    if kpi.get("due_in_window", 0) > 0:
        days = kpi.get("days_to_cluster", 0)
        resolved = kpi.get("resolved_30d", 0)
        urgent_items.append(
            f"KPI #2: {resolved}/5 resolved 30d  |  {kpi['due_in_window']} due in J-{days}"
        )
    d = brief["discipline"]
    n_unresolved = len(d.get("unresolved", []))
    if n_unresolved > 0:
        tickers = ", ".join(sorted({r["ticker"] for r in d["unresolved"][:5]}))
        urgent_items.append(f"Unresolved decisions: {n_unresolved} ({tickers})")
    fi = brief["filings_insider"]
    n_8k = len(fi.get("high_8k", []))
    if n_8k > 0:
        urgent_items.append(f"NEW 8-K HIGH/CATASTROPHIC: {n_8k}")
    n_buy_clusters = len(fi.get("buy_clusters", []))
    if n_buy_clusters > 0:
        urgent_items.append(f"NEW insider BUY clusters: {n_buy_clusters}")

    if urgent_items:
        lines.append("URGENT")
        for item in urgent_items:
            lines.append(f"  {item}")
    else:
        lines.append("URGENT: nothing urgent.")
    lines.append("")

    s = brief["stats"]
    sig = brief["signals"]
    n_sig = len(sig.get("top_signals", []))
    n_echo = len(sig.get("echo_clusters", []))
    lines.append(
        f"Signals 24h: {n_sig} top, {n_echo} echo  |  LLM today: ${s['llm_cost_today']:.2f}"
    )

    return ["\n".join(lines)]
