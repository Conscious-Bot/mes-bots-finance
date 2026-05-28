"""Journal + bias + history handlers.

Extracted from bot/main.py Sprint 1.1 chunk 8 (2026-05-16, Day 5).
Mechanical move only, zero logic change.

Module exports (7 handlers):
- cmd_history              : /history [TICKER] — decision history
- cmd_journal              : /journal [TICKER] — recent decisions detail
- cmd_journal_review       : /journal_review N — single decision deep view
- cmd_journal_unresolved   : /journal_unresolved [days] — pending resolutions
- cmd_journal_tag          : /journal_tag N TAG — override mistake_tag
- cmd_position_history     : /position_history [TICKER] — position events log
- cmd_bias_review          : /bias_review — cognitive bias patterns aggregate

DEPS (all inline lazy, zero top-level migration needed):
- shared.storage as storage_mod (20x usage across handlers)
- shared.macro (credit regime context)
- intelligence.journal, intelligence.bias_tagger, intelligence.regime
- yfinance, sqlite3, datetime
"""

from __future__ import annotations

__all__ = [
    "cmd_bias_review",
    "cmd_history",
    "cmd_journal",
    "cmd_journal_review",
    "cmd_journal_tag",
    "cmd_journal_unresolved",
    "cmd_position_history",
]


async def cmd_history(update, ctx):  # noqa: ARG001
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
    """Sprint 1.2 Phase H dispatcher - /journal family.

    Usage:
      /journal TICKER type conv reasoning     -> log decision (default action)
      /journal review [TICKER]                -> stats + recent decisions
      /journal unresolved                     -> awaiting J+30 / J+90 resolution
      /journal tag <decision_id> <new_tag>    -> override mistake_tag manually

    Types: entry|scale_in|partial_exit|full_exit|override|no_action_flag
    Abbrev: e|si|pe|fe|o|nf

    Backward-compat aliases preserved 1 release cycle:
      /journal_review, /journal_unresolved, /journal_tag

    NOT touched: /journal_audit (Bloc 5 K separate dimension).
    """
    args = ctx.args or []
    if args and args[0].lower() in ("review", "unresolved", "tag"):
        action = args[0].lower()
        if action == "review":
            ticker_filter = args[1].upper() if len(args) > 1 else None
            await _journal_review_impl(update, ticker_filter)
            return
        if action == "unresolved":
            await _journal_unresolved_impl(update)
            return
        if action == "tag":
            if len(args) < 3:
                await update.message.reply_text("Usage: /journal tag <decision_id> <new_tag>")
                return
            try:
                did = int(args[1])
            except ValueError:
                await update.message.reply_text(f"Invalid id: {args[1]}")
                return
            new_tag = " ".join(args[2:])
            await _journal_tag_impl(update, did, new_tag)
            return

    # Default: log decision (multi-word reasoning needs text.split for full string)
    from datetime import date, timedelta  # noqa: F401  # imported here for clarity

    text = update.message.text
    parts = text.split(None, 4)
    if len(parts) < 5:
        await update.message.reply_text(
            "Usage:\n"
            "  /journal <TICKER> <type> <conf_1_5> <reasoning>\n"
            "  /journal review [TICKER]\n"
            "  /journal unresolved\n"
            "  /journal tag <decision_id> <new_tag>\n"
            "\n"
            "Types: entry|scale_in|partial_exit|full_exit|override|no_action_flag\n"
            "Abbrev: e|si|pe|fe|o|nf"
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

    await _journal_log_impl(update, ticker, dtype, confidence, reasoning)


async def cmd_journal_review(update, ctx):  # noqa: ARG001
    """Legacy alias for /journal review. Sprint 1.2 Phase H."""
    parts = update.message.text.split()
    ticker_filter = parts[1].upper() if len(parts) > 1 else None
    await _journal_review_impl(update, ticker_filter)


async def cmd_journal_unresolved(update, ctx):  # noqa: ARG001
    """Legacy alias for /journal unresolved. Sprint 1.2 Phase H."""
    await _journal_unresolved_impl(update)


async def cmd_journal_tag(update, ctx):  # noqa: ARG001
    """Legacy alias for /journal tag. Sprint 1.2 Phase H."""
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
    await _journal_tag_impl(update, did, new_tag)


async def cmd_position_history(update, ctx):  # noqa: ARG001
    """Phase B5 - Show position history. Usage: /position_history [TICKER]
    Alias also available as /portfolio history [TICKER]."""
    parts = update.message.text.split()
    ticker = parts[1].upper() if len(parts) > 1 else None
    await _position_history_impl(update, ticker)


async def cmd_bias_review(update, ctx):  # noqa: ARG001
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


async def _journal_log_impl(update, ticker: str, dtype: str, confidence: int, reasoning: str) -> None:
    """Internal: log decision with full context (price, regime, credit, thesis, materiality, bias).

    Used by cmd_journal (default action) and any future automation that needs
    structured journal logging. Body extracted verbatim from prior cmd_journal,
    no dedent (body at 4sp direct-in-function).
    """
    from datetime import date, timedelta

    price = None
    try:
        from shared.prices import get_current_price

        price = get_current_price(ticker)
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


async def _journal_review_impl(update, ticker_filter) -> None:
    """Internal: journal stats + recent decisions (optionally filtered by ticker).

    Used by cmd_journal_review (legacy alias) and cmd_journal (Phase H dispatcher).
    Body extracted verbatim, no dedent.
    """
    from intelligence import journal
    from shared import storage as storage_mod

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


async def _journal_unresolved_impl(update) -> None:
    """Internal: list decisions awaiting J+30 or J+90 resolution.

    Used by cmd_journal_unresolved (legacy alias) and cmd_journal (Phase H dispatcher).
    Body extracted verbatim, no dedent.
    """
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


async def _journal_tag_impl(update, decision_id: int, new_tag: str) -> None:
    """Internal: override mistake_tag for an existing decision.

    Used by cmd_journal_tag (legacy alias) and cmd_journal (Phase H dispatcher).
    Body extracted verbatim, no dedent. Note: parameters are `decision_id` + `new_tag`
    so the helper body must reference them — but the original body used `did` and `new_tag`,
    so we provide alias bindings inline.
    """
    did = decision_id
    from shared import storage as storage_mod

    d = storage_mod.get_decision(did)
    if not d:
        await update.message.reply_text(f"Decision #{did} not found")
        return

    storage_mod.override_mistake_tag(did, new_tag)
    await update.message.reply_text(
        f"OK decision #{did}: mistake_tag_manual='{new_tag}'\n  (was auto: {d.get('mistake_tag_auto') or 'pending'})"
    )


async def _position_history_impl(update, ticker) -> None:
    """Internal: list position history (open + closed).

    Used by cmd_position_history (legacy alias) and cmd_portfolio
    (Sprint 1.2 Phase B /portfolio history dispatch). Body extracted
    verbatim, no dedent (body at 4sp direct-in-function). storage_mod
    import injected (was BEFORE parse marker in original).
    """
    from shared import storage as storage_mod

    positions = storage_mod.get_positions_history(ticker=ticker, limit=20)
    if not positions:
        await update.message.reply_text("No position history" + (f" for {ticker}" if ticker else "") + ".")
        return
    # ADR 005: avg_cost EUR canonical -> convert via cost_in for $ display.
    from shared.positions import cost_in

    lines = ["Position history" + (f" — {ticker}" if ticker else "")]
    for p in positions:
        state = "CLOSED" if (p.get("status") == "closed") else f"OPEN ({p['qty']:g})"
        rpnl = p.get("realized_pnl") or 0
        avg_usd = cost_in(p["avg_cost"], "USD") or 0
        lines.append(f"  #{p['id']} {p['ticker']} {state} entry={p['qty']:g}@${avg_usd:.2f} rpnl={rpnl:+,.2f}")
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)
