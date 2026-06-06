"""Position management handlers — buy, sell, portfolio view.

Extracted from bot/main.py Sprint 1.1 chunk 4 (2026-05-16, Day 5).
Mechanical move only, zero logic change.

Phase B5 journal chain preserved intact:
1. detect entry vs scale_in (via positions_mod.get_position)
2. update via positions_mod.add_buy/add_sell (writes positions + position_events)
3. _portfolio_journal_ctx auto-context (price, regime, credit, thesis_id, materiality_top)
4. storage.log_decision (KPI #5 100% decisions journalisees)
5. bias_tagger.auto_tag_biases (cognitive bias detection)

Module exports:
- cmd_portfolio       : /portfolio active positions + concentration + unrealized PnL
- cmd_position_buy    : /position_buy <TICKER> <QTY> <PRICE> [reasoning]
- cmd_position_sell   : /position_sell <TICKER> <QTY> <PRICE> [reasoning]
- cmd_journal_decision : /journal_decision [<id>] <free text> (enrichir reasoning a posteriori)
- _portfolio_journal_ctx : helper (re-exported via bot.main for smoke test compat)
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from shared import positions as positions_mod, storage
from shared.display import format_finance, format_pct

__all__ = [
    "_portfolio_journal_ctx",
    "cmd_portfolio",
    "cmd_position_buy",
    "cmd_position_sell",
]


def _portfolio_journal_ctx(
    ticker: str,
) -> tuple[Any | None, Any | None, str | None, Any | None, Any | None, list[Any] | None]:
    """Phase B5 — Auto-context for journal log_decision: price, regime, credit, thesis_id, materiality_top."""
    ticker = ticker.upper()
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
    materiality_top = None
    try:
        from shared import storage as storage_mod

        tops = storage_mod.get_top_material_signals(n=10, since_hours=72)
        ticker_tops = [t["id"] for t in tops if t.get("primary_ticker") == ticker][:3]
        materiality_top = ticker_tops if ticker_tops else None
    except Exception:
        pass
    return price, regime_str, credit_str, thesis_id, direction, materiality_top


async def cmd_portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Portfolio v2: alerts top, conviction, PnL%, drill-down footer."""
    assert update.message is not None  # type narrowing — command handlers always receive message

    # Sprint 1.2 Phase B dispatcher: /portfolio family sub-actions
    # Routes: sectors|narratives|drift|history|TICKER -> dedicated handlers/helpers
    # Default (no args): existing rich body below (cluster + alerts + positions)
    args = ctx.args or []
    if args:
        action = args[0].lower()
        if action == "sectors":
            from bot.handlers.portfolio_views import cmd_portfolio_sectors

            await cmd_portfolio_sectors(update, ctx)
            return
        if action == "narratives":
            from bot.handlers.portfolio_views import cmd_portfolio_narratives

            await cmd_portfolio_narratives(update, ctx)
            return
        if action == "drift":
            from bot.handlers.portfolio_views import cmd_portfolio_drift

            await cmd_portfolio_drift(update, ctx)
            return
        if action == "history":
            from bot.handlers.journal_bias import _position_history_impl

            ticker = args[1].upper() if len(args) > 1 else None
            await _position_history_impl(update, ticker)
            return
        # Else: treat args[0] as TICKER (single-ticker view, alias for /position)
        from bot.handlers.misc import _position_view_impl

        ticker = args[0].upper()
        await _position_view_impl(update, ticker)
        return

    import sqlite3
    from datetime import datetime as _dt

    from shared import config as cfg_mod, storage as storage_mod
    from shared.display import Currency
    from shared.prices import get_current_price_in_usd
    from shared.ticker_names import get_short_name

    positions = storage_mod.get_active_positions()
    if not positions:
        await update.message.reply_text("No active positions.\n\nUse /position_buy <TICKER> <qty> <price> to open one.")
        return

    try:
        cfg = cfg_mod.load()
        max_pct = float(cfg.get("style", {}).get("position_max_pct", 0.05))
    except Exception:
        max_pct = 0.05
    max_pct_threshold = max_pct * 100

    # Fetch conviction from active theses
    conn = sqlite3.connect(storage_mod._DB_PATH)
    conn.row_factory = sqlite3.Row
    theses_map = {}
    try:
        rows = conn.execute("SELECT ticker, conviction FROM theses WHERE status='active'").fetchall()
        for r in rows:
            theses_map[r["ticker"]] = r["conviction"]
    except Exception:
        pass
    finally:
        conn.close()

    # Enrich positions
    enriched = []
    total_cost = 0.0
    total_mv = 0.0
    from shared.positions import cost_in

    for p in positions:
        ticker = p["ticker"]
        # Day 13 ADR 005: avg_cost EUR canonical (Day 11 Batch 4A NATIVE comment
        # was aspirational, storage never migrated). Use cost_in helper centrally.
        cur_price = get_current_price_in_usd(ticker)
        avg_cost_usd = cost_in(p["avg_cost"], "USD") or 0.0
        cost_value = p["qty"] * avg_cost_usd
        mv = (cur_price * p["qty"]) if cur_price else cost_value
        unreal_pct = ((cur_price / avg_cost_usd - 1) * 100) if cur_price and avg_cost_usd else None
        conviction = theses_map.get(ticker)
        short_name = get_short_name(ticker) or ticker
        name_display = short_name[:22]
        enriched.append(
            {
                **p,
                "avg_cost": avg_cost_usd,
                "current_price": cur_price,
                "market_value": mv,
                "pnl_pct": unreal_pct,
                "conviction": conviction,
                "name_display": name_display,
            }
        )
        total_cost += cost_value
        total_mv += mv

    enriched_sorted = sorted(enriched, key=lambda x: x["market_value"], reverse=True)

    # Cluster concentration analysis (ADR 008: 35% cap per narrative_tag)
    import re as _re

    _CLUSTER_RE = _re.compile(r"sector_thesis_id:\s*([A-Z0-9_]+)")
    thesis_notes_by_ticker: dict[str, str] = {}
    try:
        _conn = sqlite3.connect(storage_mod._DB_PATH)
        _conn.row_factory = sqlite3.Row
        for _r in _conn.execute("SELECT ticker, notes FROM theses WHERE status='active'").fetchall():
            thesis_notes_by_ticker[_r["ticker"]] = _r["notes"] or ""
        _conn.close()
    except Exception:
        pass
    clusters: dict[str, float] = {}
    for _pos in enriched:
        _notes = thesis_notes_by_ticker.get(_pos["ticker"], "")
        _m = _CLUSTER_RE.search(_notes)
        _cn = _m.group(1) if _m else "UNCLUSTERED"
        clusters[_cn] = clusters.get(_cn, 0.0) + _pos["market_value"]
    CLUSTER_CAP_PCT = 35.0  # ADR 008
    cluster_breach: list[tuple[str, float, float]] = []
    cluster_lines: list[str] = []
    if clusters and total_mv:
        cluster_lines.append(f"CLUSTER CONCENTRATION (cap {CLUSTER_CAP_PCT:.0f}% per ADR 008)")
        for _cn, _val in sorted(clusters.items(), key=lambda x: -x[1]):
            _pct = _val / total_mv * 100
            _over = _pct - CLUSTER_CAP_PCT
            if _over > 0:
                _status = "🔴"
                _delta_str = f"+{_over:.1f}pp over cap"
                cluster_breach.append((_cn, _pct, _over))
            else:
                _status = "✅"
                _delta_str = f"{-_over:.1f}pp room"
            _val_str = format_finance(_val, decimals=0, currency=Currency.USD)
            cluster_lines.append(f"  {_status} {_cn:30} {_val_str:>10}  {_pct:>5.1f}%  ({_delta_str})")

    # Alerts
    over_sized = []
    for pos in enriched_sorted:
        pct = (pos["market_value"] / total_mv * 100) if total_mv else 0
        if pct > max_pct_threshold:
            over_sized.append((pos["ticker"], pct))

    pnl_sorted = [p for p in enriched if p["pnl_pct"] is not None]
    worst3 = sorted(pnl_sorted, key=lambda x: x["pnl_pct"])[:3]
    best3 = sorted(pnl_sorted, key=lambda x: -x["pnl_pct"])[:3]

    now_str = _dt.now().strftime("%d/%m %H:%M")
    lines = []
    lines.append(f"PORTFOLIO {now_str} (USD)")
    pnl_total = total_mv - total_cost
    pnl_total_pct = (pnl_total / total_cost * 100) if total_cost else 0
    lines.append(
        f"Book: {format_finance(total_mv, decimals=0, currency=Currency.USD)}  Cost: {format_finance(total_cost, decimals=0, currency=Currency.USD)}  "
        f"PnL: {format_finance(pnl_total, decimals=0, signed=True, currency=Currency.USD)} ({format_pct(pnl_total_pct, decimals=1, signed=True)})"
    )
    lines.append(f"{len(positions)} positions  |  Max sizing policy: {max_pct_threshold:.0f}%")
    lines.append("")

    if cluster_lines:
        lines.extend(cluster_lines)
        lines.append("")

    alerts_lines = []
    if over_sized:
        items = ", ".join(tk + " (" + format(pct, ".1f") + "%)" for tk, pct in over_sized)
        alerts_lines.append(f"  Over max {max_pct_threshold:.0f}%/book: {items}")
    if worst3:
        worst_strs = []
        for p in worst3:
            pnl_s = format_pct(p["pnl_pct"], decimals=1, signed=True)
            conv_s = f"c{p['conviction']}" if p["conviction"] else "c-"
            worst_strs.append(f"{p['ticker']} {conv_s} {pnl_s}")
        alerts_lines.append(f"  Worst 3: {', '.join(worst_strs)}")
    if best3:
        best_strs = []
        for p in best3:
            pnl_s = format_pct(p["pnl_pct"], decimals=1, signed=True)
            conv_s = f"c{p['conviction']}" if p["conviction"] else "c-"
            best_strs.append(f"{p['ticker']} {conv_s} {pnl_s}")
        alerts_lines.append(f"  Best 3: {', '.join(best_strs)}")
    if alerts_lines:
        lines.append("ALERTS")
        lines.extend(alerts_lines)
    else:
        lines.append("ALERTS: nothing flagged.")
    lines.append("")

    lines.append(f"POSITIONS · {len(enriched_sorted)} · by size")
    # Table compacte mobile : ticker · conv · value · %bk · pnl. Prix par action
    # (Cost/Now) et Name droppes (dispo dans /asymmetry TICKER + dashboard).
    # <pre> = alignement monospace + pas de wrap mobile ; send HTML plus bas.
    # Chirurgical : format_position_line (autres callers) intact, handler non decompose.
    _tbl = [f"{'ticker':<9}{'cnv':>4}{'value':>8}{'%bk':>6}{'pnl':>8}"]
    for pos in enriched_sorted:
        mv = pos["market_value"]
        pct_book = (mv / total_mv * 100) if total_mv else 0
        _cv = f"c{pos['conviction']}" if pos["conviction"] else "c-"
        _val = format_finance(mv, decimals=0, currency=Currency.USD)
        _bk = format_pct(pct_book, decimals=1)
        _pnl = format_pct(pos["pnl_pct"], decimals=1, signed=True) if pos["pnl_pct"] is not None else "n/a"
        _tbl.append(f"{pos['ticker']:<9}{_cv:>4}{_val:>8}{_bk:>6}{_pnl:>8}")
    lines.append("<pre>" + "\n".join(_tbl) + "</pre>")

    lines.append("")
    lines.append("Drill-down:")
    lines.append("  /find TICKER       → cross-domain snapshot")
    lines.append("  /thesis health     → conviction coverage check")
    lines.append("  /journal audit     → silent tickers")

    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
        if msg.count("<pre>") > msg.count("</pre>"):
            msg += "</pre>"
    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_position_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    """Buy + Phase B5 journal logging + bias tagging (auto).
    Usage: /position_buy <TICKER> <QTY> <PRICE> [reasoning]
    """
    assert update.message is not None and update.message.text is not None  # type narrowing
    parts = update.message.text.split(maxsplit=4)
    if len(parts) < 4:
        await update.message.reply_text("Usage: /position_buy <TICKER> <QTY> <PRICE> [reasoning]")
        return
    try:
        ticker, qty, price = parts[1].upper(), float(parts[2]), float(parts[3])
        reasoning = parts[4] if len(parts) > 4 else "Buy via /position_buy"
        await _buy_impl(update, ticker, qty, price, reasoning)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_position_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    """Sell + Phase B5 journal logging + bias tagging (auto).
    Usage: /position_sell <TICKER> <QTY> <PRICE> [reasoning]
    """
    assert update.message is not None and update.message.text is not None  # type narrowing
    parts = update.message.text.split(maxsplit=4)
    if len(parts) < 4:
        await update.message.reply_text("Usage: /position_sell <TICKER> <QTY> <PRICE> [reasoning]")
        return
    try:
        ticker, qty, price = parts[1].upper(), float(parts[2]), float(parts[3])
        reasoning = parts[4] if len(parts) > 4 else "Sell via /position_sell"
        await _sell_impl(update, ticker, qty, price, reasoning)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def _buy_impl(update, ticker: str, qty: float, price: float, reasoning: str) -> None:
    """Internal: execute buy with B2 risk + B5 journal + bias chain.

    Used by cmd_position_buy (legacy /position_buy alias) and cmd_trade
    (Sprint 1.2 Phase C dispatcher). Body extracted verbatim from prior
    cmd_position_buy implementation to preserve Day 13 Ship 5 KPI #5 chain.
    """
    assert update.message is not None

    # 0. B2: Risk validation gate (feature-flagged, default OFF)
    from shared import config as _cfg_b2_mod, storage as _storage_b2_mod

    _cfg_b2 = _cfg_b2_mod.load()
    if _cfg_b2.get("risk", {}).get("validate_enabled", False):
        from risk import risk_engine

        _state_b2 = _storage_b2_mod.load_state()
        _capital_b2 = _state_b2.get("capital_paper", 10000) or 10000
        _size_pct_b2 = (qty * price) / _capital_b2
        _thesis_b2 = _storage_b2_mod.get_thesis_by_ticker(ticker, status="active")
        _conviction_b2 = _thesis_b2.get("conviction", 3) if _thesis_b2 else 3
        _decision_b2 = {
            "ticker": ticker,
            "action": "buy",
            "size_pct": _size_pct_b2,
            "conviction": _conviction_b2,
            "execute_real": False,
        }
        _result_b2 = risk_engine.validate(_decision_b2)
        if not _result_b2.ok and _result_b2.severity == "block":
            # W14 mode advisory deepening (31/05 close) : softening du message
            # prescriptif. La discipline INFORME, ne refuse pas en silence.
            # Conservative partiel : on garde le return pour le moment (pas de
            # bias_events.write encore wired). Quand Pile 2.1 v2 sera live :
            # supprimer le return, INSERT bias_events(action='acted_on_bias' OU
            # 'resisted' selon outcome), laisser l'achat proceder.
            # TODO Pile 2.1 v2 : remove early return, log to bias_events.
            _msg_b2 = "Discipline risk : refus signale.\n" + "\n".join(
                f"  &middot; {r}" for r in _result_b2.reasons
            )
            _msg_b2 += "\n  Outrepasser : toggle risk.validate_enabled dans config.yaml."
            with contextlib.suppress(Exception):
                _storage_b2_mod.log_decision(
                    ticker=ticker,
                    decision_type="buy_blocked_by_risk",
                    confidence=_conviction_b2,
                    reasoning=f"discipline_risk_refus: {'; '.join(_result_b2.reasons)}",
                    direction="long",
                    price_at_decision=price,
                )
            await update.message.reply_text(_msg_b2)
            return

    # 1. Detect entry vs scale_in BEFORE update
    existing_before = positions_mod.get_position(ticker)
    dtype = "scale_in" if (existing_before and existing_before.get("qty", 0) > 0) else "entry"

    # 1.6 Adversarial co-pilot (advisory, non-blocking — Phase 1.5)
    # Runs ONLY for scale_in (existing thesis to challenge). 'entry' = thesis still
    # being formed, pre_mortem.py handles that hook separately at thesis creation.
    _copilot_response = None
    _copilot_intervention_id = None
    if dtype == "scale_in":
        try:
            from intelligence import decision_copilot

            _copilot_response, _copilot_intervention_id = decision_copilot.run_pre_trade_copilot(
                ticker=ticker, decision_type=dtype, reasoning=reasoning, price=price,
            )
        except Exception as cp_err:
            logging.getLogger("bot.position_buy").warning(
                f"copilot pre-trade failed for {ticker}: {type(cp_err).__name__}: {cp_err}"
            )

    # 1.5 Compute EUR-equivalent + enrich notes (H2 fix Day 9 audit, KPI #6 traceability)
    from shared.prices import get_currency_for_ticker as _get_cur, get_fx_rate as _get_fx

    _ticker_cur = _get_cur(ticker)
    _fx_to_eur = _get_fx(_ticker_cur, "EUR") or 1.0
    _eur_inv = qty * price * _fx_to_eur
    if "eur_invested=" in reasoning:
        _enriched_notes = reasoning  # idempotent: already tagged
    else:
        _enriched_notes = f"{reasoning} | eur_invested={_eur_inv:.2f}"

    # 2. Update position via positions_mod (writes positions + position_events)
    p = positions_mod.add_buy(ticker, qty, price, _enriched_notes)

    # 3. Phase B5 journal context + auto log_decision
    from shared import storage as storage_mod

    _px_ctx, regime, credit, thesis_id, thesis_dir, mat_top = _portfolio_journal_ctx(ticker)
    decision_id = None
    try:
        decision_id = storage_mod.log_decision(
            ticker=ticker,
            decision_type=dtype,
            confidence=3,
            reasoning=reasoning,
            direction=(thesis_dir or "long"),
            thesis_id=thesis_id,
            price_at_decision=price,
            regime=regime,
            credit_regime=credit,
            materiality_top=mat_top,
        )
    except Exception as e:
        await update.message.reply_text(f"Position updated but journal failed: {e}")

    # 3.5 Boucle-de-soi V0 : capture ancre contrefactuelle apres log_decision.
    # Source-direct fix 05/06 : avant ce patch, positions.py ne creait PAS d'ancre
    # alors que chat_intent.py le faisait -> 5 decisions orphan 03/06 dans le gate.
    # Branche : "would_have_sold" pour scale_in, "hold" sinon (entry).
    if decision_id:
        try:
            from intelligence import self_loop as _sl
            from shared import edgar as _edgar

            _qty_before_buy = (existing_before.get("qty") if existing_before else 0) or 0
            _currency = _edgar.get_currency_for_ticker(ticker) if hasattr(_edgar, "get_currency_for_ticker") else None
            _sl.record_anchor(
                decision_id=decision_id,
                ticker=ticker,
                decision_type=dtype,
                qty_before=_qty_before_buy,
                price_at_decision=price,
                currency=_currency,
                thesis_id=thesis_id,
                reasoning=reasoning,
                counterfactual_branch="would_have_sold" if dtype == "scale_in" else "hold",
            )
        except Exception as _e:
            logging.getLogger("bot.position_buy").warning(
                f"self_loop record_anchor failed {ticker}: {type(_e).__name__}: {_e}"
            )

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
        except Exception as bias_err:
            logging.getLogger("bot.position_buy").warning(
                f"bias_tagger failed for decision_id={decision_id} ticker={ticker}: "
                f"{type(bias_err).__name__}: {bias_err}"
            )

    # 4.5 Back-link copilot intervention to the actual decision row
    if _copilot_intervention_id and decision_id:
        try:
            from shared import storage as _storage_link

            _storage_link.link_copilot_intervention_decision(_copilot_intervention_id, decision_id)
        except Exception as link_err:
            logging.getLogger("bot.position_buy").warning(
                f"copilot intervention link failed: {type(link_err).__name__}: {link_err}"
            )

    # 5. Compose response
    msg = [f"✓ Bought {qty:.3f} {ticker} @ {format_finance(price, decimals=2)} [{dtype}]"]
    msg.append(f"  New qty: {p['qty']:.3f}, avg cost: {format_finance(p['avg_cost'], decimals=2)}")
    if decision_id:
        tags_str = f", biases: {','.join(bias_tags)}" if bias_tags else ""
        msg.append(f"  -> auto-logged decision #{decision_id} thesis={thesis_id or '-'}{tags_str}")
    # Append copilot brief (advisory)
    if _copilot_response:
        from intelligence.decision_copilot import format_brief_for_telegram

        cp_text = format_brief_for_telegram(_copilot_response)
        if cp_text:
            msg.append(cp_text)
    await update.message.reply_text("\n".join(msg))


async def _sell_impl(update, ticker: str, qty: float, price: float, reasoning: str) -> None:
    """Internal: execute sell with B5 journal + bias chain.

    Used by cmd_position_sell (legacy /position_sell alias) and cmd_trade
    (Sprint 1.2 Phase C dispatcher). Body extracted verbatim.
    """
    assert update.message is not None

    # 0. Predict decision_type BEFORE the sell (for copilot context)
    _existing_sell = positions_mod.get_position(ticker)
    _existing_qty = (_existing_sell or {}).get("qty", 0) or 0
    predicted_dtype = "full_exit" if qty >= _existing_qty else "partial_exit"

    # 0.5 Adversarial co-pilot (advisory, non-blocking — Phase 1.5)
    _copilot_response = None
    _copilot_intervention_id = None
    try:
        from intelligence import decision_copilot

        _copilot_response, _copilot_intervention_id = decision_copilot.run_pre_trade_copilot(
            ticker=ticker, decision_type=predicted_dtype, reasoning=reasoning, price=price,
        )
    except Exception as cp_err:
        logging.getLogger("bot.position_sell").warning(
            f"copilot pre-trade failed for {ticker}: {type(cp_err).__name__}: {cp_err}"
        )

    # 1. Update position (writes positions + position_events)
    r = positions_mod.add_sell(ticker, qty, price, reasoning)
    dtype = "full_exit" if r["closed"] else "partial_exit"

    # 2. Phase B5 journal context + auto log_decision
    from shared import storage as storage_mod

    _px_ctx, regime, credit, thesis_id, thesis_dir, mat_top = _portfolio_journal_ctx(ticker)
    decision_id = None
    try:
        decision_id = storage_mod.log_decision(
            ticker=ticker,
            decision_type=dtype,
            confidence=3,
            reasoning=reasoning,
            direction=(thesis_dir or "long"),
            thesis_id=thesis_id,
            price_at_decision=price,
            regime=regime,
            credit_regime=credit,
            materiality_top=mat_top,
        )
    except Exception as e:
        await update.message.reply_text(f"Position updated but journal failed: {e}")

    # 2.4 Boucle-de-soi V0 : capture ancre contrefactuelle apres log_decision.
    # Source-direct fix 05/06 : avant ce patch, positions.py ne creait PAS d'ancre
    # alors que chat_intent.py le faisait. Pour les sells : branche "hold"
    # (l'alternative est de garder), + bias_hypothesis winner-sell si gain > 10%.
    if decision_id:
        try:
            from intelligence import self_loop as _sl
            from shared import edgar as _edgar

            _qty_before_sell = (_existing_sell.get("qty") if _existing_sell else 0) or 0
            _avg_cost = (_existing_sell.get("avg_cost") if _existing_sell else 0) or 0
            _bias_hyp = []
            if _avg_cost > 0 and (price - _avg_cost) / _avg_cost > 0.10:
                _bias_hyp.append("vend_winners_trop_tot")
            _currency = _edgar.get_currency_for_ticker(ticker) if hasattr(_edgar, "get_currency_for_ticker") else None
            _sl.record_anchor(
                decision_id=decision_id,
                ticker=ticker,
                decision_type=dtype,
                qty_before=_qty_before_sell,
                price_at_decision=price,
                currency=_currency,
                thesis_id=thesis_id,
                bias_hypothesis=_bias_hyp,
                reasoning=reasoning,
                counterfactual_branch="hold",
            )
        except Exception as _e:
            logging.getLogger("bot.position_sell").warning(
                f"self_loop record_anchor failed {ticker}: {type(_e).__name__}: {_e}"
            )

    # 2.45 Source-direct fix 05/06 : full_exit + plus de position -> close la these
    # automatiquement. Avant : these restait active malgre position closed,
    # gate #5 deconnait (cf SNOW thesis_53 active sans position post 03/06).
    if dtype == "full_exit" and r.get("closed") and thesis_id:
        try:
            storage_mod.update_thesis_status(
                thesis_id, "concluded", notes=f"full_exit at {price} ({reasoning[:200]})"
            )
        except Exception as _close_err:
            logging.getLogger("bot.position_sell").warning(
                f"thesis close failed thesis={thesis_id} ticker={ticker}: "
                f"{type(_close_err).__name__}: {_close_err}"
            )

    # 2.5 Back-link copilot intervention to actual decision row
    if _copilot_intervention_id and decision_id:
        try:
            storage_mod.link_copilot_intervention_decision(_copilot_intervention_id, decision_id)
        except Exception as link_err:
            logging.getLogger("bot.position_sell").warning(
                f"copilot intervention link failed: {type(link_err).__name__}: {link_err}"
            )

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
        except Exception as bias_err:
            logging.getLogger("bot.position_buy").warning(
                f"bias_tagger failed for decision_id={decision_id} ticker={ticker}: "
                f"{type(bias_err).__name__}: {bias_err}"
            )

    # 4. Compose response
    msg_lines = [f"✓ Sold {r['sold_qty']:.3f} {r['ticker']} @ {format_finance(r['sold_price'], decimals=2)} [{dtype}]"]
    msg_lines.append(f"  Avg cost was: {format_finance(r['avg_cost'], decimals=2)}")
    msg_lines.append(f"  Realized PnL (event): {format_finance(r['realized_pnl_event'], decimals=2, signed=True)}")
    msg_lines.append(f"  Realized PnL (total): {format_finance(r['realized_pnl_total'], decimals=2, signed=True)}")
    msg_lines.append(f"  Remaining: {r['remaining_qty']:.3f}" + ("  [CLOSED]" if r["closed"] else ""))
    if decision_id:
        tags_str = f", biases: {','.join(bias_tags)}" if bias_tags else ""
        msg_lines.append(f"  -> auto-logged decision #{decision_id} thesis={thesis_id or '-'}{tags_str}")
    if _copilot_response:
        from intelligence.decision_copilot import format_brief_for_telegram

        cp_text = format_brief_for_telegram(_copilot_response)
        if cp_text:
            msg_lines.append(cp_text)
    await update.message.reply_text("\n".join(msg_lines))


async def cmd_trade(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Sprint 1.2 Phase C dispatcher — /trade family.

    Usage (06/06 friction décision #1 : 2-step confirm) :
      /trade buy TICKER QTY PRICE [reasoning]   → renvoie context + token TTL 60s
      /trade sell TICKER QTY PRICE [reasoning]  → renvoie context + token TTL 60s
      /trade confirm <token>                    → execute le pending trade
      /trade cancel <token>                     → annule le pending trade

    Pre-trade context check (4 dimensions) :
      1. Régime macro courant + chip warnings ticker
      2. Composition cluster avant → après simulé
      3. Bias détecté (lock_in pour sell winner, fomo pour buy après run +15% 7j)
      4. Signaux 30j ticker (bullish / bearish)

    Discipline mécanisée : on montre, on ne bloque pas. Le token TTL 60s
    force une confirmation explicite, mais user peut confirmer aveugle.

    Backward-compat:
      /position_buy [...] alias preserved 1 release cycle
      /position_sell [...] alias preserved 1 release cycle
    """
    assert update.message is not None
    args = ctx.args or []
    chat_id = update.message.chat_id
    if not args:
        await update.message.reply_text(
            "Usage: /trade <action> <TICKER> <QTY> <PRICE> [reasoning]\n"
            "       /trade confirm <token>   → exécute le pending\n"
            "       /trade cancel <token>    → annule\n"
            "\n"
            "Actions:\n"
            "  buy TICKER QTY PRICE [reasoning]\n"
            "  sell TICKER QTY PRICE [reasoning]\n"
            "\n"
            "Flow 06/06 (friction décision) :\n"
            "  1. /trade buy NVDA 10 450 → context + token\n"
            "  2. /trade confirm <token> → exécute (TTL 60s)\n"
        )
        return
    action = args[0].lower()

    # === 2-step: confirm / cancel pending pre-checked trade ===
    if action in ("confirm", "cancel"):
        if len(args) < 2:
            await update.message.reply_text(f"Usage: /trade {action} <token>")
            return
        from bot.handlers.trade_context import pop_pending
        token = args[1].strip().lower()
        pending = pop_pending(token)
        if pending is None:
            await update.message.reply_text(
                f"Token '{token}' inconnu ou expiré (TTL 60s). Relance /trade {action}."
            )
            return
        if action == "cancel":
            await update.message.reply_text(
                f"Annulé : {pending['action'].upper()} {pending['ticker']} {pending['qty']} @ {pending['price']}."
            )
            return
        # Confirm -> execute
        try:
            if pending["action"] == "buy":
                await _buy_impl(update, pending["ticker"], pending["qty"],
                                pending["price"], pending["reasoning"])
            else:
                await _sell_impl(update, pending["ticker"], pending["qty"],
                                 pending["price"], pending["reasoning"])
        except Exception as e:
            await update.message.reply_text(f"Error executing pending: {e}")
        return

    # === 1-step: pre-check + generate token ===
    if action not in ("buy", "sell"):
        await update.message.reply_text(
            f"Unknown action: '{action}'\nValid: buy, sell, confirm, cancel\nSee /trade for usage."
        )
        return
    if len(args) < 4:
        await update.message.reply_text(f"Usage: /trade {action} <TICKER> <QTY> <PRICE> [reasoning]")
        return
    try:
        ticker, qty, price = args[1].upper(), float(args[2]), float(args[3])
        reasoning = " ".join(args[4:]) if len(args) > 4 else f"{action.capitalize()} via /trade"
        # Friction décision : compute context + stocker pending + renvoyer token
        from bot.handlers.trade_context import (
            compute_trade_context,
            format_context_message,
            store_pending,
        )
        trade_ctx = compute_trade_context(action, ticker, qty, price)
        token = store_pending(action, ticker, qty, price, reasoning, chat_id)
        msg = format_context_message(trade_ctx, token)
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_journal_decision(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    """Enrichir le reasoning d'une decision deja loggee.

    Usage: /journal_decision <free text>           (cible la derniere decision)
       ou: /journal_decision <id> <free text>      (cible une decision specifique pour rattrapage)

    Workaround design Day 17 : cmd_position_buy/sell acceptent [reasoning] en 4eme arg mais
    si l'utilisateur ne le passe pas, le row est cree avec placeholder ("Buy via /position_buy").
    Ce handler enrichit apres-coup, ADDITIF (zero modif de cmd_position_buy/sell),
    observation-safe (zero impact pipeline signal->prediction->resolution).
    """
    assert update.message is not None and update.message.text is not None
    parts = update.message.text.split(maxsplit=2)
    if len(parts) < 2:
        await update.message.reply_text(
            "Usage : /journal_decision <free text>           (derniere decision)\n"
            "   ou : /journal_decision <id> <free text>      (decision specifique)"
        )
        return

    decision_id: int | None = None
    text: str = ""
    # Detect <id> <text> form
    if len(parts) >= 3 and parts[1].isdigit():
        candidate = int(parts[1])
        if storage.get_decision_brief(candidate) is not None:
            decision_id = candidate
            text = parts[2]

    # Default to latest decision
    if decision_id is None:
        latest = storage.get_latest_decision()
        if latest is None:
            await update.message.reply_text("Aucune decision en DB a enrichir.")
            return
        decision_id = latest[0]
        text = update.message.text.split(maxsplit=1)[1]

    text = text.strip()
    if not text:
        await update.message.reply_text("Reasoning vide, rien a faire.")
        return

    target = storage.get_decision_brief(decision_id)
    if target is None:
        await update.message.reply_text(f"Decision #{decision_id} introuvable.")
        return

    ok = storage.update_decision_reasoning(decision_id, text)
    if ok:
        await update.message.reply_text(f"OK reasoning enrichi pour decision #{decision_id} ({target[1]}, {target[2]})")
    else:
        await update.message.reply_text(f"Echec UPDATE decision #{decision_id}.")
