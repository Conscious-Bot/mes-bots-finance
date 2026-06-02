"""Tests timeseries helpers (charts publics)."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from intelligence.track_record_timeseries import (
    compute_all_timeseries,
    compute_bias_cumul_timeseries,
    compute_brier_rolling_timeseries,
    compute_predictions_volume_timeseries,
)


def _add_pred(db: Path, days_ago_resolved: int, brier: float = 0.15,
              outcome: str = "correct") -> None:
    cx = sqlite3.connect(db)
    cx.execute(
        "INSERT OR IGNORE INTO sources (name, type, credibility) "
        "VALUES ('src', 'newsletter', 0.7)"
    )
    src_id = cx.execute("SELECT id FROM sources WHERE name='src'").fetchone()[0]
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities) "
        "VALUES (?, 't', ?, '[\"NVDA\"]')",
        (src_id, datetime.now(UTC).isoformat()),
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    baseline = (datetime.now(UTC) - timedelta(days=days_ago_resolved + 28)).date().isoformat()
    target = (datetime.now(UTC) - timedelta(days=days_ago_resolved)).date().isoformat()
    resolved_at = (datetime.now(UTC) - timedelta(days=days_ago_resolved)).isoformat()
    cx.execute(
        "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
        "baseline_price, baseline_date, target_date, probability_at_creation, "
        "brier_score, outcome, resolved_at, methodology_version) "
        "VALUES (?, 'NVDA', 'bullish', 28, 100.0, ?, ?, 0.7, ?, ?, ?, 'v2')",
        (sig_id, baseline, target, brier, outcome, resolved_at),
    )
    cx.commit()
    cx.close()


def _add_bias(db: Path, bias: str = "lock_in",
              days_ago_resolved: int = 30,
              delta_signed_eur: float = -100.0) -> None:
    cx = sqlite3.connect(db)
    created = (datetime.now(UTC) - timedelta(days=days_ago_resolved + 90)).isoformat()
    resolved = (datetime.now(UTC) - timedelta(days=days_ago_resolved)).isoformat()
    res = json.dumps({
        "delta_signed_eur": delta_signed_eur,
        "resolved_at": resolved,
        "horizon_days": 90,
        "anchor_price_eur": 100.0,
    }, sort_keys=True)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, "
        "decision_json, counterfactual_json, resolution_json, status, "
        "source, horizon_days, resolve_at) "
        "VALUES (?, 'NVDA', ?, 'acted_on_bias', '{}', '{}', ?, "
        "'resolved', 'auto_detected', 90, datetime('now', '+30 days'))",
        (created, bias, res),
    )
    cx.commit()
    cx.close()


# ─── compute_brier_rolling_timeseries ─────────────────────────────────────


def test_brier_rolling_empty_db(migrated_db):
    cx = sqlite3.connect(migrated_db)
    try:
        ts = compute_brier_rolling_timeseries(cx, total_days=30, step_days=7)
        # All points should have brier_avg=None (no data)
        assert len(ts) > 0
        for p in ts:
            assert p["brier_avg"] is None
            assert p["n_resolved"] == 0
    finally:
        cx.close()


def test_brier_rolling_with_data(migrated_db):
    """3+ preds resolved sur la fenetre -> brier_avg calcule."""
    for i in range(5):
        _add_pred(migrated_db, days_ago_resolved=10 + i, brier=0.15)
    cx = sqlite3.connect(migrated_db)
    try:
        ts = compute_brier_rolling_timeseries(
            cx, window_days=30, total_days=60, step_days=7,
        )
        # Au moins un point recent doit avoir des data
        recent = ts[-1]
        assert recent["brier_avg"] == 0.15
        assert recent["n_resolved"] == 5
        assert recent["accuracy_pct"] == 100.0
    finally:
        cx.close()


def test_brier_rolling_chrono_order(migrated_db):
    """Points sont en ordre chronologique croissant."""
    cx = sqlite3.connect(migrated_db)
    try:
        ts = compute_brier_rolling_timeseries(cx, total_days=180, step_days=30)
        dates = [p["date"] for p in ts]
        assert dates == sorted(dates)
    finally:
        cx.close()


def test_brier_rolling_insufficient_data_threshold(migrated_db):
    """N<3 sur fenetre -> brier_avg=None."""
    _add_pred(migrated_db, days_ago_resolved=10, brier=0.15)
    _add_pred(migrated_db, days_ago_resolved=12, brier=0.15)
    cx = sqlite3.connect(migrated_db)
    try:
        ts = compute_brier_rolling_timeseries(cx, window_days=30, total_days=60)
        recent = ts[-1]
        assert recent["n_resolved"] == 2
        assert recent["brier_avg"] is None  # < 3 -> None
    finally:
        cx.close()


# ─── compute_bias_cumul_timeseries ────────────────────────────────────────


def test_bias_cumul_empty_db(migrated_db):
    cx = sqlite3.connect(migrated_db)
    try:
        ts = compute_bias_cumul_timeseries(cx, "lock_in", total_days=60, step_days=7)
        # Tous a 0
        assert all(p["cumul_delta_eur"] == 0.0 for p in ts)
        assert all(p["n_resolved_to_date"] == 0 for p in ts)
    finally:
        cx.close()


def test_bias_cumul_running_total(migrated_db):
    """3 events resolved -100, -200, +50 -> cumul final -250 EUR."""
    _add_bias(migrated_db, "lock_in", days_ago_resolved=50, delta_signed_eur=-100.0)
    _add_bias(migrated_db, "lock_in", days_ago_resolved=30, delta_signed_eur=-200.0)
    _add_bias(migrated_db, "lock_in", days_ago_resolved=10, delta_signed_eur=50.0)
    cx = sqlite3.connect(migrated_db)
    try:
        ts = compute_bias_cumul_timeseries(cx, "lock_in", total_days=90, step_days=15)
        final = ts[-1]
        assert final["cumul_delta_eur"] == -250.0
        assert final["n_resolved_to_date"] == 3
        # Cumul monotone (always >= n_to_date precedent)
        prev_n = 0
        for p in ts:
            assert p["n_resolved_to_date"] >= prev_n
            prev_n = p["n_resolved_to_date"]
    finally:
        cx.close()


def test_bias_cumul_excludes_other_bias(migrated_db):
    """Events fomo_greed n'apparaissent pas dans lock_in cumul."""
    _add_bias(migrated_db, "lock_in", days_ago_resolved=10, delta_signed_eur=-100.0)
    _add_bias(migrated_db, "fomo_greed", days_ago_resolved=10, delta_signed_eur=500.0)
    cx = sqlite3.connect(migrated_db)
    try:
        ts = compute_bias_cumul_timeseries(cx, "lock_in", total_days=30)
        assert ts[-1]["cumul_delta_eur"] == -100.0
        ts_fomo = compute_bias_cumul_timeseries(cx, "fomo_greed", total_days=30)
        assert ts_fomo[-1]["cumul_delta_eur"] == 500.0
    finally:
        cx.close()


def test_bias_cumul_handles_corrupted_json(migrated_db):
    """Resolution_json corrompu -> ignored, pas de crash."""
    cx = sqlite3.connect(migrated_db)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, "
        "decision_json, counterfactual_json, resolution_json, status, "
        "source, horizon_days, resolve_at) "
        "VALUES (datetime('now'), 'X', 'lock_in', 'acted_on_bias', "
        "'{}', '{}', '{bad json}', 'resolved', 'auto_detected', "
        "90, datetime('now', '+30 days'))"
    )
    cx.commit()
    cx.close()
    cx = sqlite3.connect(migrated_db)
    try:
        ts = compute_bias_cumul_timeseries(cx, "lock_in", total_days=30)
        assert ts[-1]["cumul_delta_eur"] == 0.0
        assert ts[-1]["n_resolved_to_date"] == 0
    finally:
        cx.close()


# ─── compute_predictions_volume_timeseries ────────────────────────────────


def test_volume_timeseries_counts(migrated_db):
    """Counts preds created and resolved per window."""
    _add_pred(migrated_db, days_ago_resolved=10)
    _add_pred(migrated_db, days_ago_resolved=12)
    cx = sqlite3.connect(migrated_db)
    try:
        ts = compute_predictions_volume_timeseries(cx, total_days=60, step_days=7)
        # Most recent window should contain at least the recent resolved
        total_created = sum(p["n_created_in_window"] for p in ts)
        total_resolved = sum(p["n_resolved_in_window"] for p in ts)
        assert total_resolved >= 2
        # baseline_date dans le passe (resolved-28j), donc cree avant
        assert total_created >= 2
    finally:
        cx.close()


# ─── compute_all_timeseries ───────────────────────────────────────────────


def test_all_timeseries_bundle_keys(migrated_db):
    cx = sqlite3.connect(migrated_db)
    try:
        bundle = compute_all_timeseries(cx, total_days=60)
        assert "brier_rolling" in bundle
        assert "predictions_volume" in bundle
        assert "bias_cumul_lock_in" in bundle
        assert "bias_cumul_fomo_greed" in bundle
        # Tous des lists non-vides (au moins 1 point chacun)
        for v in bundle.values():
            assert isinstance(v, list)
            assert len(v) > 0
    finally:
        cx.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
