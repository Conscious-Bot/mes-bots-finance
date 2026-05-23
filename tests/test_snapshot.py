import math

from intelligence.snapshot import aggregate


def test_aggregate_basic():
    pos = [{"ticker": "A", "qty": 10, "avg_cost": 100.0}, {"ticker": "B", "qty": 5, "avg_cost": 200.0}]
    snap = aggregate(pos, {"A": 120.0, "B": 200.0}, prev_hwm=0.0)
    assert snap["total_value_eur"] == 2200.0
    assert snap["total_cost_eur"] == 2000.0
    assert snap["pnl_eur"] == 200.0 and snap["pnl_pct"] == 10.0
    assert snap["n_positions"] == 2 and snap["n_priced"] == 2


def test_aggregate_unpriced_excluded():
    pos = [{"ticker": "A", "qty": 10, "avg_cost": 100.0}, {"ticker": "B", "qty": 5, "avg_cost": 200.0}]
    snap = aggregate(pos, {"A": 110.0, "B": None}, prev_hwm=0.0)
    assert snap["n_priced"] == 1
    assert snap["total_value_eur"] == 1100.0 and snap["total_cost_eur"] == 1000.0
    assert snap["detail_json"]["B"]["value"] is None


def test_aggregate_nan_excluded():
    pos = [{"ticker": "A", "qty": 10, "avg_cost": 100.0}, {"ticker": "B", "qty": 5, "avg_cost": 200.0}]
    snap = aggregate(pos, {"A": 110.0, "B": float("nan")}, prev_hwm=0.0)
    assert snap["n_priced"] == 1
    assert snap["total_value_eur"] == 1100.0
    assert math.isfinite(snap["total_value_eur"]) and math.isfinite(snap["pnl_pct"])
    assert snap["detail_json"]["B"]["value"] is None


def test_aggregate_no_price_none():
    assert aggregate([{"ticker": "A", "qty": 1, "avg_cost": 100.0}], {"A": None}, 0.0) is None


def test_hwm_monotonic_and_drawdown():
    pos = [{"ticker": "A", "qty": 1, "avg_cost": 100.0}]
    up = aggregate(pos, {"A": 1100.0}, prev_hwm=1000.0)
    assert up["hwm_value_eur"] == 1100.0 and up["drawdown_pct"] == 0.0
    down = aggregate(pos, {"A": 900.0}, prev_hwm=1000.0)
    assert down["hwm_value_eur"] == 1000.0
    assert round(down["drawdown_pct"], 1) == -10.0
