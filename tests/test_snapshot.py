import math

import pytest

from intelligence import snapshot as snap_mod
from intelligence.snapshot import MIN_COST_COVERAGE, aggregate


def test_aggregate_basic():
    pos = [{"ticker": "A", "qty": 10, "avg_cost": 100.0}, {"ticker": "B", "qty": 5, "avg_cost": 200.0}]
    snap = aggregate(pos, {"A": 120.0, "B": 200.0}, prev_hwm=0.0)
    assert snap["total_value_eur"] == 2200.0
    assert snap["total_cost_eur"] == 2000.0
    assert snap["pnl_eur"] == 200.0 and snap["pnl_pct"] == 10.0
    assert snap["n_positions"] == 2 and snap["n_priced"] == 2


def test_aggregate_small_unpriced_tolerated():
    """Une petite ligne sans prix (1% du coût) reste tolérée : snapshot écrit,
    biais borné, visible via n_priced < n_positions."""
    pos = [
        {"ticker": "A", "qty": 10, "avg_cost": 500.0},   # cost 5000
        {"ticker": "B", "qty": 10, "avg_cost": 490.0},   # cost 4900
        {"ticker": "C", "qty": 1, "avg_cost": 100.0},    # cost 100 = 1%
    ]
    snap = aggregate(pos, {"A": 500.0, "B": 490.0, "C": None}, prev_hwm=0.0)
    assert snap is not None
    assert snap["n_priced"] == 2 and snap["n_positions"] == 3
    assert snap["detail_json"]["C"]["value"] is None


def test_aggregate_partial_refused():
    """Classe « agrégat partiel ≠ total » (04/07/2026) : 50% du coût sans prix
    → PAS de snapshot (None), plutôt qu'un total tronqué comparé au HWM complet
    qui fabriquerait un faux drawdown (faux gel Digue 1)."""
    pos = [{"ticker": "A", "qty": 10, "avg_cost": 100.0}, {"ticker": "B", "qty": 5, "avg_cost": 200.0}]
    assert aggregate(pos, {"A": 110.0, "B": None}, prev_hwm=0.0) is None


def test_aggregate_coverage_boundary():
    """Boundary explicite : couverture == MIN_COST_COVERAGE passe, juste dessous refuse."""
    # A pricée = 98% du coût, B unpriced = 2% → coverage exactement 0.98 → écrit.
    pos = [
        {"ticker": "A", "qty": 1, "avg_cost": 9800.0},
        {"ticker": "B", "qty": 1, "avg_cost": 200.0},
    ]
    at_threshold = aggregate(pos, {"A": 9800.0, "B": None}, prev_hwm=0.0)
    assert at_threshold is not None
    assert math.isclose(9800.0 / 10000.0, MIN_COST_COVERAGE)
    # B unpriced = 2.5% → coverage 0.975 < 0.98 → refusé.
    pos_below = [
        {"ticker": "A", "qty": 1, "avg_cost": 9750.0},
        {"ticker": "B", "qty": 1, "avg_cost": 250.0},
    ]
    assert aggregate(pos_below, {"A": 9750.0, "B": None}, prev_hwm=0.0) is None


def test_aggregate_nan_counts_as_unpriced():
    """NaN = pas un prix : petite ligne NaN tolérée (comme None), grosse refusée."""
    small = [
        {"ticker": "A", "qty": 10, "avg_cost": 990.0},
        {"ticker": "B", "qty": 1, "avg_cost": 100.0},
    ]
    snap = aggregate(small, {"A": 1000.0, "B": float("nan")}, prev_hwm=0.0)
    assert snap is not None
    assert math.isfinite(snap["total_value_eur"]) and math.isfinite(snap["pnl_pct"])
    assert snap["detail_json"]["B"]["value"] is None
    big = [{"ticker": "A", "qty": 1, "avg_cost": 100.0}, {"ticker": "B", "qty": 1, "avg_cost": 100.0}]
    assert aggregate(big, {"A": 110.0, "B": float("nan")}, prev_hwm=0.0) is None


def test_aggregate_no_price_none():
    assert aggregate([{"ticker": "A", "qty": 1, "avg_cost": 100.0}], {"A": None}, 0.0) is None


def test_hwm_monotonic_and_drawdown():
    pos = [{"ticker": "A", "qty": 1, "avg_cost": 100.0}]
    up = aggregate(pos, {"A": 1100.0}, prev_hwm=1000.0)
    assert up["hwm_value_eur"] == 1100.0 and up["drawdown_pct"] == 0.0
    down = aggregate(pos, {"A": 900.0}, prev_hwm=1000.0)
    assert down["hwm_value_eur"] == 1000.0
    assert round(down["drawdown_pct"], 1) == -10.0


def test_aggregate_zero_cost_basis_no_bypass():
    """Bypass fermé (revue 04/07) : cost basis inconnu (cost_all=0) → impossible
    de borner le biais → refuse dès qu'une ligne manque. Complet → écrit."""
    pos = [{"ticker": "A", "qty": 10, "avg_cost": 0}, {"ticker": "B", "qty": 5, "avg_cost": 0}]
    assert aggregate(pos, {"A": 110.0, "B": None}, prev_hwm=0.0) is None
    full = aggregate(pos, {"A": 110.0, "B": 50.0}, prev_hwm=0.0)
    assert full is not None and full["n_priced"] == 2


# ---------- compute_snapshot / daily_snapshot_job : le refus doit être VISIBLE ----------


def _wire(monkeypatch, positions, prices_map, upserts):
    monkeypatch.setattr(snap_mod.storage, "get_open_positions", lambda: positions)
    monkeypatch.setattr(snap_mod.storage, "latest_snapshot_hwm", lambda: 60000.0)
    monkeypatch.setattr(
        snap_mod.storage, "upsert_portfolio_snapshot", lambda s: upserts.append(s)
    )
    monkeypatch.setattr(
        snap_mod, "get_current_price_in_eur", lambda t: prices_map.get(t)
    )


def test_compute_snapshot_raises_on_low_coverage(monkeypatch):
    """Couverture insuffisante → RuntimeError listant les manquants (visible via
    _safe_run → scheduler_runs FAIL), PAS un skip silencieux."""
    upserts = []
    pos = [{"ticker": "A", "qty": 10, "avg_cost": 100.0}, {"ticker": "B", "qty": 5, "avg_cost": 200.0}]
    _wire(monkeypatch, pos, {"A": 110.0, "B": None}, upserts)
    with pytest.raises(RuntimeError, match="REFUSÉ") as exc:
        snap_mod.compute_snapshot()
    assert "B" in str(exc.value)
    assert upserts == []


def test_compute_snapshot_empty_book_silent(monkeypatch):
    """Book vide = silence légitime (None), pas un raise."""
    upserts = []
    _wire(monkeypatch, [], {}, upserts)
    assert snap_mod.compute_snapshot() is None
    assert upserts == []


def test_daily_snapshot_job_propagates_refusal(monkeypatch):
    """daily_snapshot_job NE catch PAS le refus (le raise doit remonter à
    _safe_run pour être journalisé fail) et n'écrit rien."""
    upserts = []
    pos = [{"ticker": "A", "qty": 1, "avg_cost": 100.0}, {"ticker": "B", "qty": 1, "avg_cost": 100.0}]
    _wire(monkeypatch, pos, {"A": 110.0, "B": None}, upserts)
    with pytest.raises(RuntimeError):
        snap_mod.daily_snapshot_job()
    assert upserts == []


def test_daily_snapshot_job_writes_when_complete(monkeypatch):
    upserts = []
    pos = [{"ticker": "A", "qty": 10, "avg_cost": 100.0}]
    _wire(monkeypatch, pos, {"A": 120.0}, upserts)
    snap_mod.daily_snapshot_job()
    assert len(upserts) == 1
    assert upserts[0]["total_value_eur"] == 1200.0
    assert upserts[0]["n_priced"] == 1
