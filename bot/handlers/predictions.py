"""Day 10 E batch 2+3 extracted from bot/main.py.

Handlers: cmd_credibility, cmd_feedback, cmd_predictions, cmd_resolve_now
"""

from intelligence import credibility as credibility_mod, learning as learning_mod
from shared import storage


async def cmd_credibility(update, ctx):  # noqa: ARG001
    """Credibilite des sources : top 10 + bottom 5."""
    msg = credibility_mod.list_top_sources(n=10)
    msg += "\n\n" + credibility_mod.list_worst_sources(n=5)
    await update.message.reply_text(msg)


async def cmd_predictions(update, ctx):
    """Sprint 1.2 Phase K dispatcher.

    /predictions          → list recent 15 predictions (default)
    /predictions resolve  → manual trigger resolve_due_predictions cron
    """
    args = ctx.args or []

    if args and args[0].lower() == "resolve":
        await _predictions_resolve(update, ctx)
        return

    preds = storage.get_recent_predictions(limit=15)
    if not preds:
        await update.message.reply_text("Aucune prediction enregistree.")
        return
    lines = ["Predictions recentes:"]
    for p in preds:
        ticker = p.get("ticker", "?")
        dir_ = (p.get("direction") or "?")[:4]
        baseline = p.get("baseline_price") or 0
        target = p.get("target_date", "?")
        outcome = p.get("outcome") or "pending"
        ret = p.get("return_pct")
        if ret is not None:
            lines.append(f"#{p['id']} {ticker} {dir_} ${baseline:.2f} -> {ret * 100:+.1f}% [{outcome}]")
        else:
            lines.append(f"#{p['id']} {ticker} {dir_} ${baseline:.2f} target {target} [pending]")
    await update.message.reply_text("\n".join(lines))


async def _predictions_resolve(update, ctx):  # noqa: ARG001
    """Sub-action: trigger resolve_due_predictions cron manually."""
    await update.message.reply_text("Resolution en cours...")
    try:
        results = learning_mod.resolve_due_predictions()
        msg = learning_mod.format_resolve_report(results)
        await update.message.reply_text(msg[:4000])
    except Exception as e:
        await update.message.reply_text(f"Erreur: {type(e).__name__}: {e}")


async def cmd_resolve_now(update, ctx):  # noqa: ARG001
    """Force la resolution des predictions arrivees a echeance."""
    await update.message.reply_text("Resolution en cours...")
    try:
        results = learning_mod.resolve_due_predictions()
        msg = learning_mod.format_resolve_report(results)
        await update.message.reply_text(msg[:4000])
    except Exception as e:
        await update.message.reply_text(f"Erreur: {type(e).__name__}: {e}")


async def cmd_feedback(update, ctx):
    """Feedback up/down sur un signal. Usage: /feedback <signal_id> <up|down>."""
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text(
            "Usage: /feedback <signal_id> <up|down>\nEx: /feedback 42 up\n(signal_id affiches dans le digest avec prefix #)"
        )
        return
    try:
        signal_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text(f"signal_id invalide: {ctx.args[0]}")
        return
    rating = ctx.args[1].lower()
    if rating not in ("up", "down"):
        await update.message.reply_text(f"rating doit etre up ou down, got: {rating}")
        return
    await _feedback_impl(update, signal_id, rating)


async def _feedback_impl(update, signal_id: int, rating: str) -> None:
    """Internal: apply user feedback to signal source credibility.

    Used by cmd_feedback (legacy /feedback alias) and cmd_sources
    (Sprint 1.2 Phase I dispatcher /sources feedback ID up|down).
    Body extracted verbatim, no dedent (body at 4sp direct-in-function).
    """
    try:
        result = credibility_mod.apply_feedback(signal_id, rating)
        old = result.get("old_credibility") or 0.5
        new = result.get("new_credibility") or 0.5
        src = (result.get("source_name") or "?")[:40]
        msg = f"OK feedback {rating} sur signal #{signal_id}.\nSource: {src}\nCredibility: {old:.2f} -> {new:.2f} (delta {result['delta']:+.2f})"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Erreur: {type(e).__name__}: {e}")
