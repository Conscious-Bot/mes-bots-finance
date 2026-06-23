"""Telegram handler /adversarial — 4-stage bull/bear/counter/synth loop.

Usage : /adversarial <ticker> [buy|sell|trim|review]
  /adversarial GEV buy
  /adversarial KLAC trim

Garde-fous (memes que /research) :
- Rate-limit 1/h/user via shared.storage.check_research_brief_rate_limit
- Cap budget LLM hard ($X/jour) — partage le budget de /research
- Anti-anchoring : refuse send si verdict pattern detecte (gate in run())
- Fail-closed : si tous backends down, message clair pas brief fabrique

Differe de /research : extraction LLM des claims + verdicts par counter-evidence.
Output structuré avec emoji verdict (✅❌🔄❓) pour scan rapide.
"""
from __future__ import annotations

import logging

log = logging.getLogger("bot")

# Budget hard cap quotidien partage avec /research : $5/jour
_DAILY_BUDGET_USD = 5.0
_VALID_INTENTS = {"buy", "sell", "trim", "review"}


async def cmd_adversarial(update, ctx):  # noqa: ARG001
    """/adversarial <ticker> [intent] — 4-stage adversarial pre-trade research."""
    from intelligence.adversarial_research_loop import run
    from shared import notify
    from shared.storage import get_research_brief_cost_today

    msg = update.message
    user_id = str(update.effective_user.id) if update.effective_user else "anon"

    # Parse args : ticker + optional intent
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.reply_text(
            "Usage : `/adversarial <ticker> [intent]`\n\n"
            "Intent : buy (default) | sell | trim | review\n\n"
            "Exemples :\n"
            "  `/adversarial GEV buy`\n"
            "  `/adversarial KLAC trim`\n\n"
            "_4-stage loop : bull → bear adversaire → counter-evidence → verdicts._\n"
            "_LLM extract claims + judge contre counter-search. ZERO direction._",
            parse_mode="Markdown",
        )
        return

    target = parts[1].strip().upper()
    intent = parts[2].strip().lower() if len(parts) > 2 else "buy"
    if intent not in _VALID_INTENTS:
        await msg.reply_text(
            f"Intent invalide : `{intent}`. Use : {' / '.join(_VALID_INTENTS)}",
            parse_mode="Markdown",
        )
        return

    # Budget cap check (partage avec /research)
    try:
        spent_today = get_research_brief_cost_today(user_id)
        if spent_today >= _DAILY_BUDGET_USD:
            await msg.reply_text(
                f"Budget quotidien research+adversarial atteint "
                f"(${spent_today:.2f} / ${_DAILY_BUDGET_USD:.2f}). Reset minuit UTC."
            )
            return
    except Exception as e:
        log.warning(f"cmd_adversarial budget check err: {e}")

    # Inform : 4 stages = ~30-60s
    await msg.reply_text(
        f"🔬 Adversarial loop `{target}` ({intent}) ~30-60s...\n"
        "_4 stages : bull → bear → counter → verdicts_",
        parse_mode="Markdown",
    )

    try:
        result = run(target=target, user_id=user_id, intent=intent)
    except Exception as e:
        log.exception(f"cmd_adversarial loop failed for target={target!r}: {e}")
        await msg.reply_text(
            f"❌ Erreur loop : {type(e).__name__}. Sources peut-etre indisponibles."
        )
        return

    if not result.ok:
        await msg.reply_text(f"❌ {result.error or 'Erreur inconnue'}")
        return

    markdown = result.markdown
    # Telegram limit 4096 chars per message — split si besoin
    if len(markdown) <= 4000:
        await notify.send_text(markdown, parse_mode="Markdown")
    else:
        chunks = [markdown[i:i + 4000] for i in range(0, len(markdown), 4000)]
        for chunk in chunks:
            await notify.send_text(chunk, parse_mode="Markdown")
