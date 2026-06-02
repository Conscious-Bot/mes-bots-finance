"""Tests bias_track_record : aggregation cumul delta_signed_eur par bias."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from intelligence.bias_track_record import (
    compute_all_bias_track_records,
    compute_bias_track_record,
)


def _add_event(
    db: Path, bias: str = "lock_in",
    ticker: str = "NVDA",
    status: str = "resolved",
    delta_signed_eur: float | None = -250.0,
    action: str = "acted_on_bias",
    days_ago: int = 30,
) -> int:
    cx = sqlite3.connect(db)
    created_at = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    resolved_at = (datetime.now(UTC) - timedelta(days=max(0, days_ago - 30))).isoformat()
    resolve_at_fut = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    decision = json.dumps({"action": action, "ref": "test"})
    cf = json.dumps({"anchor_price_eur": 100.0, "initial_qty": 50.0,
                     "discipline_expected_delta": 0.0,
                     "counterfactual_method": "cash_idle", "horizon_days": 90})
    res = None
    if status == "resolved" and delta_signed_eur is not None:
        res = json.dumps({
            "delta_signed_eur": delta_signed_eur,
            "horizon_days": 90,
            "anchor_price_eur": 100.0,
            "resolved_at": resolved_at,
        }, sort_keys=True)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, "
        "decision_json, counterfactual_json, resolution_json, status, "
        "source, horizon_days, resolve_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'auto_detected', 90, ?)",
        (created_at, ticker, bias, action, decision, cf, res, status, resolve_at_fut),
    )
    eid = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.commit()
    cx.close()
    return eid


# ─── Empty DB ─────────────────────────────────────────────────────────────


def test_empty_db_returns_insufficient_data(migrated_db):
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_bias_track_record(cx, "lock_in")
        assert rec["n_resolved"] == 0
        assert rec["posture"] == "INSUFFICIENT_DATA"
        assert rec["total_delta_signed_eur"] == 0.0
        assert rec["latest_resolved"] is None
    finally:
        cx.close()


# ─── Cumul deltas ─────────────────────────────────────────────────────────


def test_cumul_negative_deltas_alert(migrated_db):
    """5 events lock_in avec delta -200 EUR each = -1000 total -> ALERT."""
    for _ in range(5):
        _add_event(migrated_db, bias="lock_in", delta_signed_eur=-200.0)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_bias_track_record(cx, "lock_in")
        assert rec["n_resolved"] == 5
        assert rec["total_delta_signed_eur"] == -1000.0
        assert rec["avg_delta_eur"] == -200.0
        assert rec["fraction_harmful"] == 1.0
        assert rec["fraction_beneficial"] == 0.0
        assert rec["posture"] == "ALERT"  # < -500 EUR
    finally:
        cx.close()


def test_cumul_positive_deltas_ok(migrated_db):
    """5 events avec delta +300 each = +1500 total -> OK."""
    for _ in range(5):
        _add_event(migrated_db, bias="lock_in", delta_signed_eur=300.0)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_bias_track_record(cx, "lock_in")
        assert rec["total_delta_signed_eur"] == 1500.0
        assert rec["fraction_beneficial"] == 1.0
        assert rec["posture"] == "OK"
    finally:
        cx.close()


def test_mixed_deltas_warn(migrated_db):
    """3 events +100 + 2 events -50 -> +200 total, 60% beneficial -> OK."""
    for _ in range(3):
        _add_event(migrated_db, bias="lock_in", delta_signed_eur=100.0)
    for _ in range(2):
        _add_event(migrated_db, bias="lock_in", delta_signed_eur=-50.0)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_bias_track_record(cx, "lock_in")
        assert rec["total_delta_signed_eur"] == 200.0
        assert rec["fraction_beneficial"] == 0.6
        assert rec["fraction_harmful"] == 0.4
        assert rec["posture"] == "OK"
    finally:
        cx.close()


def test_warn_negative_but_not_alert_floor(migrated_db):
    """3 events delta -100 each = -300 (entre -500 et 0) -> WARN."""
    for _ in range(3):
        _add_event(migrated_db, bias="lock_in", delta_signed_eur=-100.0)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_bias_track_record(cx, "lock_in")
        assert rec["total_delta_signed_eur"] == -300.0
        assert rec["posture"] == "WARN"
    finally:
        cx.close()


# ─── Median + p95 ─────────────────────────────────────────────────────────


def test_median_p95_only_when_n_ge_5(migrated_db):
    """N=4 -> median/p95 None. N=5 -> values."""
    for _ in range(4):
        _add_event(migrated_db, bias="lock_in", delta_signed_eur=-100.0)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_bias_track_record(cx, "lock_in")
        assert rec["median_delta_eur"] is None
        assert rec["p95_delta_eur"] is None

        _add_event(migrated_db, bias="lock_in", delta_signed_eur=500.0)
        rec2 = compute_bias_track_record(cx, "lock_in")
        assert rec2["n_resolved"] == 5
        assert rec2["median_delta_eur"] == -100.0
        assert rec2["p95_delta_eur"] == 500.0
    finally:
        cx.close()


# ─── Status decomposition ────────────────────────────────────────────────


def test_status_decomposition(migrated_db):
    """3 open + 2 resolved + 1 void + 1 missing_data."""
    for _ in range(3):
        _add_event(migrated_db, status="open")
    for _ in range(2):
        _add_event(migrated_db, status="resolved", delta_signed_eur=100.0)
    _add_event(migrated_db, status="void")
    _add_event(migrated_db, status="missing_data")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_bias_track_record(cx, "lock_in")
        assert rec["n_open"] == 3
        assert rec["n_resolved"] == 2
        assert rec["n_void"] == 1
        assert rec["n_missing_data"] == 1
    finally:
        cx.close()


# ─── Latest resolved ──────────────────────────────────────────────────────


def test_latest_resolved_picks_most_recent(migrated_db):
    """Latest = highest id with status=resolved."""
    _add_event(migrated_db, ticker="AAA", delta_signed_eur=-100.0)
    _add_event(migrated_db, ticker="BBB", delta_signed_eur=-50.0)
    last_id = _add_event(migrated_db, ticker="CCC", delta_signed_eur=200.0)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_bias_track_record(cx, "lock_in")
        assert rec["latest_resolved"]["ticker"] == "CCC"
        assert rec["latest_resolved"]["delta_signed_eur"] == 200.0
    finally:
        cx.close()
    assert last_id  # silence unused


# ─── Filtre par bias ──────────────────────────────────────────────────────


def test_other_bias_not_mixed(migrated_db):
    """Events fomo_greed n'apparaissent pas dans lock_in track record."""
    _add_event(migrated_db, bias="lock_in", delta_signed_eur=-100.0)
    _add_event(migrated_db, bias="fomo_greed", delta_signed_eur=500.0)
    _add_event(migrated_db, bias="fomo_greed", delta_signed_eur=-300.0)
    cx = sqlite3.connect(migrated_db)
    try:
        rec_lock = compute_bias_track_record(cx, "lock_in")
        rec_fomo = compute_bias_track_record(cx, "fomo_greed")
        assert rec_lock["n_resolved"] == 1
        assert rec_lock["total_delta_signed_eur"] == -100.0
        assert rec_fomo["n_resolved"] == 2
        assert rec_fomo["total_delta_signed_eur"] == 200.0
    finally:
        cx.close()


# ─── Rolling window ───────────────────────────────────────────────────────


def test_rolling_window_excludes_old(migrated_db):
    """Rolling 30j -> exclut event cree il y a 60j."""
    _add_event(migrated_db, bias="lock_in", delta_signed_eur=-100.0, days_ago=60)
    _add_event(migrated_db, bias="lock_in", delta_signed_eur=-200.0, days_ago=10)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_bias_track_record(cx, "lock_in", rolling_days=30)
        assert rec["n_resolved"] == 1
        assert rec["total_delta_signed_eur"] == -200.0
    finally:
        cx.close()


# ─── Missing/corrupted resolution_json ────────────────────────────────────


def test_missing_resolution_json_counted_but_no_delta(migrated_db):
    """Event resolved sans delta_signed_eur valide -> compté en n_resolved
    mais pas dans cumul. Defensive contre corrupted JSON."""
    cx = sqlite3.connect(migrated_db)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, "
        "decision_json, counterfactual_json, resolution_json, status, "
        "source, horizon_days, resolve_at) "
        "VALUES (datetime('now'), 'X', 'lock_in', 'acted_on_bias', "
        "'{}', '{}', '{not valid json}', 'resolved', 'auto_detected', "
        "90, datetime('now', '+30 days'))"
    )
    cx.commit()
    cx.close()
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_bias_track_record(cx, "lock_in")
        assert rec["n_resolved"] == 1
        assert rec["total_delta_signed_eur"] == 0.0
        assert rec["avg_delta_eur"] is None  # pas calculable
    finally:
        cx.close()


# ─── compute_all ──────────────────────────────────────────────────────────


def test_compute_all_returns_three_bias(migrated_db):
    """compute_all retourne les 3 bias dans l'ordre canonique."""
    cx = sqlite3.connect(migrated_db)
    try:
        all_rec = compute_all_bias_track_records(cx)
        assert len(all_rec) == 3
        assert all_rec[0]["bias"] == "lock_in"
        assert all_rec[1]["bias"] == "fomo_greed"
        assert all_rec[2]["bias"] == "other"
    finally:
        cx.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
