"""PRESAGE — Passerelle dérivée. UN seul lieu de calcul par métrique.

Soudure du joint ① du diagnostic 29/05 round 4 :
> "La couche derivee n'a pas de passerelle. Chaque vue recalcule
>  poids/asymetrie/P&L dans son coin -> divergence ASML 7.9% vs 5.7%."

Avant : 10 sites dans render.py calculent `pct = w / total * 100` chacun
avec leur propre `total`. 8 sites calculent asymmetry/margin differemment.
Les vues divergent par construction.

Maintenant : `compute_book_view()` calcule TOUT en un point unique.
Les vues lisent BookView / PositionView, ne re-calculent jamais.

Convention par cohérence avec CONVENTIONS §5 (passerelles ressources) :
- storage/llm/prices/notify/config = passerelles ressources externes
- VIEWS = passerelle dérivée interne (calcul portfolio)

Cache module-level : la vue se recalcule une fois par render cycle.
clear_cache() pour les tests / hot reload.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.position import Position

# ─────────────────────── VIEW DATACLASSES ──────────────────────────────────


@dataclass(frozen=True)
class PositionView:
    """Snapshot derive d'une Position, prêt à l'affichage.

    Tous les calculs sont fait au moment de compute_book_view(). Les vues
    consomment cet objet en lecture seule -- aucun recalcul.
    """
    ticker: str
    # Poids
    weight_eur: float            # qty * current_price_eur (market value)
    weight_pct: float            # weight_eur / book.total_market_eur * 100
    cost_basis_eur: float        # qty * avg_cost_eur
    # P&L
    pnl_eur: float               # weight_eur - cost_basis_eur
    pnl_pct: float | None        # pnl_eur / cost_basis_eur * 100
    # Asymetrie thesis
    asymmetry_ratio: float | None     # (target - current) / (current - stop)
    margin_to_stop_pct: float | None  # (current - stop) / current * 100
    margin_to_target_pct: float | None  # (target - current) / current * 100
    frac_on_stop_target_axis: float | None  # (current - stop) / (target - stop) * 100
    # Cible 70k
    target_eur: float | None
    target_pct: float | None
    gap_to_target_eur: float | None  # target_eur - weight_eur


@dataclass(frozen=True)
class BookView:
    """Agregat dérive du book entier. Lu par toutes les vues.

    Single source of truth pour les totaux + per-position views.
    """
    total_market_eur: float
    total_cost_eur: float
    total_pnl_eur: float
    total_pnl_pct: float | None
    n_positions: int
    # Per-ticker views (dict for O(1) lookup)
    by_ticker: dict[str, PositionView] = field(default_factory=dict)
    # Aggregates : sector, theme, macro_factor (drivers), cluster
    # Computed in pass 2 from by_ticker
    by_macro_factor: dict[str, float] = field(default_factory=dict)
    by_theme: dict[str, float] = field(default_factory=dict)
    by_wrapper: dict[str, float] = field(default_factory=dict)

    def weight_pct_of(self, ticker: str) -> float:
        """API stable : poids % par ticker. Une seule définition."""
        v = self.by_ticker.get(ticker)
        return v.weight_pct if v else 0.0

    def view_of(self, ticker: str) -> PositionView | None:
        return self.by_ticker.get(ticker)


# ─────────────────────── BUILDER ───────────────────────────────────────────


_BOOK_VIEW_CACHE: BookView | None = None


def clear_cache() -> None:
    global _BOOK_VIEW_CACHE
    _BOOK_VIEW_CACHE = None


def compute_book_view(*, use_cache: bool = True) -> BookView:
    """Single source of truth pour les métriques dérivées du book.

    Lit les Position canoniques via shared.book.get_canonical_positions()
    -- qui elles-mêmes joignent les 5 sources de vérité (DB + canonical +
    target + theses + axes + meta).

    Tout calcul de dérivé (pct, pnl, asymetrie, margin) passe par ici. Les
    vues lisent BookView.weight_pct_of(ticker), jamais p["weight"] / total.

    Args:
        use_cache: réutilise le snapshot existant si dispo. Mettre à False
                   après une transaction d'écriture (sell/buy).
    """
    global _BOOK_VIEW_CACHE
    if use_cache and _BOOK_VIEW_CACHE is not None:
        return _BOOK_VIEW_CACHE

    from shared import book

    positions = book.get_canonical_positions()
    held = [p for p in positions if p.in_db]

    # Totaux du book (une seule définition)
    total_market = sum(p.weight_market_eur for p in held) or 1.0
    total_cost = sum(p.cost_basis_eur for p in held)
    total_pnl = total_market - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else None

    by_ticker: dict[str, PositionView] = {}
    by_macro: dict[str, float] = {}
    by_theme: dict[str, float] = {}
    by_wrap: dict[str, float] = {}

    for p in held:
        pv = _build_position_view(p, total_market)
        by_ticker[p.ticker] = pv
        # Aggregates
        mf = p.judgments.driver or "Unclassified"
        by_macro[mf] = by_macro.get(mf, 0.0) + pv.weight_eur
        # theme: lu via in_target_70k row (joint dans Position.target_eur en passant)
        # On le récupère depuis canonical perimeter
        # Pour l'aggregate theme, on a besoin du theme de target_allocation.
        # Position ne l'expose pas direct -- a ajouter en V2. Pour l'instant skip.
        wp = p.facts.wrapper or "CTO"
        by_wrap[wp] = by_wrap.get(wp, 0.0) + pv.weight_eur

    view = BookView(
        total_market_eur=round(total_market, 2),
        total_cost_eur=round(total_cost, 2),
        total_pnl_eur=round(total_pnl, 2),
        total_pnl_pct=round(total_pnl_pct, 2) if total_pnl_pct is not None else None,
        n_positions=len(held),
        by_ticker=by_ticker,
        by_macro_factor={k: round(v, 2) for k, v in by_macro.items()},
        by_theme=by_theme,  # populated when Position exposes theme
        by_wrapper={k: round(v, 2) for k, v in by_wrap.items()},
    )
    _BOOK_VIEW_CACHE = view
    return view


def _build_position_view(p: Position, total_market: float) -> PositionView:
    """Calcule TOUS les dérivés pour une position en un seul endroit."""
    weight_eur = p.weight_market_eur
    cost_basis = p.cost_basis_eur
    pnl_eur = weight_eur - cost_basis
    pnl_pct = (pnl_eur / cost_basis * 100) if cost_basis > 0 else None

    # Asymetrie : sur native price si dispo (pas de mix EUR/native)
    cur = p.facts.prix_courant_native or p.facts.prix_courant_eur
    asym = None
    margin_stop = None
    margin_tgt = None
    frac_axis = None
    th = p.judgments.thesis
    if th and cur:
        if th.target_full and th.stop_price:
            up = th.target_full - cur
            down = cur - th.stop_price
            if down > 0:
                # Precision 3 decimales : evite que 0.005 round a 0.00 et viole
                # invariant asym > 0 quand up > 0 et down > 0 (cf ALAB pres cible).
                asym = round(up / down, 3)
            tgt_minus_stop = th.target_full - th.stop_price
            if tgt_minus_stop > 0:
                frac_axis = round(max(0.0, min(100.0, (cur - th.stop_price) / tgt_minus_stop * 100)), 1)
        if th.stop_price:
            margin_stop = round((cur - th.stop_price) / cur * 100, 1)
        if th.target_full:
            margin_tgt = round((th.target_full - cur) / cur * 100, 1)

    # Cible 70k -- target_eur sur Position absent (on lit via book directement)
    # Pour V0 on laisse None ; quand Position exposera target_eur on remplit.
    target_eur = None
    target_pct = None
    gap = None

    return PositionView(
        ticker=p.ticker,
        weight_eur=round(weight_eur, 2),
        weight_pct=round(weight_eur / total_market * 100, 2) if total_market > 0 else 0.0,
        cost_basis_eur=round(cost_basis, 2),
        pnl_eur=round(pnl_eur, 2),
        pnl_pct=round(pnl_pct, 2) if pnl_pct is not None else None,
        asymmetry_ratio=asym,
        margin_to_stop_pct=margin_stop,
        margin_to_target_pct=margin_tgt,
        frac_on_stop_target_axis=frac_axis,
        target_eur=target_eur,
        target_pct=target_pct,
        gap_to_target_eur=gap,
    )


# ─────────────────────── API CONVENIENCE ───────────────────────────────────


def get_position_view(ticker: str) -> PositionView | None:
    """Lookup direct par ticker. La vue est cachée au niveau book."""
    return compute_book_view().view_of(ticker)


def get_total_market_eur() -> float:
    """Une seule définition du total book (market value)."""
    return compute_book_view().total_market_eur
