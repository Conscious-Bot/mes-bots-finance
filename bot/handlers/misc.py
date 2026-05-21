"""Misc handlers — asymmetry, brief, position direct ops, thesis_set.

Extracted from bot/main.py Sprint 1.1 chunk 10 (2026-05-16, Day 5).
Final PLAIN (update, ctx) handler extraction. Mechanical move only.

Module exports (5 handlers):
- cmd_asymmetry    : /asymmetry TICKER — counter sell-too-early bias math
- cmd_brief        : /brief — morning ritual 6 sections
- cmd_position    : /position TICKER — show single position detail
- cmd_thesis_set   : /thesis_set ID FIELD VALUE — direct thesis field edit

DEPS migrated (top-level):
- import logging + log instance (used by 1 handler)
- from shared import positions as positions_mod (used by cmd_position)
"""

from __future__ import annotations

import logging

from shared import positions as positions_mod

__all__ = [
    "cmd_asymmetry",
    "cmd_brief",
    "cmd_position",
    "cmd_thesis_set",
]

log = logging.getLogger("bot")


async def cmd_asymmetry(update, ctx):
    """Legacy alias: /asymmetry -> /thesis asymmetry."""
    await _asymmetry_impl(update, ctx.args or [])


async def _asymmetry_impl(update, args: list[str]) -> None:
    """Internal: asymmetry computation. Used by /asymmetry and /thesis asymmetry."""
    from intelligence import asymmetry as asym_mod
    from shared import storage as storage_mod

    if args:
        ticker = args[0].upper()
        thesis = storage_mod.get_thesis_by_ticker(ticker, status="active")
        if not thesis:
            await update.message.reply_text(f"No active thesis for {ticker}.")
            return
        await update.message.reply_text(f"Computing asymmetry on {ticker}...")
        r = asym_mod.compute_thesis_asymmetry(thesis)
        if r is None:
            await update.message.reply_text(f"Cannot compute asymmetry for {ticker} (no thesis data).")
            return
        msg = asym_mod.format_asymmetry_single(r)
    else:
        await update.message.reply_text("Computing portfolio-wide asymmetry...")
        results = asym_mod.compute_portfolio_asymmetry()
        msg = asym_mod.format_portfolio_asymmetry(results)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_brief(update, ctx):  # noqa: ARG001
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


async def cmd_position(update, ctx):  # noqa: ARG001
    """Detail: /position TICKER (alias also available as /portfolio TICKER)"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /position <TICKER>")
        return
    try:
        ticker = parts[1].upper()
        await _position_view_impl(update, ticker)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
async def cmd_thesis_set(update, ctx):
    """Legacy alias: /thesis_set -> /thesis set."""
    await _thesis_set_impl(update, ctx.args or [])


async def _thesis_set_impl(update, args: list[str]) -> None:
    """Internal: edit thesis field. Used by /thesis_set and /thesis set."""
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: /thesis set <TICKER> <field> <value>\n\n"
            "Editable numeric: target_price, target_partial, target_full, stop_price, entry_price, conviction\n"
            "Editable text:    notes, horizon, key_drivers, invalidation_triggers, triggers_profit_take, status\n\n"
            "Examples:\n"
            "  /thesis set NVDA target_partial 260\n"
            "  /thesis set NVDA stop_price 175\n"
            "  /thesis set NVDA notes Post-earnings re-eval"
        )
        return
    ticker, field = args[0].upper(), args[1].lower()
    value = " ".join(args[2:])
    parts = ["", ticker, field, value]  # backward compat for body refs to parts[3]
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

async def _position_view_impl(update, ticker: str) -> None:
    """Internal: show position detail (qty, avg, P&L, history).

    Used by cmd_position (legacy /position alias) and cmd_portfolio
    (Sprint 1.2 Phase B /portfolio TICKER dispatch). Body extracted
    verbatim, dedented by 4 (was inside try block in original cmd_position).
    """
    p = positions_mod.get_position(ticker)
    if not p:
        await update.message.reply_text(f"No open position for {ticker}")
        return
    hist = positions_mod.get_history(ticker)
    await update.message.reply_text(positions_mod.format_position_detail(p, hist))

