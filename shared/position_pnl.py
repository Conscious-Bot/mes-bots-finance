"""SOCLE canonique : P&L position EUR -- source unique.

Cf migration alembic 0043 + directive Olivier 08/06 :
  "on choisit EUR et on s'y tient. Sourcer + convertir auto a l'entree."

Helper UNIQUE pour le P&L position. Tout consumer (book row, panneau theses,
card, governor) consomme cette fonction -- aucun calc local du P&L position
ne doit survivre.

Conventions (apres migration 0043) :
  - positions.avg_cost_eur : valeur canonique EUR (backfill cohérent USD->EUR via fx,
    autres legacy EUR tel quel).
  - value_eur_now = qty * last_price_native * fx_rate_to_eur (déja correct via
    shared.valuation.position_valuation -> Datum compose, cf SOCLE Phase 2 S2).

Le P&L canonique :
  cost_basis_eur = qty * avg_cost_eur
  value_eur_now = via position_valuation (Datum compose, fx-correct)
  pnl_position_pct_eur = (value_eur_now / cost_basis_eur - 1) * 100
  pnl_position_eur = value_eur_now - cost_basis_eur

Tous deux en EUR cohérent. Aucun mismatch FX possible.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def pnl_position_pct_eur(position: dict[str, Any] | Any) -> float | None:
    """P&L position canonique en EUR. Source unique pour TOUS les consumers.

    Args:
        position : dict (row positions) OU object BookLine-like
                   Doit fournir : qty, avg_cost_eur, ticker
                   OU equivalent attribute access.

    Returns:
        float | None : pnl_pct en EUR cohérent.
                       None si fail-closed (qty manquant, avg_cost_eur manquant,
                       value_eur non-derivable).

    Discipline L15 fail-closed : retourne None plutôt qu'un nombre fabrique.
    Le caller doit afficher "n/a" ou un fallback, jamais un chiffre faux.
    """
    # Extract fields (dict or object)
    def _g(key: str) -> Any:
        if isinstance(position, dict):
            return position.get(key)
        return getattr(position, key, None)

    qty = _g("qty")
    avg_cost_eur = _g("avg_cost_eur")
    ticker = _g("ticker")

    # Fail-closed : inputs critiques manquants
    if not qty or not avg_cost_eur or not ticker:
        return None
    if qty <= 0 or avg_cost_eur <= 0:
        return None

    # cost_basis_eur cohérent
    cost_basis_eur = qty * avg_cost_eur

    # value_eur_now via position_valuation (Datum compose, fx-correct)
    # Si position est un row dict avec id -> on peut appeler position_valuation
    position_id = _g("id")
    if position_id is not None:
        try:
            from shared.valuation import position_valuation
            pv = position_valuation(int(position_id))
            if pv is not None and pv.value_eur is not None:
                value_eur_now = pv.value_eur
                return (value_eur_now / cost_basis_eur - 1) * 100.0
        except Exception as e:
            log.warning(f"position_valuation fallback for {ticker}: {e}")

    # Fallback : calculer value_eur_now depuis attributs du position dict
    last_price_native = _g("last_price_native")
    fx_rate = _g("fx_rate_to_eur")
    if not last_price_native or not fx_rate or last_price_native <= 0 or fx_rate <= 0:
        return None
    value_eur_now = qty * last_price_native * fx_rate
    return (value_eur_now / cost_basis_eur - 1) * 100.0


def pnl_position_eur(position: dict[str, Any] | Any) -> float | None:
    """P&L position en EUR (montant absolu, pas %). Source unique.

    Returns:
        float | None : pnl en EUR. None si fail-closed.
    """
    pct = pnl_position_pct_eur(position)
    if pct is None:
        return None

    def _g(key: str) -> Any:
        if isinstance(position, dict):
            return position.get(key)
        return getattr(position, key, None)

    qty = _g("qty") or 0
    avg_cost_eur = _g("avg_cost_eur") or 0
    if qty <= 0 or avg_cost_eur <= 0:
        return None
    cost_basis_eur = qty * avg_cost_eur
    return cost_basis_eur * (pct / 100.0)
