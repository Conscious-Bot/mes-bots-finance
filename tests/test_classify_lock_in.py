"""Tests classify_lock_in (Surface 2 lock_in spec finale 02/06/2026).

5 gates testes :
  1. Status these == 'active'
  2. Gain realise > 0
  3. Gain < 50% cible_conviction (axe timing)
  4. Magnitude vendue >= seuil degressif (axe exit-vs-trim)
  5. Garde over-cap (exclus si rightsize, ADR 009)

Property-based via Hypothesis sur classifier + chaque garde + coherence
des dimensions retournees.
"""
from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from intelligence.lock_in_detector import (
    MAGNITUDE_THRESHOLD_BY_CONV,
    TARGET_PNL_BY_CONV,
    classify_lock_in,
)


def _make_thesis(
    conviction: int = 5,
    status: str = "active",
    entry_price: float = 100.0,
    target_full: float = 170.0,
    opened_at: str = "2026-05-01T00:00:00+00:00",
) -> dict:
    return {
        "conviction": conviction,
        "status": status,
        "target_partial": entry_price * 1.3,
        "target_full": target_full,
        "opened_at": opened_at,
        "entry_price": entry_price,
    }


_SENTINEL = object()


def _make_sale(
    ticker: str = "NVDA",
    qty_sold: float = 50,
    sold_price: float = 110,  # +10% pnl
    qty_before: float = 100,
    avg_cost: float = 100,
    thesis=_SENTINEL,
    overcap: str = "dormant",
) -> dict:
    return {
        "ticker": ticker,
        "qty_sold": qty_sold,
        "sold_price_eur": sold_price,
        "qty_before": qty_before,
        "avg_cost": avg_cost,
        "thesis": _make_thesis() if thesis is _SENTINEL else thesis,
        "overcap_state": overcap,
    }


# ─── Pre-conditions arithmetiques ─────────────────────────────────────────


def test_empty_ticker_returns_none():
    assert classify_lock_in(_make_sale(ticker="")) is None


def test_qty_sold_zero_returns_none():
    assert classify_lock_in(_make_sale(qty_sold=0)) is None


def test_qty_sold_above_qty_before_returns_none():
    """Bug caller : on ne peut pas vendre plus qu'on n'a."""
    assert classify_lock_in(_make_sale(qty_sold=150, qty_before=100)) is None


def test_avg_cost_zero_returns_none():
    assert classify_lock_in(_make_sale(avg_cost=0)) is None


def test_sold_price_zero_returns_none():
    assert classify_lock_in(_make_sale(sold_price=0)) is None


# ─── Gate 1 : these active ────────────────────────────────────────────────


def test_no_thesis_returns_none():
    assert classify_lock_in(_make_sale(thesis=None)) is None


def test_thesis_invalidated_returns_none():
    sale = _make_sale(thesis=_make_thesis(status="invalidated"))
    assert classify_lock_in(sale) is None


def test_thesis_closed_returns_none():
    sale = _make_sale(thesis=_make_thesis(status="closed"))
    assert classify_lock_in(sale) is None


def test_invalid_conviction_returns_none():
    """Conviction None ou hors {1..5} -> ignored."""
    sale = _make_sale(thesis=_make_thesis(conviction=99))  # type: ignore[arg-type]
    assert classify_lock_in(sale) is None


# ─── Gate 2 : winner only (gain > 0) ──────────────────────────────────────


def test_loss_position_returns_none():
    """sold_price < avg_cost (perte) -> pas un winner."""
    sale = _make_sale(sold_price=90, avg_cost=100)  # -10%
    assert classify_lock_in(sale) is None


def test_breakeven_returns_none():
    """sold_price == avg_cost (pnl=0) -> pas un winner."""
    sale = _make_sale(sold_price=100, avg_cost=100)
    assert classify_lock_in(sale) is None


# ─── Gate 3 : pnl < 50% cible_conviction (timing) ─────────────────────────


def test_c5_pnl_above_halfway_returns_none():
    """c5 cible +70%, halfway = +35%. PnL +40% -> these progress OK, pas
    de lock_in (au-dessus de halfway)."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=5),
        sold_price=140, avg_cost=100,  # +40%
    )
    assert classify_lock_in(sale) is None


def test_c5_pnl_at_halfway_exactly_returns_none():
    """Bord superieur du gate timing : pnl == halfway -> pas candidat
    (strict less than)."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=5),
        sold_price=135, avg_cost=100,  # +35% = exact halfway c5
    )
    assert classify_lock_in(sale) is None


def test_c3_pnl_below_halfway_is_candidate():
    """c3 cible +50%, halfway = +25%. PnL +15% -> dessous halfway,
    candidat (si autres gates OK)."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=3),
        sold_price=115, avg_cost=100,
        qty_sold=60, qty_before=100,  # 60% >= seuil c3 50%
    )
    result = classify_lock_in(sale)
    assert result is not None
    assert result["reason"] == "candidate"


# ─── Gate 4 : magnitude vendue >= seuil ───────────────────────────────────


def test_c1_always_ignored_via_magnitude():
    """c1 seuil = None -> tout vendu sur c1 est ignore (pas un signal)."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=1),
        sold_price=110, avg_cost=100,
        qty_sold=100, qty_before=100,  # 100% vendu
    )
    assert classify_lock_in(sale) is None


def test_c5_small_trim_returns_none():
    """c5 seuil 25%. Vendre 20% -> trim, pas exit."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=5),
        sold_price=120, avg_cost=100,
        qty_sold=20, qty_before=100,  # 20% < 25% seuil c5
    )
    assert classify_lock_in(sale) is None


def test_c5_exit_at_threshold_is_candidate():
    """c5 seuil 25%. Vendre exactement 25% -> candidat."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=5),
        sold_price=120, avg_cost=100,  # +20% < 35% halfway
        qty_sold=25, qty_before=100,
    )
    result = classify_lock_in(sale)
    assert result is not None
    assert result["magnitude_pct"] == 0.25


def test_c2_trim_below_threshold_returns_none():
    """c2 seuil 75%. Vendre 50% -> trim sous seuil."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=2),
        sold_price=110, avg_cost=100,  # +10% < 20% halfway c2
        qty_sold=50, qty_before=100,
    )
    assert classify_lock_in(sale) is None


def test_c2_exit_above_threshold_is_candidate():
    """c2 seuil 75%. Vendre 80% -> exit -> candidat.
    PnL 16% pour passer gate 2b floor 15% (spec CLAUDE.md lock_in v2.c.6)."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=2),
        sold_price=116, avg_cost=100,
        qty_sold=80, qty_before=100,
    )
    result = classify_lock_in(sale)
    assert result is not None


# ─── Garde 5 : over-cap rightsize ─────────────────────────────────────────


def test_overcap_state_over_excludes_candidate():
    """Ligne over-cap -> vente = rightsize, pas lock_in (ADR 009)."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=5),
        sold_price=120, avg_cost=100,
        qty_sold=30, qty_before=100,
        overcap="over",
    )
    assert classify_lock_in(sale) is None


def test_overcap_dormant_does_not_exclude():
    """Pas over-cap -> garde 5 passe."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=5),
        sold_price=120, avg_cost=100,
        qty_sold=30, qty_before=100,
        overcap="dormant",
    )
    result = classify_lock_in(sale)
    assert result is not None


def test_overcap_unknown_does_not_exclude():
    """'unknown' -> on suppose pas over (conservateur sur faux-positif)."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=5),
        sold_price=120, avg_cost=100,
        qty_sold=30, qty_before=100,
        overcap="unknown",
    )
    result = classify_lock_in(sale)
    assert result is not None


# ─── Dimensions enrichies dans candidate ──────────────────────────────────


def test_candidate_dimensions_complete():
    """Verifie que toutes les dimensions sont presentes + correctes."""
    sale = _make_sale(
        thesis=_make_thesis(conviction=4, entry_price=100.0, target_full=160.0),
        sold_price=125, avg_cost=100,  # +25% (halfway c4 = 30%)
        qty_sold=40, qty_before=100,  # 40% >= 35% seuil c4
    )
    result = classify_lock_in(sale)
    assert result is not None
    assert result["pnl_pct"] == 0.25
    assert result["target_pnl_pct"] == 0.60
    assert result["target_halfway"] == 0.30
    assert result["magnitude_pct"] == 0.40
    assert result["magnitude_threshold"] == 0.35
    assert result["conviction"] == 4
    dims = result["dimensions"]
    assert dims["pnl_pct_at_sell"] == 0.25
    assert dims["conviction_at_sell"] == 4
    # pnl_progress = 0.25 / 0.60 = 0.4167
    assert abs(dims["pnl_pct_progress"] - 0.4167) < 0.001


# ─── Property-based : invariants generaux ─────────────────────────────────


@given(
    conviction=st.integers(min_value=1, max_value=5),
    pnl_pct=st.floats(min_value=-0.5, max_value=2.0, allow_nan=False),
    magnitude=st.floats(min_value=0.01, max_value=1.0, allow_nan=False),
    overcap=st.sampled_from(["over", "dormant", "unknown"]),
)
def test_classify_no_crash_arbitrary_inputs(conviction, pnl_pct, magnitude, overcap):
    """Property : aucune crash sur entries arbitraires dans la plage realiste."""
    avg_cost = 100.0
    sold_price = avg_cost * (1 + pnl_pct)
    qty_before = 100.0
    qty_sold = qty_before * magnitude
    if sold_price <= 0:
        return  # skip edge case oblige par les invariants pre-condition
    sale = _make_sale(
        thesis=_make_thesis(conviction=conviction),
        sold_price=sold_price, avg_cost=avg_cost,
        qty_sold=qty_sold, qty_before=qty_before,
        overcap=overcap,
    )
    result = classify_lock_in(sale)
    # Soit None, soit dict candidate avec reason='candidate'
    assert result is None or result["reason"] == "candidate"


@given(conviction=st.integers(min_value=1, max_value=5))
def test_candidate_implies_pnl_below_halfway(conviction):
    """Property : si candidate retourne quelque chose, pnl_pct < target_halfway."""
    target = TARGET_PNL_BY_CONV[conviction]
    halfway = 0.5 * target
    # Construit un sale qui passe tous les gates SAUF qu'on teste gate 3
    mag_thresh = MAGNITUDE_THRESHOLD_BY_CONV[conviction]
    if mag_thresh is None:
        return  # c1 ignored, gate 4 bloque toujours
    # PnL juste sous halfway
    pnl_pct = halfway - 0.01
    if pnl_pct <= 0:
        return  # gate 2 bloque
    sale = _make_sale(
        thesis=_make_thesis(conviction=conviction),
        sold_price=100 * (1 + pnl_pct), avg_cost=100,
        qty_sold=100 * mag_thresh, qty_before=100,
        overcap="dormant",
    )
    result = classify_lock_in(sale)
    if result is not None:
        assert result["pnl_pct"] < halfway


@given(conviction=st.integers(min_value=2, max_value=5))
def test_candidate_implies_magnitude_above_threshold(conviction):
    """Property : si candidate retourne quelque chose, magnitude >= threshold."""
    mag_thresh = MAGNITUDE_THRESHOLD_BY_CONV[conviction]
    if mag_thresh is None:
        return
    target = TARGET_PNL_BY_CONV[conviction]
    halfway = 0.5 * target
    pnl_pct = max(0.01, halfway - 0.05)
    sale = _make_sale(
        thesis=_make_thesis(conviction=conviction),
        sold_price=100 * (1 + pnl_pct), avg_cost=100,
        qty_sold=100 * mag_thresh, qty_before=100,
        overcap="dormant",
    )
    result = classify_lock_in(sale)
    if result is not None:
        assert result["magnitude_pct"] >= mag_thresh


def test_overcap_over_never_yields_candidate():
    """Property garde 5 : peu importe les autres conditions, over -> None."""
    for conv in (2, 3, 4, 5):
        mag_thresh = MAGNITUDE_THRESHOLD_BY_CONV[conv]
        if mag_thresh is None:
            continue
        sale = _make_sale(
            thesis=_make_thesis(conviction=conv),
            sold_price=110, avg_cost=100,  # +10% gain
            qty_sold=100 * mag_thresh, qty_before=100,
            overcap="over",
        )
        assert classify_lock_in(sale) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
