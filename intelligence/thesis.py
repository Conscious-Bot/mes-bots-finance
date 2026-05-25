"""Thesis tracker — behavioral edge module.

Forces bidirectional pre-commit discipline:
- At entry: drivers + invalidation triggers + profit-take triggers + targets + horizon
- At exit: anti-premature-exit checkpoint (require trigger validation)
- Monthly: revisit with mirror questions ('Why should I HOLD?' before 'Should I sell?')

Addresses regret-driven decisions both ways:
- Anti loss-aversion / mean-reversion: prevents selling winners on emotion
- Anti FOMO / late-exit: surfaces profit-take signals
"""

from shared import storage


def add_thesis(
    ticker,
    direction,
    horizon,
    conviction,
    key_drivers,
    invalidation_triggers,
    entry_price,
    target_partial=None,
    target_full=None,
    triggers_profit_take=None,
    target_price=None,
    notes=None,
):
    """Add a new thesis with discipline checks. Returns dict with thesis_id + warnings."""
    warnings = []

    if direction not in ("long", "short", "watch"):
        raise ValueError(f"direction must be long/short/watch, got: {direction}")
    if not isinstance(conviction, int) or conviction < 1 or conviction > 5:
        raise ValueError(f"conviction must be int 1-5, got: {conviction}")

    if isinstance(key_drivers, str):
        key_drivers = [d.strip() for d in key_drivers.split(";") if d.strip()]
    if isinstance(invalidation_triggers, str):
        invalidation_triggers = [t.strip() for t in invalidation_triggers.split(";") if t.strip()]
    if isinstance(triggers_profit_take, str):
        triggers_profit_take = [t.strip() for t in triggers_profit_take.split(";") if t.strip()]

    if len(key_drivers) < 2:
        warnings.append("Moins de 2 drivers - these molle. Ajoute en.")
    if len(invalidation_triggers) < 1:
        warnings.append("Aucun trigger d'invalidation - DANGER. C'est ce qui te fera tenir si la these s'effondre.")
    if direction == "long" and not (triggers_profit_take or target_partial or target_full):
        warnings.append("Aucun trigger de profit-take ni target. Tu ne sauras pas quand vendre.")
    if conviction == 5:
        warnings.append("Conviction 5 = tres rare. Tu es sur ?")

    thesis_id = storage.insert_thesis(
        ticker=ticker,
        direction=direction,
        horizon=horizon,
        conviction=conviction,
        key_drivers=key_drivers,
        invalidation_triggers=invalidation_triggers,
        entry_price=entry_price,
        target_price=target_price,
        target_partial=target_partial,
        target_full=target_full,
        triggers_profit_take=triggers_profit_take,
        notes=notes,
    )

    # Phase B7 — Pre-mortem auto-generation (Opus call, blocks ~5-15s)
    pre_mortem_display = None
    try:
        from intelligence import pre_mortem as pm_mod

        full = storage.get_thesis_full(thesis_id) or {}
        full["key_drivers"] = key_drivers
        full["invalidation_triggers"] = invalidation_triggers
        pm_json = pm_mod.generate_pre_mortem(full)
        if pm_json:
            storage.update_thesis_pre_mortem(thesis_id, pm_json)
            pre_mortem_display = pm_mod.format_pre_mortem_display(pm_json)
    except Exception:
        pass

    return {
        "thesis_id": thesis_id,
        "ticker": ticker.upper(),
        "warnings": warnings,
        "pre_mortem_display": pre_mortem_display,
    }


def format_thesis_card(thesis):
    """Format a thesis for Telegram display (Markdown)."""
    direction_icon = {"long": "[L]", "short": "[S]", "watch": "[W]"}.get(thesis.get("direction"), "?")
    status_icon = {"active": "ACTIVE", "invalidated": "INVALIDATED", "realized": "REALIZED", "stale": "STALE"}.get(
        thesis.get("status"), "?"
    )

    lines = [
        f"*{thesis['ticker']}* {direction_icon} | conviction {thesis['conviction']}/5 | {status_icon}",
        f"_horizon {thesis.get('horizon', '?')}, opened {(thesis.get('opened_at') or '?')[:10]}_",
        f"entry: ${thesis.get('entry_price', '?')}",
    ]
    if thesis.get("target_partial"):
        lines.append(f"target partiel: ${thesis['target_partial']}")
    if thesis.get("target_full"):
        lines.append(f"target plein: ${thesis['target_full']}")

    drivers = thesis.get("key_drivers") or []
    if drivers:
        lines.append("")
        lines.append("*Drivers:*")
        for d in drivers:
            lines.append(f"  - {d}")

    invalid = thesis.get("invalidation_triggers") or []
    if invalid:
        lines.append("")
        lines.append("*Invalidation triggers:*")
        for t in invalid:
            lines.append(f"  ! {t}")

    pt = thesis.get("triggers_profit_take") or []
    if pt:
        lines.append("")
        lines.append("*Profit-take triggers:*")
        for t in pt:
            lines.append(f"  $ {t}")

    notes = thesis.get("notes") or ""
    if notes:
        lines.append("")
        lines.append(f"_notes: {notes[:300]}_")
    return "\n".join(lines)


def list_active():
    """Return formatted list of all active theses."""
    theses = storage.list_theses(status="active")
    if not theses:
        return "Aucune these active. Utilise /thesis_add pour en creer une."
    parts = [f"*{len(theses)} these(s) active(s):*", ""]
    for t in theses:
        parts.append(format_thesis_card(t))
        parts.append("---")
    return "\n".join(parts)


def check_exit_request(ticker, current_price=None):
    """Anti-premature-exit + late-exit checkpoint.

    Returns dict: thesis_found, status, triggers_met, message, thesis (optional).
    """
    thesis = storage.get_thesis_by_ticker(ticker, status="active")
    if not thesis:
        return {
            "thesis_found": False,
            "status": "no_thesis",
            "message": f"Pas de these active sur {ticker.upper()}. Exit OK sans checkpoint.",
        }

    triggers_met = []
    if current_price is not None and thesis.get("target_full") and current_price >= thesis["target_full"]:
        triggers_met.append(f"target plein atteint (${thesis['target_full']})")

    if triggers_met:
        return {
            "thesis_found": True,
            "thesis": thesis,
            "status": "trigger_met",
            "triggers_met": triggers_met,
            "message": (
                f"OK Exit JUSTIFIE sur {ticker.upper()}.\n\n"
                + "Conditions atteintes :\n"
                + "\n".join(f"  - {t}" for t in triggers_met)
                + "\n\nUtilise /exit_force pour confirmer la sortie effective."
            ),
        }

    parts = [f"*EXIT NON JUSTIFIE sur {ticker.upper()}*", ""]
    parts.append(f"Ta these (conviction {thesis['conviction']}/5, opened {(thesis.get('opened_at') or '?')[:10]}) :")
    parts.append("")

    drivers = thesis.get("key_drivers") or []
    if drivers:
        parts.append("*Drivers que tu as poses :*")
        for d in drivers:
            parts.append(f"  - {d}")
        parts.append("")

    invalid = thesis.get("invalidation_triggers") or []
    if invalid:
        parts.append("*Triggers d'invalidation (aucun atteint) :*")
        for t in invalid:
            parts.append(f"  ! {t}")
        parts.append("")

    targets = []
    if thesis.get("target_partial"):
        targets.append(f"partiel ${thesis['target_partial']}")
    if thesis.get("target_full"):
        targets.append(f"plein ${thesis['target_full']}")
    if targets and current_price:
        parts.append(f"*Targets (non atteints @ ${current_price}) :* {', '.join(targets)}")
        parts.append("")

    parts.append("*Question :* aucun trigger n'a ete declenche. Pourquoi sortir ?")
    parts.append("")
    parts.append("Si tu confirmes la sortie emotionnelle (regret-driven), utilise :")
    parts.append(f"`/exit_force {ticker.upper()} <raison>`")
    parts.append("Le bot loggera la sortie comme non-justifiee pour la calibration future.")

    return {
        "thesis_found": True,
        "thesis": thesis,
        "status": "no_trigger",
        "triggers_met": [],
        "message": "\n".join(parts),
    }


def get_revisit_due():
    """Return list of theses due for monthly revisit."""
    return storage.get_theses_due_for_revisit(days_threshold=30)


def build_revisit_questions(thesis):
    """Generate mirror questions for monthly revisit. Order matters: HOLD first."""
    lines = [
        f"*Revisit mensuel - {thesis['ticker']}* (conviction {thesis['conviction']}/5)",
        "",
        "*Drivers initiaux :*",
    ]
    for d in thesis.get("key_drivers") or []:
        lines.append(f"  - {d}")
    lines.append("")
    lines.append("*Triggers d'invalidation :*")
    for t in thesis.get("invalidation_triggers") or []:
        lines.append(f"  ! {t}")
    lines.append("")
    lines.append("*Question 1 - POURQUOI HOLD ?*")
    lines.append("Qu'est-ce qui te confirme aujourd'hui que tes drivers tiennent encore ?")
    lines.append("")
    lines.append("*Question 2 - POURQUOI SELL ?*")
    lines.append("Un trigger d'invalidation s'est-il declenche ?")
    lines.append("Un trigger de profit-take s'est-il declenche ?")
    lines.append("")
    lines.append("*Question 3 - TON BIAIS DU MOIS ?*")
    lines.append("Es-tu en train de ceder a la peur de rendre tes gains, ou a la FOMO ?")
    lines.append("")
    lines.append(f"Pour logger ta reflexion : `/thesis_note {thesis['id']} <ta reponse>`")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== Test thesis.py ===")
    print("\n1. List active theses :")
    print(list_active())
    print("\n2. Theses due for revisit :")
    due = get_revisit_due()
    print(f"   {len(due)} these(s) due")
    print("\n3. Check exit on non-existent thesis (NVDA) :")
    r = check_exit_request("NVDA", current_price=300)
    print(r["message"])
