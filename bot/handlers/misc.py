"""Misc handlers — asymmetry, brief, position direct ops, thesis_set.

Extracted from bot/main.py Sprint 1.1 chunk 10 (2026-05-16, Day 5).
Final PLAIN (update, ctx) handler extraction. Mechanical move only.

Module exports (5 handlers):
- cmd_asymmetry    : /asymmetry TICKER — counter sell-too-early bias math
- cmd_brief        : /brief — morning ritual 6 sections
- cmd_position_set : /position_set TICKER QTY AVG_COST — direct override
- cmd_position    : /position TICKER — show single position detail
- cmd_thesis_set   : /thesis_set ID FIELD VALUE — direct thesis field edit

DEPS migrated (top-level):
- import logging + log instance (used by 1 handler)
- from shared import positions as positions_mod (used by cmd_position, cmd_position_set)
"""
from __future__ import annotations

import logging

from shared import positions as positions_mod

__all__ = [
    "cmd_asymmetry",
    "cmd_brief",
    "cmd_position",
    "cmd_position_set",
    "cmd_thesis_set",
]

log = logging.getLogger("bot")


async def cmd_asymmetry(update, ctx):  # noqa: ARG001
    """Phase C13 — Show asymmetry ratio for thesis. Usage: /asymmetry [TICKER]"""
    parts = update.message.text.split()
    from intelligence import asymmetry as asym_mod
    from shared import storage as storage_mod

    if len(parts) >= 2:
        ticker = parts[1].upper()
        thesis = storage_mod.get_thesis_by_ticker(ticker, status="active")
        if not thesis:
            await update.message.reply_text(f"No active thesis for {ticker}.")
            return
        await update.message.reply_text(f"Computing asymmetry on {ticker}...")
        r = asym_mod.compute_thesis_asymmetry(thesis)
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


async def cmd_position_set(update, ctx):  # noqa: ARG001
    """Bootstrap position: /position_set TICKER QTY AVG_COST [notes]"""
    parts = update.message.text.split(maxsplit=4)
    if len(parts) < 4:
        await update.message.reply_text("Usage: /position_set <TICKER> <QTY> <AVG_COST> [notes]")
        return
    try:
        ticker, qty, avg = parts[1].upper(), float(parts[2]), float(parts[3])
        notes = parts[4] if len(parts) > 4 else None
        positions_mod.set_position(ticker, qty, avg, notes)
        await update.message.reply_text(f"✓ Position set: {ticker} qty={qty:.3f} @ ${avg:.2f}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_position(update, ctx):  # noqa: ARG001
    """Detail: /position TICKER"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /position <TICKER>")
        return
    try:
        ticker = parts[1].upper()
        p = positions_mod.get_position(ticker)
        if not p:
            await update.message.reply_text(f"No open position for {ticker}")
            return
        hist = positions_mod.get_history(ticker)
        await update.message.reply_text(positions_mod.format_position_detail(p, hist))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_thesis_set(update, ctx):  # noqa: ARG001
    """Edit a field on active thesis: /thesis_set TICKER field value"""
    parts = update.message.text.split(maxsplit=3)
    if len(parts) < 4:
        await update.message.reply_text(
            "Usage: /thesis_set <TICKER> <field> <value>\n\n"
            "Editable numeric: target_price, target_partial, target_full, stop_price, entry_price, conviction\n"
            "Editable text:    notes, horizon, key_drivers, invalidation_triggers, triggers_profit_take, status\n\n"
            "Examples:\n"
            "  /thesis_set NVDA target_partial 260\n"
            "  /thesis_set NVDA stop_price 175\n"
            "  /thesis_set NVDA notes 'Post-earnings re-eval'"
        )
        return
    ticker, field, value = parts[1].upper(), parts[2].lower(), parts[3]
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
