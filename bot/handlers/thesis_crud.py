"""Day 10 E batch 4 extracted from bot/main.py.

Handlers: _parse_thesis_template, cmd_exit, cmd_exit_force, cmd_thesis_add, cmd_thesis_list, cmd_thesis_note, cmd_thesis_revisit
"""

from intelligence import thesis as thesis_mod
from shared import storage

THESIS_TEMPLATE = (
    "Format thesis_add (copie-colle, remplace les valeurs) :\n\n"
    "/thesis_add\n"
    "ticker: NVDA\n"
    "direction: long\n"
    "horizon: 24m\n"
    "conviction: 4\n"
    "drivers: AI capex growth >40%; HBM supply constraint; CUDA moat\n"
    "invalidation: revenue Q/Q <20%; major customer defection; CUDA alternative success\n"
    "profit_take: revenue growth peak; PE >55x; margin compression\n"
    "entry_price: 130\n"
    "target_partial: 250\n"
    "target_full: 350\n"
    "notes: AI infra primary play\n\n"
    "Multi-item: separer par ';'"
)


async def cmd_thesis_add(update, ctx):  # noqa: ARG001
    text = update.message.text or ""
    body_split = text.split(maxsplit=1)
    body = body_split[1] if len(body_split) > 1 else ""
    if not body.strip():
        await update.message.reply_text(THESIS_TEMPLATE)
        return
    params = _parse_thesis_template(body)
    if "ticker" not in params or "entry_price" not in params:
        await update.message.reply_text("Manque 'ticker' et/ou 'entry_price'. Tape /thesis_add seul pour le template.")
        return
    try:
        result = thesis_mod.add_thesis(
            ticker=params["ticker"],
            direction=params.get("direction", "long"),
            horizon=params.get("horizon", "12m"),
            conviction=int(params.get("conviction", 3)),
            key_drivers=params.get("drivers", ""),
            invalidation_triggers=params.get("invalidation", ""),
            entry_price=float(params["entry_price"]),
            target_partial=float(params["target_partial"]) if "target_partial" in params else None,
            target_full=float(params["target_full"]) if "target_full" in params else None,
            triggers_profit_take=params.get("profit_take", ""),
            notes=params.get("notes", ""),
        )
        msg = f"OK these #{result['thesis_id']} ajoutee pour {result['ticker']}"
        if result["warnings"]:
            msg += "\n\nWarnings:\n" + "\n".join(f"  - {w}" for w in result["warnings"])
        await update.message.reply_text(msg)
        if result.get("pre_mortem_display"):
            pm_msg = result["pre_mortem_display"]
            if len(pm_msg) > 3900:
                pm_msg = pm_msg[:3900] + "\n[truncated]"
            await update.message.reply_text(pm_msg)
    except (KeyError, ValueError) as e:
        await update.message.reply_text(f"Erreur: {e}\n\nTape /thesis_add seul pour le template.")


async def cmd_thesis_list(update, ctx):  # noqa: ARG001
    msg = thesis_mod.list_active()
    # Telegram hard limit 4096 chars; chunk on paragraph boundaries if needed
    if len(msg) <= 3900:
        await update.message.reply_text(msg)
        return
    chunks = []
    cur = ""
    for para in msg.split("\n\n"):
        if len(cur) + len(para) + 2 < 3900:
            cur = cur + "\n\n" + para if cur else para
        else:
            if cur:
                chunks.append(cur)
            cur = para
    if cur:
        chunks.append(cur)
    for c in chunks:
        await update.message.reply_text(c)


async def cmd_thesis_revisit(update, ctx):
    """Revisit a thesis. With ID/ticker arg: revisit ONLY that one (scoped mark).

    Bug-fix 2026-05-22: previously ignored ctx.args and looped over the entire
    due-list, marking ALL theses revisited on display (one /thesis revisit 34
    mass-marked all 33 active theses reviewed). Now respects the argument and
    only marks the explicitly-requested thesis.
    """
    args = ctx.args or []
    if args:
        ident = args[0].strip()
        t = storage.get_thesis(int(ident)) if ident.isdigit() else storage.get_thesis_by_ticker(ident.upper())
        if not t:
            await update.message.reply_text(f"These introuvable : {ident}")
            return
        questions = thesis_mod.build_revisit_questions(t)
        await update.message.reply_text(questions)
        storage.update_thesis_revisit(t["id"])
        return
    due = thesis_mod.get_revisit_due()
    if not due:
        await update.message.reply_text("Aucune these en attente de revisit mensuel.")
        return
    tickers = "  ".join(f"{t['ticker']}(#{t['id']})" for t in due)
    await update.message.reply_text(
        f"{len(due)} these(s) en attente de revisit :\n{tickers}\n\n"
        f"Revisit une par une : /thesis revisit <ID ou TICKER>"
    )


async def cmd_thesis_note(update, ctx):
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text("Usage: /thesis_note <thesis_id> <ta note>")
        return
    try:
        thesis_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text(f"thesis_id invalide: {ctx.args[0]}")
        return
    note = " ".join(ctx.args[1:])
    storage.append_thesis_note(thesis_id, note)
    await update.message.reply_text(f"Note ajoutee a these #{thesis_id}.")


async def cmd_exit(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Usage: /exit TICKER [current_price]")
        return
    ticker = ctx.args[0].upper()
    current_price = None
    if len(ctx.args) > 1:
        try:
            current_price = float(ctx.args[1])
        except ValueError:
            await update.message.reply_text(f"Prix invalide: {ctx.args[1]}")
            return
    result = thesis_mod.check_exit_request(ticker, current_price)
    await update.message.reply_text(result["message"])


async def cmd_exit_force(update, ctx):
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text("Usage: /exit_force TICKER <raison>")
        return
    ticker = ctx.args[0].upper()
    reason = " ".join(ctx.args[1:])
    t = storage.get_thesis_by_ticker(ticker, status="active")
    if not t:
        await update.message.reply_text(f"Pas de these active sur {ticker}.")
        return
    check = thesis_mod.check_exit_request(ticker)
    note_suffix = "[regret_driven]" if check["status"] == "no_trigger" else "[trigger_met]"
    storage.close_thesis(t["id"], status="realized", reason=f"{note_suffix} {reason}")
    await update.message.reply_text(f"OK these {ticker} fermee 'realized' {note_suffix}\nRaison: {reason}")


def _parse_thesis_template(text):
    out = {}
    for line in text.split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        val = val.strip()
        if val:
            out[key] = val
    return out



async def cmd_thesis(update, ctx):
    """Family dispatcher: /thesis <sub-action> [args].

    Sub-actions: add, list, set, note, revisit, health, premortem, asymmetry, check_triggers
    """
    args = ctx.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /thesis <sub-action> [args]\n\n"
            "Sub-actions:\n"
            "  /thesis list                            Active theses list\n"
            "  /thesis add [template]                  Create new thesis\n"
            "  /thesis set TICKER field value          Edit thesis field\n"
            "  /thesis note ID text                    Add note to thesis\n"
            "  /thesis revisit [TICKER]                Revisit thesis\n"
            "  /thesis health [days] [min_impact]      Health snapshot\n"
            "  /thesis premortem ID                    Show pre-mortem\n"
            "  /thesis asymmetry [TICKER]              Asymmetry ratio\n"
            "  /thesis check_triggers                  Manual trigger check\n"
        )
        return
    sub = args[0].lower()
    rest = args[1:]

    if sub in ("list", "add", "note", "revisit"):
        ctx.args = rest
        if sub == "list":
            await cmd_thesis_list(update, ctx)
        elif sub == "add":
            await cmd_thesis_add(update, ctx)
        elif sub == "note":
            await cmd_thesis_note(update, ctx)
        elif sub == "revisit":
            await cmd_thesis_revisit(update, ctx)
        return

    if sub == "set":
        from bot.handlers.misc import _thesis_set_impl
        await _thesis_set_impl(update, rest)
    elif sub == "health":
        from bot.handlers.thesis_health import _thesis_health_impl
        await _thesis_health_impl(update, rest)
    elif sub == "premortem":
        from bot.handlers.thesis_analyze import _thesis_premortem_impl
        await _thesis_premortem_impl(update, rest)
    elif sub == "asymmetry":
        from bot.handlers.misc import _asymmetry_impl
        await _asymmetry_impl(update, rest)
    elif sub == "check_triggers":
        from bot.handlers.echo_crypto_macro import _price_check_impl
        await _price_check_impl(update)
    else:
        await update.message.reply_text(
            f"Unknown sub-action: {sub}\nUse /thesis (no args) for help."
        )
