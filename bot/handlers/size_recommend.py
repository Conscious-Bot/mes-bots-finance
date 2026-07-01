"""/size_recommend — Telegram handler voluntary advisor sur le sizing Kelly.

Phase 2 wiring (26/06/2026) : surface le module risk/sizing.py:position_size()
qui est FEATURE READY mais NOT YET WIRED INTO RUNTIME depuis 13 mai 2026.

Pattern : voluntary advisor. L'user appelle quand il veut. Pas de blocage
auto-magique de /position_buy aujourd'hui (à dial up si le pattern d'usage
le justifie). Doctrine : "tu décides, je dis ce que la math dit".

Usage Telegram :
    /size_recommend TICKER EDGE_PCT VARIANCE [CONVICTION] [CAPITAL_EUR]

    EDGE_PCT       : edge attendu en fraction (ex 0.05 = 5%)
    VARIANCE       : variance estimée du return (ex 0.04 si vol 20%)
    CONVICTION     : 1-5 optionnel (défaut = aucun, cap c5 sommet bride)
    CAPITAL_EUR    : optionnel (défaut = book value courant)

Exemple :
    /size_recommend AVGO 0.04 0.05 3
    → reco €X (Quarter Kelly + cap c3 4.5%)

Réf : risk/sizing.py (formula UNIQUE Quarter Kelly + cap dur)
      shared/sizing_caps.py (source de vérité cap par conviction)
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from risk.sizing import position_size
from shared import storage
from shared.sizing_caps import cap_for_conviction

logger = logging.getLogger(__name__)


def _current_book_value_eur() -> float | None:
    """Lit la dernière valeur du book (pf_value) du dernier portfolio_grade.

    Fail-soft : retourne None si pas dispo, callsite gère.
    """
    try:
        with storage.db() as cx:
            row = cx.execute(
                "SELECT total_capital_eur FROM portfolio_grades "
                "ORDER BY snapshot_at DESC LIMIT 1"
            ).fetchone()
            if row and row[0] and row[0] > 0:
                return float(row[0])
    except Exception as e:
        logger.debug("book value fetch fail: %s", e)
    return None


async def cmd_size_recommend(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """`/size_recommend TICKER EDGE_PCT VARIANCE [CONVICTION] [CAPITAL_EUR]`"""
    if not ctx.args or len(ctx.args) < 3:
        msg = (
            "Usage : `/size_recommend TICKER EDGE_PCT VARIANCE [CONVICTION] [CAPITAL_EUR]`\n\n"
            "Exemple : `/size_recommend AVGO 0.04 0.05 3`\n"
            "= edge 4%, variance 5% (vol ~22%), conviction c3 → Quarter Kelly + cap c3 4.5%.\n\n"
            "Paramètres :\n"
            "• EDGE\\_PCT : edge attendu en fraction (0.05 = 5%)\n"
            "• VARIANCE : variance estimée (ex 0.04 si vol 20%)\n"
            "• CONVICTION (opt) : 1-5, sinon cap c5 conservatif\n"
            "• CAPITAL\\_EUR (opt) : sinon book value courant"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    ticker = ctx.args[0].upper()
    try:
        edge_pct = float(ctx.args[1])
        variance = float(ctx.args[2])
    except ValueError:
        await update.message.reply_text(
            "❌ EDGE\\_PCT et VARIANCE doivent être des floats (ex 0.04 0.05).",
            parse_mode="Markdown",
        )
        return

    conviction: int | None = None
    if len(ctx.args) >= 4:
        try:
            c = int(ctx.args[3])
            if c not in (1, 2, 3, 4, 5):
                raise ValueError("range")
            conviction = c
        except ValueError:
            await update.message.reply_text("❌ CONVICTION doit être 1-5.")
            return

    capital: float | None = None
    if len(ctx.args) >= 5:
        try:
            capital = float(ctx.args[4])
        except ValueError:
            await update.message.reply_text("❌ CAPITAL\\_EUR doit être un float.", parse_mode="Markdown")
            return

    if capital is None:
        capital = _current_book_value_eur()
        if capital is None:
            await update.message.reply_text(
                "❌ Book value indisponible (portfolio_grade_history vide). "
                "Passe CAPITAL\\_EUR explicite en 5e arg.",
                parse_mode="Markdown",
            )
            return

    sized_eur = position_size(
        edge_pct=edge_pct,
        variance_estimate=variance,
        capital=capital,
        regime_factor=1.0,
        conviction=conviction,
    )
    cap_pct = cap_for_conviction(conviction)
    cap_eur = capital * cap_pct
    raw_kelly_pct = edge_pct / variance if variance > 0 else 0
    quarter_kelly_pct = raw_kelly_pct * 0.25
    quarter_kelly_eur = capital * quarter_kelly_pct

    # Was cap hit ?
    capped = sized_eur < quarter_kelly_eur - 0.01
    cap_note = f" (capped à c{conviction}={cap_pct * 100:.1f}%)" if capped and conviction else ""
    if capped and conviction is None:
        cap_note = " (capped à c5 conservatif 6.0%)"

    conv_lbl = f"c{conviction}" if conviction else "c5 (default)"

    msg = (
        f"📐 *Size recommend* — {ticker}\n\n"
        f"Inputs : edge={edge_pct * 100:.2f}%, variance={variance:.4f}, "
        f"conviction={conv_lbl}\n"
        f"Capital base : €{capital:,.0f}\n\n"
        f"Raw Kelly : {raw_kelly_pct * 100:.2f}% (€{capital * raw_kelly_pct:,.0f})\n"
        f"Quarter Kelly : {quarter_kelly_pct * 100:.2f}% (€{quarter_kelly_eur:,.0f})\n"
        f"Cap par conviction : {cap_pct * 100:.1f}% (€{cap_eur:,.0f})\n\n"
        f"➡️ *Sized = €{sized_eur:,.0f}*{cap_note}\n\n"
        f"_Voluntary advisor — pas de blocage auto sur /position\\_buy._\n"
        f"_Réf : risk/sizing.py + shared/sizing\\_caps.py_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
