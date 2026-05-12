"""Phase Brief — Morning ritual aggregator (corrected APIs)."""
import logging
from datetime import datetime, timedelta, timezone
log = logging.getLogger(__name__)


def _macro_section():
    regime = "unknown"
    credit = "unknown"
    try:
        from shared import macro as _macro
        snap = _macro.get_macro_snapshot()
        if isinstance(snap, dict):
            vix = snap.get("vix")
            yc = snap.get("yield_curve_spread")
            dxy = snap.get("dxy")
            parts = []
            if vix is not None:
                parts.append(f"VIX={float(vix):.1f}")
            if yc is not None:
                parts.append(f"YC={float(yc):+.2f}")
            if dxy is not None:
                parts.append(f"DXY={float(dxy):.1f}")
            if parts:
                regime = " | ".join(parts)
    except Exception as e:
        log.warning(f"macro snapshot failed: {e}")
    try:
        from shared import macro as _macro
        reg = _macro.get_credit_regime()
        if isinstance(reg, dict):
            try:
                credit = _macro.format_credit_regime(reg)
                # if too verbose, truncate
                if "\n" in credit:
                    credit = credit.split("\n")[0][:100]
            except Exception:
                credit = str(reg.get("label") or reg.get("regime") or reg)[:100]
    except Exception as e:
        log.warning(f"credit regime failed: {e}")
    catalysts = []
    try:
        from shared import storage
        import sqlite3
        conn = sqlite3.connect(storage._DB_PATH)
        conn.row_factory = sqlite3.Row
        cutoff = (datetime.now() + timedelta(days=21)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT name, event_date FROM macro_events "
            "WHERE event_date BETWEEN date('now') AND ? "
            "ORDER BY event_date ASC LIMIT 5", (cutoff,)
        ).fetchall()
        for r in rows:
            catalysts.append(f"{r['event_date']} {r['name']}")
        conn.close()
    except Exception:
        pass
    return {"macro_regime": regime, "credit_regime": credit, "catalysts": catalysts}


def _signals_section():
    from shared import storage
    import sqlite3
    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    top_signals = []
    try:
        rows = conn.execute(
            "SELECT s.id, s.title, s.score, s.entities, s.timestamp, src.name AS source_name "
            "FROM signals s LEFT JOIN sources src ON s.source_id = src.id "
            "WHERE s.timestamp >= ? AND s.score IS NOT NULL "
            "ORDER BY s.score DESC LIMIT 5", (cutoff,)
        ).fetchall()
        for r in rows:
            top_signals.append({
                "title": r["title"] or "?",
                "score": r["score"],
                "source": r["source_name"] or "?",
                "entities": r["entities"] or "[]",
            })
    except Exception as e:
        log.warning(f"signals section: {e}")
    conn.close()
    echo_clusters = []
    try:
        from shared import echo
        if hasattr(echo, "get_recent_multi_source_clusters"):
            clusters = echo.get_recent_multi_source_clusters(window_hours=24, min_unique_sources=2)
            for c in clusters[:5]:
                echo_clusters.append(c)
    except Exception as e:
        log.warning(f"echo section: {e}")
    return {"top_signals": top_signals, "echo_clusters": echo_clusters}


def _filings_insider_section():
    from shared import storage
    import sqlite3
    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    high_8k = []
    try:
        rows = conn.execute(
            "SELECT ticker, filed_at, severity, severity_reason, items_raw "
            "FROM filings_8k_log "
            "WHERE date(filed_at) >= date('now', '-7 days') "
            "AND severity IN ('catastrophic', 'high') "
            "ORDER BY filed_at DESC LIMIT 10"
        ).fetchall()
        for r in rows:
            high_8k.append(dict(r))
    except Exception as e:
        log.warning(f"8k section: {e}")
    buy_clusters = []
    try:
        rows = conn.execute(
            "SELECT ticker, detected_at, cluster_strength, distinct_buyers, total_buy_m, return_30d "
            "FROM insider_buy_clusters_log "
            "WHERE date(detected_at) >= date('now', '-7 days') "
            "ORDER BY detected_at DESC LIMIT 5"
        ).fetchall()
        for r in rows:
            buy_clusters.append(dict(r))
    except Exception as e:
        log.warning(f"buy cluster section: {e}")
    conn.close()
    return {"high_8k": high_8k, "buy_clusters": buy_clusters}


def _portfolio_section():
    from intelligence import asymmetry
    theses_asym = asymmetry.compute_portfolio_asymmetry()
    from shared import storage
    positions = storage.get_active_positions() or []
    return {"theses_asym": theses_asym, "positions": positions}


def _discipline_section():
    from shared import storage
    import sqlite3
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
                "id": r["id"], "ticker": r["ticker"],
                "decision_type": r["decision_type"],
                "created_at": r["created_at"][:10],
                "due_status": due_status,
            })
    except Exception as e:
        log.warning(f"discipline section: {e}")
    conn.close()
    revisits = []
    try:
        from intelligence import thesis as thesis_mod
        if hasattr(thesis_mod, "get_revisit_due"):
            revisits = thesis_mod.get_revisit_due() or []
    except Exception:
        pass
    return {"unresolved": unresolved, "revisits_due": revisits}


def _stats_section():
    from shared import storage
    import sqlite3
    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    llm_cost_today = 0.0
    try:
        row = conn.execute(
            "SELECT SUM(cost_usd) AS total FROM llm_calls WHERE date(created_at) = date('now')"
        ).fetchone()
        llm_cost_today = float(row["total"]) if row and row["total"] else 0.0
    except Exception:
        pass
    resolved_24h = 0
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM predictions "
            "WHERE resolved_at IS NOT NULL AND datetime(resolved_at) >= datetime('now', '-24 hours')"
        ).fetchone()
        resolved_24h = int(row["n"]) if row and row["n"] else 0
    except Exception:
        pass
    conn.close()
    return {"llm_cost_today": llm_cost_today, "predictions_resolved_24h": resolved_24h}


def build_brief():
    return {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "macro": _macro_section(),
        "signals": _signals_section(),
        "filings_insider": _filings_insider_section(),
        "portfolio": _portfolio_section(),
        "discipline": _discipline_section(),
        "stats": _stats_section(),
    }


def format_brief(brief):
    chunks = []
    lines = [f"☀ MORNING BRIEF — {brief['date']}", ""]
    m = brief["macro"]
    lines.append("━━━ MACRO & REGIME ━━━")
    lines.append(f"Macro: {m['macro_regime']}")
    lines.append(f"Credit: {m['credit_regime']}")
    if m["catalysts"]:
        lines.append("Catalysts ≤21j:")
        for c in m["catalysts"][:5]:
            lines.append(f"  {c}")
    lines.append("")

    fi = brief["filings_insider"]
    lines.append("━━━ FILINGS & INSIDER (7j) ━━━")
    if fi["high_8k"]:
        lines.append(f"NEW 8-K HIGH+CATASTROPHIC: {len(fi['high_8k'])}")
        for r in fi["high_8k"][:5]:
            lines.append(f"  {r['ticker']} {r['filed_at'][:10]} [{r['severity']}] {r['items_raw']}")
    else:
        lines.append("NEW 8-K HIGH+CATASTROPHIC: 0")
    if fi["buy_clusters"]:
        lines.append(f"NEW Insider BUY clusters: {len(fi['buy_clusters'])}")
        for r in fi["buy_clusters"][:5]:
            ret = f" J+30={r['return_30d']:+.1%}" if r.get("return_30d") is not None else " (pending)"
            lines.append(f"  {r['ticker']} {r['detected_at'][:10]} {r['cluster_strength']} n={r['distinct_buyers']}{ret}")
    else:
        lines.append("NEW Insider BUY clusters: 0")
    chunks.append("\n".join(lines))

    lines = []
    p = brief["portfolio"]
    lines.append("━━━ PORTFOLIO ━━━")
    if p["theses_asym"]:
        lines.append(f"Active theses ({len(p['theses_asym'])}):")
        for r in p["theses_asym"]:
            if "asymmetry_ratio" in r:
                icon = {"STRONG_RUN": "🟢🟢", "FAVORABLE": "🟢", "BALANCED": "🟡",
                        "UNFAVORABLE": "🟠", "FLIPPED": "🔴",
                        "STOP_BREACHED": "⛔", "TARGET_HIT": "🎯"}.get(r["verdict"], "?")
                ratio = r["asymmetry_ratio"]
                ratio_str = "TARGET" if ratio >= 999 else f"{ratio:.2f}x"
                lines.append(f"  {icon} {r['ticker']:6s} asym={ratio_str:>7s}  → {r['verdict']}")
    else:
        lines.append("Active theses: 0")
    if p["positions"]:
        lines.append(f"Open positions ({len(p['positions'])}):")
        for pos in p["positions"]:
            lines.append(f"  {pos['ticker']} {pos.get('qty')}@${pos.get('avg_cost', 0):.2f}")
    else:
        lines.append("Open positions: 0")
    lines.append("")
    d = brief["discipline"]
    lines.append("━━━ DISCIPLINE PENDING ━━━")
    if d["unresolved"]:
        lines.append(f"Unresolved decisions ({len(d['unresolved'])}):")
        for r in d["unresolved"][:5]:
            lines.append(f"  #{r['id']} {r['ticker']} {r['decision_type']} ({r['due_status']}) {r['created_at']}")
    else:
        lines.append("Unresolved decisions: 0")
    revisit_count = len(d["revisits_due"]) if d["revisits_due"] else 0
    lines.append(f"Theses revisit due: {revisit_count}")
    lines.append("")
    s = brief["stats"]
    lines.append("━━━ STATS ━━━")
    lines.append(f"LLM spend today: ${s['llm_cost_today']:.2f}")
    lines.append(f"Predictions resolved 24h: {s['predictions_resolved_24h']}")
    chunks.append("\n".join(lines))

    sig = brief["signals"]
    if sig["top_signals"] or sig["echo_clusters"]:
        lines = ["━━━ SIGNALS 24h ━━━"]
        if sig["top_signals"]:
            lines.append(f"Top materiality ({len(sig['top_signals'])}):")
            for s in sig["top_signals"][:5]:
                title = (s["title"] or "")[:90]
                lines.append(f"  [{s['score']}] {s['source']}: {title}")
        else:
            lines.append("Top materiality: 0")
        if sig["echo_clusters"]:
            lines.append(f"\nEcho clusters multi-source ({len(sig['echo_clusters'])}):")
            for c in sig["echo_clusters"][:5]:
                if isinstance(c, dict):
                    ids = c.get("signal_ids") or c.get("ids") or []
                    sz = len(ids) if isinstance(ids, list) else "?"
                    lines.append(f"  cluster {c.get('cluster_id', '?')}: {sz} signals")
                else:
                    lines.append(f"  {c}")
        else:
            lines.append("Echo clusters: 0")
        chunks.append("\n".join(lines))
    return chunks
