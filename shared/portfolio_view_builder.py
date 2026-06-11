"""Cure #120 étape 2 12/06/2026 — builder positions vit dans shared/, pas dashboard/.

Le builder `_positions()` était dans `dashboard/render.py:3823` mais c'est pure
logique (book.get_held_lines + view.value_eur_datum + shape dict). Zéro rendu
HTML/CSS. Sa place est shared/, pas dashboard/.

Conséquence directe : `intelligence/spof_and_sizing.py:35,103` (qui importait
`from dashboard.render import _positions`) pourra importer depuis ici → retire
2 entrées du whitelist legacy intelligence/→dashboard/ (ratchet decreasing-only
cf tests/test_no_shared_dashboard_import.py).

MIGRATION 09/06 (Phase Lane 2 #1) — directive Olivier (préservée) :
  Le builder UNIQUE de positions doit lire le seam `book.value_eur` (Datum
  canonique via prices.get + prices.fx live). Avant : weight = qty *
  current_price_eur (cache DB). Maintenant : weight = view.value_eur_datum.
  Trois panneaux deviennent cohérents d'un coup avec ce seul commit.

Test invariant somme-parties (`tests/test_aggregate_sum_equals_parts.py`)
verrouille la cohérence `Σ p["weight"] == Σ view.value_eur`.

Fallback BookLine.weight_market_eur si view manquante (position sans thèse
active OU view degraded fail-closed). Documente le degraded au moment de la
migration.

Shape backward-compat (inchangée vs avant) :
    ticker (str) · weight (float, EUR market value) · avg_cost · wrapper
    · qty · current_price_eur · cost_basis_eur
    + M1 typed columns (last_price_native, last_price_currency, price_asof,
      fx_rate_to_eur, fx_asof) -- TODO migration : ces colonnes legacy
      deviennent obsolètes une fois consumers migrés vers view.* direct.
"""
from __future__ import annotations


def build_positions_view(views: dict) -> list[dict]:
    """Builder unique consommé par les 3 panneaux _concentration, _cluster_health,
    _risk_watch_panel + intelligence/spof_and_sizing.

    Cure #120 étape 5 (12/06) — SINGLE-SOURCE ENFORCEMENT : `views` est requis,
    plus de fallback intérieur. Le caller DOIT tirer `get_all_positions_views()`
    UNE FOIS en amont et passer le dict. Empêche le drift double-source
    silencieux (deux callers tiraient le seam séparément → caches yfinance
    désynchronisés → poids divergents pour la même ligne).

    Passer `{}` (dict vide) reste explicite et autorisé (= aucune view, fallback
    BookLine.weight_market_eur pour toutes les lignes). Ce qui est BANNI :
    laisser le builder décider lui-même quand tirer le seam.
    """
    try:
        from shared import book as _bk
    except Exception:
        return []

    out = []
    for ln in _bk.get_held_lines():
        cost_basis = (ln.qty or 0) * (ln.avg_cost_eur or 0)
        # weight depuis le seam canonical (book.value_eur via prices.get/fx live).
        # Fallback BookLine si view absente (thèse non-active / view degraded).
        v = views.get(ln.ticker) if views else None
        if v is not None and v.value_eur_datum is not None:
            _v = v.value_eur_datum.value
            weight = float(_v.amount if hasattr(_v, "amount") else _v)
        else:
            weight = ln.weight_market_eur or 0
        out.append({
            "ticker": ln.ticker,
            "weight": weight,  # MARKET VALUE EUR via seam canonical (book.value_eur)
            "avg_cost": float(ln.avg_cost_eur or 0),
            "wrapper": (ln.wrapper or "CTO").upper(),
            "qty": float(ln.qty or 0),
            "current_price_eur": ln.current_price_eur,
            "cost_basis_eur": cost_basis,
            # M1 typed columns canoniques (Axe 3 / Axe 5).
            "last_price_native": ln.last_price_native,
            "last_price_currency": ln.last_price_currency,
            "price_asof": ln.price_asof,
            "fx_rate_to_eur": ln.fx_rate_to_eur,
            "fx_asof": ln.fx_asof,
        })
    return out


# Alias historique : `_positions` était le nom du builder dans dashboard/render.py
# pendant 6 mois. Cure #120 étape 2 le déplace ici, mais l'alias permet aux
# call-sites legacy (3 panneaux render.py + intelligence/spof_and_sizing) de
# garder leur nom d'import. À supprimer au moment où on renomme partout (cure
# cosmétique non-bloquante).
_positions = build_positions_view
