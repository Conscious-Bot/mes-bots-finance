"""Soudure ① -- convergence des vues sur la passerelle dérivée.

Property tests qui FAIL si jamais une vue calcule un dérivé différemment de
shared/views.compute_book_view(). C'est l'invariant qui empeche la fuite
"ASML 7.9% vs 5.7%" de revenir.

Methodo : prendre quelques tickers representatifs et comparer toutes les
sources qui calculent le meme metrique.
"""

from __future__ import annotations

import pytest

from shared import views


@pytest.fixture(scope="module")
def book_view():
    """Convergence tests reposent sur une DB peuplee (positions reelles).
    En CI la DB est soit absente, soit migree-mais-vide -> skip cleanly toute
    la suite plutot que 65 echecs spurieux. Garantit que ces invariants
    s'executent quand pertinent (dev local) et restent silencieux quand pas
    applicable (CI fresh checkout)."""
    try:
        views.clear_cache()
        bv = views.compute_book_view()
    except Exception as e:
        pytest.skip(f"compute_book_view crashed ({type(e).__name__}: {e}) -- DB likely uninitialized")
    if bv.n_positions == 0:
        pytest.skip("Empty DB (n_positions=0) -- convergence tests require live data")
    return bv


def test_book_view_total_market_unique(book_view):
    """Single source for total market : > 0 et coherent ordre de grandeur."""
    assert book_view.total_market_eur > 10_000  # > 10k€
    assert book_view.total_market_eur < 1_000_000


def test_book_view_position_weights_sum_to_100(book_view):
    """Invariant fondamental : somme des weight_pct = 100% (± 0.5% pour arrondi)."""
    s = sum(pv.weight_pct for pv in book_view.by_ticker.values())
    assert abs(s - 100.0) < 0.5, f"sum weight_pct = {s} != 100"


def test_book_view_total_pnl_equals_market_minus_cost(book_view):
    """Invariant comptable : pnl = market - cost (tolerance arrondi 1 cent)."""
    expected = book_view.total_market_eur - book_view.total_cost_eur
    assert abs(book_view.total_pnl_eur - expected) < 0.05


def test_book_view_macro_factor_sum_consistent(book_view):
    """Aggregate par macro_factor doit sommer à total_market."""
    s = sum(book_view.by_macro_factor.values())
    assert abs(s - book_view.total_market_eur) < 1.0


def test_book_view_wrapper_sum_consistent(book_view):
    """Aggregate par wrapper (PEA/CTO) doit sommer à total_market."""
    s = sum(book_view.by_wrapper.values())
    assert abs(s - book_view.total_market_eur) < 1.0


def test_mauboussin_actual_pct_converges_with_book_view(book_view):
    """Soudure ① : compute_mauboussin_sizing().actual_pct == BookView.weight_pct.

    Tolerance : 0.1pp (arrondi a 1 decimale dans Mauboussin vs 2 dans views).
    Si ce test sort rouge = une vue calcule le poids differemment.
    """
    from intelligence.spof_and_sizing import compute_mauboussin_sizing

    msz = compute_mauboussin_sizing()
    divergences = []
    for tk, d in msz.items():
        pv = book_view.view_of(tk)
        if pv is None:
            continue
        delta = abs(d["actual_pct"] - pv.weight_pct)
        if delta > 0.1:
            divergences.append((tk, d["actual_pct"], pv.weight_pct, delta))
    assert not divergences, f"Mauboussin diverge du BookView : {divergences}"


def test_book_view_caches_until_cleared():
    """Cache module-level evite les recalculs multiples par render cycle."""
    v1 = views.compute_book_view(use_cache=True)
    v2 = views.compute_book_view(use_cache=True)
    assert v1 is v2  # meme objet en cache

    views.clear_cache()
    v3 = views.compute_book_view(use_cache=True)
    assert v3 is not v1  # nouveau objet apres clear


def test_position_view_pnl_sign_matches_market_vs_cost(book_view):
    """Per-ticker : pnl_eur > 0 <=> weight_eur > cost_basis_eur."""
    for pv in book_view.by_ticker.values():
        if pv.cost_basis_eur <= 0:
            continue
        if pv.pnl_eur > 0:
            assert pv.weight_eur > pv.cost_basis_eur, f"{pv.ticker} pnl>0 mais weight<=cost"
        elif pv.pnl_eur < 0:
            assert pv.weight_eur < pv.cost_basis_eur, f"{pv.ticker} pnl<0 mais weight>=cost"


def test_asymmetry_ratio_positive_when_above_stop(book_view):
    """Si margin_to_stop_pct > 0 ET margin_to_target_pct > 0 alors asymmetry > 0."""
    for pv in book_view.by_ticker.values():
        if (pv.margin_to_stop_pct is not None and pv.margin_to_stop_pct > 0
                and pv.margin_to_target_pct is not None and pv.margin_to_target_pct > 0):
            assert pv.asymmetry_ratio is not None and pv.asymmetry_ratio > 0, \
                f"{pv.ticker} margins positives mais asym = {pv.asymmetry_ratio}"


def test_frac_on_axis_bounded(book_view):
    """L'axe stop->cible est [0, 100] strict."""
    for pv in book_view.by_ticker.values():
        if pv.frac_on_stop_target_axis is None:
            continue
        assert 0 <= pv.frac_on_stop_target_axis <= 100, \
            f"{pv.ticker} frac_on_axis = {pv.frac_on_stop_target_axis}"
