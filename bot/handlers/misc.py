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
    "cmd_chat",
    "cmd_grade",
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


async def cmd_grade(update, ctx):
    """/grade — affiche la Note du portefeuille (6 dimensions) en Telegram.

    /grade            -> grade actuel + breakdown
    /grade sim TICKER buy QTY PRICE   -> simulation avant/apres
    /grade sim TICKER sell QTY        -> simulation vente
    """
    from intelligence import portfolio_grade as _grade
    from shared import storage as _stg

    args = ctx.args or []

    # --- mode simulation ---
    if args and args[0].lower() in ("sim", "simulate"):
        if len(args) < 4:
            await update.message.reply_text(
                "Usage : /grade sim TICKER buy|sell QTY [PRICE]\n"
                "Exemple : /grade sim ASML.AS buy 5 750"
            )
            return
        ticker = args[1].upper()
        action_kind = args[2].lower()
        try:
            qty = float(args[3])
        except ValueError:
            await update.message.reply_text("qty invalide")
            return
        price = float(args[4]) if len(args) > 4 else 0.0
        action_type = {"buy": "buy", "sell": "sell", "exit": "full_exit"}.get(action_kind, "buy")
        try:
            sim = _grade.simulate_grade(
                {"type": action_type, "ticker": ticker, "qty": qty, "price_eur": price}
            )
        except Exception as e:
            await update.message.reply_text(f"Sim echec : {type(e).__name__}: {e}")
            return
        before = sim["before"]
        after = sim["after"]
        delta = sim["delta_score"]
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "·")
        diag = "\n".join(f"  · {d}" for d in (sim["diagnosis"] or ["aucune dim ne bouge >=5pts"]))
        msg = (
            f"📊 SIMULATION — {action_kind} {ticker} qty={qty}\n\n"
            f"Avant : {before['overall_grade']} ({before['overall_score']}/100)\n"
            f"Après : {after['overall_grade']} ({after['overall_score']}/100)\n"
            f"Δ : {arrow} {delta:+d} pts\n\n"
            f"Dimensions qui bougent :\n{diag}"
        )
        await update.message.reply_text(msg)
        return

    # --- mode default : grade actuel ---
    try:
        latest = _stg.get_latest_portfolio_grade()
        if not latest:
            g = _grade.compute_grade()
            grade_letter = g["overall_grade"]
            score = g["overall_score"]
            dims = g["dimensions"]
            snap_date = g["snapshot_date"]
            cap = g["total_capital_eur"]
            n_pos = g["n_positions"]
        else:
            import json as _json

            grade_letter = latest["overall_grade"]
            score = latest["overall_score"]
            dims = _json.loads(latest["dimensions_json"] or "{}")
            snap_date = latest["snapshot_date"]
            cap = latest.get("total_capital_eur") or 0
            n_pos = latest.get("n_positions") or 0
        trend = _grade.compute_trend_7d()
        trend_str = {"improving": "↑ 7j", "stable": "· stable 7j", "deteriorating": "↓ 7j", "no_history": "J0"}.get(
            trend, ""
        )
    except Exception as e:
        await update.message.reply_text(f"Note PF indisponible : {type(e).__name__}: {e}")
        return

    lines = [
        f"📊 NOTE DU PORTEFEUILLE — {snap_date}",
        "",
        f"  {grade_letter}  ·  {score}/100  ·  {trend_str}",
        f"  ({cap:.0f}€ · {n_pos} positions)",
        "",
    ]
    dim_labels = {
        "quality_T1_plus": "Qualité T1+T1★",
        "T2_redondant": "T2 redondant",
        "decorrelation_star": "Décorrélation ★",
        "sizing_conviction": "Sizing conviction",
        "cluster_cap": "Cluster cap",
        "thesis_health": "Santé des thèses",
    }
    for dk, label in dim_labels.items():
        d = dims.get(dk) or {}
        cur = d.get("current_pct", 0) or 0
        tgt = d.get("target_pct", 0) or 0
        kind = "≤" if dk in ("T2_redondant", "cluster_cap") else "≥"
        ok = (cur <= tgt) if kind == "≤" else (cur >= tgt)
        flag = "✅" if ok else "⚠️"
        ev = (d.get("evidence") or "")[:80]
        lines.append(f"{flag} {label:18s} {cur:>5.1f}% / {kind}{tgt:.0f}%")
        if ev:
            lines.append(f"   {ev}")
    lines.append("")
    lines.append("Sim trade : /grade sim TICKER buy|sell QTY [PRICE]")
    await update.message.reply_text("\n".join(lines))


async def cmd_chat(update, ctx):
    """/chat <question> — pose une question au copilot (meme RAG que dashboard).

    Single-shot (pas d'historique multi-tour sur Telegram pour l'instant).
    """
    args = ctx.args or []
    if not args:
        await update.message.reply_text(
            "Usage : /chat <question>\n"
            "Exemple : /chat Quelle est ma plus grosse fragilite en ce moment ?"
        )
        return
    message = " ".join(args).strip()
    await update.message.reply_text("Le copilot reflechit... (8-15s)")
    try:
        from dashboard.chat import chat as _chat

        result = _chat(message)
    except Exception as e:
        await update.message.reply_text(f"Erreur : {type(e).__name__}: {e}")
        return
    reply = result.get("reply") or "(reponse vide)"
    if result.get("error"):
        reply = f"⚠️ {reply}"
    # Telegram limit 4096
    if len(reply) > 3900:
        reply = reply[:3900] + "\n[truncated]"
    await update.message.reply_text(reply)
