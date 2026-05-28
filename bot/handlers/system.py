"""System-level handlers: ping (liveness probe) + help (commands index)."""

from shared import storage


async def cmd_ping(update, ctx):  # noqa: ARG001
    """Liveness probe : alive + capital + drawdown."""
    state = storage.load_state()
    await update.message.reply_text(
        f"alive\n"
        f"capital: ${state['current_capital']:.0f}\n"
        f"drawdown: {state['drawdown_pct']:.1%}\n"
        f"theses actives: {state['active_theses_count']}\n"
        f"paper_only: {state['paper_only']}"
    )


async def cmd_help(update, ctx):
    """Liste des commandes enregistrees, generee depuis le registre (source unique)."""
    from telegram.ext import CommandHandler as _CH

    seen: dict[str, str] = {}
    for group in ctx.application.handlers.values():
        for h in group:
            if not isinstance(h, _CH):
                continue
            doc = (h.callback.__doc__ or "").strip().split("\n")[0].strip()
            names = getattr(h, "commands", None) or getattr(h, "command", None) or []
            for name in names:
                seen.setdefault(str(name), doc)

    items = sorted(seen.items())
    header = f"mes-bots-finance — {len(items)} commandes (genere du registre)\n\n"
    rows = [f"/{name}  {doc[:55]}" for name, doc in items]

    limit = 3800
    chunk = header
    for row in rows:
        if len(chunk) + len(row) + 1 > limit:
            await update.message.reply_text(chunk.rstrip())
            chunk = ""
        chunk += row + "\n"
    if chunk.strip():
        await update.message.reply_text(chunk.rstrip())
