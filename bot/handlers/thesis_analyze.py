"""Thesis analysis + debate + risk-check handlers.

Extracted from bot/main.py Sprint 1.1 chunk 6 (2026-05-16, Day 5).
Mechanical move only, zero logic change.

Module exports (5 handlers):
- cmd_thesis_premortem  : /thesis_premortem ID — generate pre-mortem for thesis
- cmd_analyze           : /analyze TICKER — deep fiche on ticker
- cmd_analyze_debate    : /analyze_debate TICKER — multi-round debate
- cmd_risk_check        : /risk_check TICKER SIDE USD — Opus risk gate

Other thesis handlers (cmd_thesis_add/list/revisit/note/set) intentionally
NOT in this chunk — they use Update/ContextTypes type hints (different
signature pattern), reserved for future chunk.
"""

from __future__ import annotations

import logging

from intelligence import analyze as analyze_mod

__all__ = [
    "cmd_analyze",
    "cmd_analyze_debate",
    "cmd_risk_check",
    "cmd_thesis_premortem",
]


log = logging.getLogger("bot")


async def cmd_thesis_premortem(update, ctx):
    """Legacy alias: /thesis_premortem -> /thesis premortem."""
    await _thesis_premortem_impl(update, ctx.args or [])


async def _thesis_premortem_impl(update, args: list[str]) -> None:
    """Internal: display pre-mortem. Used by /thesis_premortem and /thesis premortem."""
    if not args:
        await update.message.reply_text("Usage: /thesis premortem <thesis_id>")
        return
    try:
        tid = int(args[0])
    except ValueError:
        await update.message.reply_text(f"Invalid id: {args[0]}")
        return
    from shared import storage as storage_mod

    pm_json = storage_mod.get_thesis_pre_mortem(tid)
    if not pm_json:
        await update.message.reply_text(
            f"No pre-mortem for thesis #{tid}.\nOnly theses created after Phase B7 (12/05/2026) have pre-mortems."
        )
        return
    from intelligence import pre_mortem as pm_mod

    display = pm_mod.format_pre_mortem_display(pm_json)
    if not display:
        await update.message.reply_text("Pre-mortem stored but parse failed.")
        return
    if len(display) > 3900:
        display = display[:3900] + "\n[truncated]"
    await update.message.reply_text(display)


async def cmd_analyze_debate(update, ctx):  # noqa: ARG001
    """Phase C11 — Multi-round Bull/Bear debate. Usage: /analyze_debate TICKER"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /analyze_debate <TICKER>")
        return
    ticker = parts[1].upper()
    await update.message.reply_text(f"Running 3-round adversarial debate on {ticker} (~30-60s, ~$0.10)...")
    try:
        from intelligence import analyze as analyze_mod_local, debate as debate_mod
        from shared import storage as storage_mod

        data = analyze_mod_local.fetch_stock_data(ticker)
        if not data:
            await update.message.reply_text(f"No data available for {ticker}.")
            return
        context_text = analyze_mod_local.build_prompt(data)[:3500]
        result = debate_mod.run_multi_round_debate(ticker, context_text)
        if not result.get("rounds"):
            await update.message.reply_text("Debate produced no rounds. Aborting.")
            return
        debate_id = storage_mod.save_debate_transcript(
            ticker=ticker,
            transcript_dict=result,
            convergence_score=result.get("convergence_score"),
            verdict=result.get("verdict"),
        )
        chunks = debate_mod.format_debate_for_telegram(result)
        for c in chunks:
            if len(c) > 3900:
                c = c[:3900] + "\n[truncated]"
            await update.message.reply_text(c)
        await update.message.reply_text(f"Debate #{debate_id} saved.")
    except Exception as e:
        log.warning(f"analyze_debate error: {e}")
        await update.message.reply_text(f"Error: {e}")


async def cmd_risk_check(update, ctx):  # noqa: ARG001
    """Phase C12 — Pre-commit discipline check on proposed trade.
    Usage: /risk_check TICKER SIDE USD_AMOUNT [reasoning]
    Example: /risk_check NVDA long 5000 Adding before earnings May 21"""
    text = update.message.text or ""
    parts = text.split(maxsplit=4)
    if len(parts) < 4:
        await update.message.reply_text(
            "Usage: /risk_check TICKER SIDE USD_AMOUNT [reasoning]\n"
            "Example: /risk_check NVDA long 5000 Adding before earnings"
        )
        return
    ticker = parts[1].upper()
    side = parts[2].lower()
    try:
        proposed_usd = float(parts[3])
    except ValueError:
        await update.message.reply_text(f"Invalid USD amount: {parts[3]}")
        return
    reasoning = parts[4] if len(parts) > 4 else ""
    await update.message.reply_text(f"Running risk check on {ticker} {side.upper()} ${proposed_usd:,.0f} (~15-30s)...")
    try:
        from intelligence import risk_manager
        from shared import storage as storage_mod

        result = risk_manager.run_risk_check(ticker, side, proposed_usd, reasoning)
        positions = storage_mod.get_active_positions() or []
        thesis = storage_mod.get_thesis_by_ticker(ticker, status="active")
        snapshot = {"positions": positions, "thesis": thesis}
        rcid = storage_mod.save_risk_check(
            ticker=ticker,
            side=side,
            proposed_usd=proposed_usd,
            verdict=result.get("verdict", "unknown"),
            risk_check_dict=result,
            portfolio_snapshot=snapshot,
        )
        msg = risk_manager.format_risk_check_display(result, ticker, side, proposed_usd)
        msg += f"\n\nRisk check #{rcid} saved."
        if len(msg) > 3900:
            msg = msg[:3900] + "\n[truncated]"
        await update.message.reply_text(msg)
    except Exception as e:
        log.warning(f"risk_check error: {e}")
        await update.message.reply_text(f"Error: {e}")


async def cmd_analyze(update, ctx):  # noqa: ARG001
    """Full company analysis fiche: /analyze TICKER"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /analyze <TICKER>  (e.g. /analyze NVDA, /analyze BTC-USD)")
        return
    ticker = parts[1].upper()
    await update.message.reply_text(f"⏳ Generating analysis for {ticker} (~15-30s)...")
    try:
        result = analyze_mod.analyze_stock(ticker)
        chunks = analyze_mod.format_for_telegram(result)
        for chunk in chunks:
            await update.message.reply_text(chunk)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
