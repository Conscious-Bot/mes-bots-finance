"""W0 SPEC_GAUGE_PRICE_AXIS tests — axe-prix EUR, 5 repères, money-invariant.

Cf SPEC_GAUGE_PRICE_AXIS.md §7 tests verrouillants.

Le test critique : SK Hynix (cur EUR > target EUR via PMP roulant ≈ target)
→ ticks cost et target distincts ET visibles, dot vert au-delà du target.
CCJ idem mais sans beyond.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def render_axis():
    from dashboard.render import _position_axis_price
    return _position_axis_price


def test_skhynix_target_not_collapsed_to_zero(render_axis):
    """SK Hynix : cost_eur ≈ target_eur (PMP rattrapé) MAIS axe-prix les sépare.

    Valeurs réelles 09/06 :
      cost_eur=1060.53 (PMP fee-inclusive)
      entry_eur=856.80 (entry × fx_now)
      target_eur=1053.86 (target × fx_now)  → 0.7% en-dessous de cost_eur
      stop_eur=728.28
      cur_eur=1254.80  → AU-DESSUS du target (badge "beyond" attendu)
    """
    html = render_axis(
        stop_eur=728.28, cost_eur=1060.53, entry_eur=856.80,
        target_eur=1053.86, cur_eur=1254.80,
        pnl_pct_cost=18.3, perf_pct_entry=46.45,
    )
    assert html, "expected non-empty HTML"
    # Le tick cost et target ont des positions visuelles DISTINCTES
    # (vérif indirect : les deux apparaissent dans le HTML avec leurs labels)
    assert 'title="cost"' in html
    assert 'title="target"' in html
    # Dot vert "acc" car cur > target
    assert 'tbar-dot acc' in html
    # Beyond visible dans tooltip
    assert 'beyond +19.1%' in html


def test_ccj_target_close_to_cost_both_visible(render_axis):
    """CCJ : target_eur (95.54) très proche de cost_eur (94.98) -- 0.6%.
    Sur axe-prix, les 2 ticks restent distincts (pas effondrés sur un même 0).
    """
    html = render_axis(
        stop_eur=62.14, cost_eur=94.98, entry_eur=77.67,
        target_eur=95.54, cur_eur=91.12,
        pnl_pct_cost=-4.06, perf_pct_entry=17.31,
    )
    assert html
    assert 'title="cost"' in html
    assert 'title="target"' in html
    # cur entre cost et target, ni bear ni acc
    assert 'tbar-dot acc' not in html
    assert 'tbar-dot bear' not in html


def test_dot_bear_when_below_stop(render_axis):
    """cur < stop → dot rouge."""
    html = render_axis(
        stop_eur=100.0, cost_eur=110.0, entry_eur=105.0,
        target_eur=130.0, cur_eur=95.0,
    )
    assert 'tbar-dot bear' in html


def test_dot_acc_when_above_target(render_axis):
    """cur > target → dot vert."""
    html = render_axis(
        stop_eur=100.0, cost_eur=110.0, entry_eur=105.0,
        target_eur=130.0, cur_eur=140.0,
    )
    assert 'tbar-dot acc' in html


def test_fallback_no_target_still_renders(render_axis):
    """Pas de target → gauge rendue avec stop/cost/entry/cur."""
    html = render_axis(
        stop_eur=100.0, cost_eur=110.0, entry_eur=105.0,
        target_eur=None, cur_eur=120.0,
    )
    assert html  # rendered
    assert 'title="target"' not in html
    assert 'title="cost"' in html


def test_returns_empty_when_insufficient_refs(render_axis):
    """< 2 repères → return ""."""
    html = render_axis(
        stop_eur=None, cost_eur=None, entry_eur=100.0,
        target_eur=None, cur_eur=110.0,
    )
    assert html == ""


def test_returns_empty_when_no_cur(render_axis):
    """Pas de current → return ""."""
    html = render_axis(
        stop_eur=100.0, cost_eur=110.0, entry_eur=105.0,
        target_eur=130.0, cur_eur=None,
    )
    assert html == ""


def test_tooltip_has_both_frames(render_axis):
    """Tooltip honore les 2 frames (P&L cost + perf entry + beyond)."""
    html = render_axis(
        stop_eur=100.0, cost_eur=110.0, entry_eur=105.0,
        target_eur=130.0, cur_eur=145.0,
        pnl_pct_cost=31.8, perf_pct_entry=38.1,
    )
    assert "P&amp;L +31.8% depuis coût" in html or "P&L +31.8% depuis coût" in html
    assert "thèse +38.1% depuis entry" in html
    assert "beyond" in html


def test_axis_data_attrs_eur(render_axis):
    """data-axmin / data-axmax exposés en EUR pour hover JS."""
    html = render_axis(
        stop_eur=100.0, cost_eur=110.0, entry_eur=105.0,
        target_eur=130.0, cur_eur=120.0,
    )
    # Padding 5% appliqué : p_min ≈ 100 - 1.5 = 98.5, p_max ≈ 130 + 1.5 = 131.5
    assert 'data-axmin=' in html
    assert 'data-axmax=' in html
