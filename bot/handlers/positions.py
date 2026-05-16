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
- _portfolio_journal_ctx : helper (re-exported via bot.main for smoke test compat)
"""
from __future__ import annotations

import contextlib
import logging

from shared import positions as positions_mod

__all__ = [
    "_portfolio_journal_ctx",
    "cmd_portfolio",
    "cmd_position_buy",
    "cmd_position_sell",
]


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


async def cmd_portfolio(update, ctx):  # noqa: ARG001
    """Phase B5 — Show active positions + concentration + unrealized PnL."""
    from shared import storage as storage_mod

    positions = storage_mod.get_active_positions()
    if not positions:
        await update.message.reply_text("No active positions.\n\nUse /position_buy <TICKER> <qty> <price> to open one.")
        return

    from shared.prices import get_current_price_eur

    total_cost = sum(p["qty"] * p["avg_cost"] for p in positions)
    enriched = []
    total_mv = 0.0
    for p in positions:
        ticker = p["ticker"]
        cur_price = get_current_price_eur(ticker)
        mv = (cur_price * p["qty"]) if cur_price else (p["avg_cost"] * p["qty"])
        unreal = (mv - p["qty"] * p["avg_cost"]) if cur_price else 0.0
        enriched.append({**p, "current_price": cur_price, "market_value": mv, "unrealized_pnl": unreal})
        total_mv += mv

    lines = [f"Portfolio — {len(positions)} active positions (EUR)"]
    lines.append(f"  Cost basis: €{total_cost:,.2f}")
    lines.append(f"  Market value: €{total_mv:,.2f}")
    if total_cost > 0:
        lines.append(f"  Unrealized PnL: €{total_mv - total_cost:+,.2f} ({(total_mv / total_cost - 1) * 100:+.1f}%)")
    lines.append("")
    lines.append("Positions (% of book):")
    for p in sorted(enriched, key=lambda x: x["market_value"], reverse=True):
        pct = (p["market_value"] / total_mv * 100) if total_mv else 0
        cur = f"€{p['current_price']:.2f}" if p.get("current_price") else "?"
        avg = p["avg_cost"]
        mv_str = f"€{p['market_value']:>6,.0f}"
        lines.append(
            f"  {p['ticker']:9s} {p['qty']:>7.3f} @€{avg:>7.2f} now {cur:>9s} = {mv_str:>8s}  [{pct:4.1f}%]"
        )
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_position_buy(update, ctx):  # noqa: ARG001
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
            except Exception as bias_err:
                logging.getLogger("bot.position_buy").warning(
                    f"bias_tagger failed for decision_id={decision_id} ticker={ticker}: "
                    f"{type(bias_err).__name__}: {bias_err}"
                )

        # 5. Compose response
        msg = [f"✓ Bought {qty:.3f} {ticker} @ ${price:.2f} [{dtype}]"]
        msg.append(f"  New qty: {p['qty']:.3f}, avg cost: ${p['avg_cost']:.2f}")
        if decision_id:
            tags_str = f", biases: {','.join(bias_tags)}" if bias_tags else ""
            msg.append(f"  -> auto-logged decision #{decision_id} thesis={thesis_id or '-'}{tags_str}")
        await update.message.reply_text("\n".join(msg))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_position_sell(update, ctx):  # noqa: ARG001
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
            except Exception as bias_err:
                logging.getLogger("bot.position_buy").warning(
                    f"bias_tagger failed for decision_id={decision_id} ticker={ticker}: "
                    f"{type(bias_err).__name__}: {bias_err}"
                )

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
