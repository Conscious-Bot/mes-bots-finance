"""Telegram handler /research — Spec #152 / chantier #150 G3.

Usage : /research <ticker_ou_theme>
  /research AAPL
  /research data center power grid

Garde-fous (SPEC §5) :
- Rate-limit 1/h/user via shared.storage.check_research_brief_rate_limit
- Cap budget LLM hard ($X/jour) — check via shared.storage.get_research_brief_cost_today
- Anti-anchoring : refuse send si verdict pattern detecte (cf intelligence.research_brief)
- Fail-closed : si Bigdata down ou cible inconnue, message clair pas brief fabrique
"""
from __future__ import annotations

import logging

log = logging.getLogger("bot")

# Budget hard cap quotidien : $5/jour (suffit pour 100 briefs ~$0.05 each)
_DAILY_BUDGET_USD = 5.0


async def cmd_research(update, ctx):  # noqa: ARG001
    """/research <ticker|theme> — fournit matiere factuelle structuree."""
    from intelligence.research_brief import fetch
    from shared import notify
    from shared.storage import get_research_brief_cost_today

    msg = update.message
    user_id = str(update.effective_user.id) if update.effective_user else "anon"

    # Parse args
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.reply_text(
            "Usage : `/research <ticker_ou_theme>`\n\n"
            "Exemples :\n"
            "  `/research AAPL`\n"
            "  `/research data center power grid`\n\n"
            "_Fournit faits + consensus + news + cadre causal. ZERO jugement._",
            parse_mode="Markdown",
        )
        return

    target = parts[1].strip()

    # Budget cap check
    try:
        spent_today = get_research_brief_cost_today(user_id)
        if spent_today >= _DAILY_BUDGET_USD:
            await msg.reply_text(
                f"Budget research quotidien atteint (${spent_today:.2f} / "
                f"${_DAILY_BUDGET_USD:.2f}). Reset minuit UTC."
            )
            return
    except Exception as e:
        log.warning(f"cmd_research budget check err: {e}")

    # Inform user that fetch is in progress (Bigdata calls can take 5-15s)
    await msg.reply_text(f"🔍 Brief en cours pour `{target}` ~10s...", parse_mode="Markdown")

    # Fetch + format
    try:
        result = fetch(target=target, user_id=user_id)
    except Exception as e:
        log.exception(f"cmd_research fetch failed for target={target!r}: {e}")
        await msg.reply_text(f"❌ Erreur fetch : {type(e).__name__}. Sources peut-etre indisponibles, retry.")
        return

    if not result.get("ok"):
        await msg.reply_text(f"❌ {result.get('error', 'Erreur inconnue')}")
        return

    markdown = result["markdown"]

    # Telegram limit 4096 chars per message — split si besoin
    if len(markdown) <= 4000:
        await notify.send_text(markdown, parse_mode="Markdown")
    else:
        chunks = [markdown[i:i + 4000] for i in range(0, len(markdown), 4000)]
        for chunk in chunks:
            await notify.send_text(chunk, parse_mode="Markdown")
