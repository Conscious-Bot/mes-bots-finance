"""Business invariants on DB state — catch silent data corruption.

These tests query the LIVE DB and assert invariants that should always hold.
Run in CI/pytest. If any invariant fails, real data corruption exists and
needs investigation (not a test bug).

Distinction from test_schema_drift.py:
- test_schema_drift: structural integrity (columns/tables exist as code expects)
- test_invariants_metier (this file): VALUE-level integrity (qty>=0, uniqueness,
  consistency between related columns, monotonic timestamps, range bounds)

Some invariants are "vacuously true" today (e.g. Brier scores ∈ [0,1] when
N=0 resolved). They become non-trivial as data accumulates. Better to ship
them now than retrofit later when violation is already in prod.

If a test fails, the failure message tells you WHICH rows violate.
"""

import sqlite3
from pathlib import Path

import pytest

DB = Path(__file__).resolve().parent.parent / "data" / "bot.db"


@pytest.fixture(scope="module")
def conn():
    if not DB.exists():
        pytest.skip(f"DB not found at {DB}")
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_positions_qty_non_negative(conn):
    """positions.qty must always be >= 0. Negative inventory makes no sense."""
    rows = conn.execute("SELECT id, ticker, qty FROM positions WHERE qty < 0").fetchall()
    assert not rows, f"Negative qty on positions: {[dict(r) for r in rows]}"


def test_positions_no_duplicate_open_ticker(conn):
    """At most ONE open position per ticker. Duplicates = book corruption."""
    rows = conn.execute(
        "SELECT ticker, COUNT(*) AS n FROM positions WHERE status='open' GROUP BY ticker HAVING n > 1"
    ).fetchall()
    assert not rows, f"Duplicate open positions on ticker: {[dict(r) for r in rows]}"


def test_predictions_brier_in_unit_interval(conn):
    """brier_score must be ∈ [0, 1] when not NULL.

    Brier = (forecast_prob - outcome)^2 with outcome ∈ {0, 1} and prob ∈ [0, 1].
    Result mathematically bounded [0, 1]. Outside that range = computation bug.
    Vacuous today (N=0), becomes meaningful post-10/06 batch resolution.
    """
    rows = conn.execute(
        "SELECT id, ticker, brier_score FROM predictions "
        "WHERE brier_score IS NOT NULL AND (brier_score < 0 OR brier_score > 1)"
    ).fetchall()
    assert not rows, f"Brier out of [0,1]: {[dict(r) for r in rows]}"


def test_decisions_return_30d_consistent_with_prices(conn):
    """return_30d_pct must match (price_30d - price_at_decision) / price_at_decision.

    Tolerance: 0.001 (0.1%) — handles float rounding. Outside that = computation
    bug or manual override out of sync.
    Vacuous today (N=0 resolved); will fire after first 30d resolutions.
    """
    rows = conn.execute(
        "SELECT id, ticker, price_at_decision, price_30d, return_30d_pct "
        "FROM decisions WHERE resolved_30d_at IS NOT NULL "
        "AND price_at_decision IS NOT NULL AND price_at_decision > 0 "
        "AND price_30d IS NOT NULL AND return_30d_pct IS NOT NULL"
    ).fetchall()
    violations = []
    for r in rows:
        expected = (r["price_30d"] - r["price_at_decision"]) / r["price_at_decision"]
        actual = r["return_30d_pct"]
        if abs(expected - actual) > 0.001:
            violations.append(
                {
                    "id": r["id"],
                    "ticker": r["ticker"],
                    "expected": expected,
                    "actual": actual,
                }
            )
    assert not violations, f"return_30d_pct inconsistent: {violations}"


def test_decisions_return_90d_consistent_with_prices(conn):
    """Same as 30d but for 90d horizon."""
    rows = conn.execute(
        "SELECT id, ticker, price_at_decision, price_90d, return_90d_pct "
        "FROM decisions WHERE resolved_90d_at IS NOT NULL "
        "AND price_at_decision IS NOT NULL AND price_at_decision > 0 "
        "AND price_90d IS NOT NULL AND return_90d_pct IS NOT NULL"
    ).fetchall()
    violations = []
    for r in rows:
        expected = (r["price_90d"] - r["price_at_decision"]) / r["price_at_decision"]
        actual = r["return_90d_pct"]
        if abs(expected - actual) > 0.001:
            violations.append(
                {
                    "id": r["id"],
                    "ticker": r["ticker"],
                    "expected": expected,
                    "actual": actual,
                }
            )
    assert not violations, f"return_90d_pct inconsistent: {violations}"


def test_position_events_timestamp_monotone_per_position(conn):
    """Within each position_id series, timestamps must be non-decreasing.

    Out-of-order events = either bug in event logging or manual DB tampering.
    Column name: 'timestamp' (NOT 'ts' — corrected from TODO assumption).
    """
    rows = conn.execute("SELECT id, position_id, timestamp FROM position_events ORDER BY position_id, id").fetchall()
    violations = []
    last_ts_by_pos: dict[int, str] = {}
    for r in rows:
        pid, ts = r["position_id"], r["timestamp"]
        if pid in last_ts_by_pos and ts < last_ts_by_pos[pid]:
            violations.append(
                {
                    "event_id": r["id"],
                    "position_id": pid,
                    "ts": ts,
                    "prev_ts": last_ts_by_pos[pid],
                }
            )
        last_ts_by_pos[pid] = ts
    assert not violations, f"Non-monotonic position_events timestamps: {violations}"


def test_theses_active_have_positive_entry_price(conn):
    """Active theses must have entry_price > 0 (or NULL = unset, acceptable).

    A thesis with entry_price=0 or negative is corrupted — can't compute returns.
    NULL is permitted (thesis opened pre-price or as watch).
    """
    rows = conn.execute(
        "SELECT id, ticker, entry_price FROM theses "
        "WHERE status='active' AND entry_price IS NOT NULL AND entry_price <= 0"
    ).fetchall()
    assert not rows, f"Active thesis with non-positive entry_price: {[dict(r) for r in rows]}"
