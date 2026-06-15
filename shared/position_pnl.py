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
    ticker = _g("ticker")
    if not qty or not ticker or qty <= 0:
        return None

    # === cost_basis_eur : priorité simple > legacy native×fx ===
    #
    # Vérité hand-checked AMD (cf garde Olivier R) :
    #   qty 4.12 × avg_cost_eur 127.20 = cost_basis 524.06 EUR
    #   qty × last_price_native × fx_rate_to_eur = value_eur 1666.84 EUR
    #   pnl_pct = +218.0%  (la vrai P&L Olivier)
    #
    # Priorité 1 : avg_cost_eur direct (post-M1 simple, contrat clair).
    # Priorité 2 : avg_cost_native × fx_at_purchase (legacy 0044, conservée
    #              pour positions migrées avec triple Monetary natif).
    avg_cost_eur = _g("avg_cost_eur")
    if not avg_cost_eur or avg_cost_eur <= 0:
        # Fallback legacy : derive depuis native × fx_at_purchase
        avg_cost_native = _g("avg_cost_native")
        fx_at_purchase = _g("fx_at_purchase")
        if not avg_cost_native or not fx_at_purchase:
            return None
        if avg_cost_native <= 0 or fx_at_purchase <= 0:
            return None
        avg_cost_eur = avg_cost_native * fx_at_purchase

    cost_basis_eur = qty * avg_cost_eur

    # === value_eur_now : priorité inputs du dict > Datum canonique live ===
    #
    # Priorité 1 : inputs du position dict (last_price_native + fx_rate_to_eur).
    #              C'est la vérité passée par le caller (test unit fixture OU
    #              BookLine canonique pré-chargé avec snapshot DB). Respecter
    #              les inputs garantit déterminisme et tests reproductibles.
    # Priorité 2 : book.value_eur(ticker, qty) -> Datum[Monetary(EUR)] live
    #              via prices.get + prices.fx. Utilisé si le dict ne porte pas
    #              les fields ; le caller veut donc du live frais.
    last_price_native = _g("last_price_native")
    fx_rate = _g("fx_rate_to_eur")
    if last_price_native and fx_rate and last_price_native > 0 and fx_rate > 0:
        value_eur_now = qty * last_price_native * fx_rate
    else:
        value_eur_now = None
        try:
            from shared.book import value_eur as book_value_eur
            bv = book_value_eur(ticker, qty)
            if bv is not None and bv.value is not None and hasattr(bv.value, "amount"):
                value_eur_now = float(bv.value.amount)
        except Exception as e:
            log.warning(f"book.value_eur fallback for {ticker}: {e}")
        if value_eur_now is None or value_eur_now <= 0:
            return None

    pnl_pct = (value_eur_now / cost_basis_eur - 1) * 100.0

    # NOTE 15/06/2026 : register_concept retire (cure fork detection #145).
    # Le helper n'a pas de production caller, seul tests/test_position_pnl_canonical.py
    # l'appelle avec fixtures hardcoded → pollue concept_index avec valeurs fixture
    # → fork detection systematic (helper fixture stale vs view live). Source
    # canonique = position_view.compute_position() qui register depuis _views
    # central (dashboard/render.py post-regen). Le helper devient pure calcul.
    # Tests math toujours verts (l'effet side-effect register etait dispensable).
    return pnl_pct


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
