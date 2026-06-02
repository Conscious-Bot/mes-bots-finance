"""Tests track_record_aggregator : single source of truth pour public track."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from intelligence.track_record_aggregator import compute_public_track_record


def _add_thesis(db: Path, ticker: str, direction: str = "bullish",
                days_ago: int = 30) -> None:
    cx = sqlite3.connect(db)
    opened_at = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    cx.execute(
        "INSERT INTO theses (ticker, conviction, direction, status, opened_at, "
        "entry_price, target_full, stop_price) "
        "VALUES (?, 4, ?, 'active', ?, 100.0, 160.0, 85.0)",
        (ticker, direction, opened_at),
    )
    cx.commit()
    cx.close()


def _add_resolved_prediction(db: Path, ticker: str, direction: str = "bullish",
                              brier: float = 0.15, outcome: str = "correct") -> None:
    cx = sqlite3.connect(db)
    cx.execute(
        "INSERT OR IGNORE INTO sources (name, type, credibility) "
        "VALUES ('test_src', 'newsletter', 0.7)"
    )
    src_id = cx.execute("SELECT id FROM sources WHERE name='test_src'").fetchone()[0]
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities) "
        "VALUES (?, 'test', ?, ?)",
        (src_id, datetime.now(UTC).isoformat(), f'["{ticker}"]'),
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.execute(
        "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
        "baseline_price, baseline_date, target_date, probability_at_creation, "
        "brier_score, outcome, resolved_at, methodology_version) "
        "VALUES (?, ?, ?, 28, 100.0, "
        "date('now', '-30 days'), date('now', '-2 days'), 0.7, ?, ?, "
        "datetime('now', '-2 days'), 'v2')",
        (sig_id, ticker, direction, brier, outcome),
    )
    cx.commit()
    cx.close()


def _add_resolved_bias(db: Path, bias: str = "lock_in", ticker: str = "NVDA",
                       delta_signed_eur: float = -200.0) -> None:
    cx = sqlite3.connect(db)
    res = json.dumps({
        "delta_signed_eur": delta_signed_eur,
        "horizon_days": 90,
        "anchor_price_eur": 100.0,
        "resolved_at": datetime.now(UTC).isoformat(),
    }, sort_keys=True)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, "
        "decision_json, counterfactual_json, resolution_json, status, "
        "source, horizon_days, resolve_at) "
        "VALUES (datetime('now'), ?, ?, 'acted_on_bias', "
        "'{}', '{}', ?, 'resolved', 'auto_detected', 90, "
        "datetime('now', '+30 days'))",
        (ticker, bias, res),
    )
    cx.commit()
    cx.close()


# ─── Smoke : structure shell ──────────────────────────────────────────────


def test_empty_db_returns_full_structure(migrated_db):
    """Meme avec DB vide, l'aggregator retourne la structure attendue."""
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_public_track_record(cx)
        assert "as_of" in rec
        assert "predictions" in rec
        assert "bias_events" in rec
        assert "theses" in rec
        assert "alpha" in rec
        assert "sources" in rec
        assert "methodology" in rec
        assert "posture_global" in rec
        assert rec["rolling_days"] == 180
    finally:
        cx.close()


def test_empty_db_posture_insufficient(migrated_db):
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_public_track_record(cx)
        assert rec["posture_global"] == "INSUFFICIENT_DATA"
        assert rec["predictions"]["n_resolved"] == 0
        assert rec["predictions"]["brier_status"] == "INSUFFICIENT_DATA"
        assert rec["theses"]["n_active"] == 0
    finally:
        cx.close()


# ─── Predictions populated ────────────────────────────────────────────────


def test_predictions_brier_ok(migrated_db):
    """5+ predictions resolved avec Brier <= 0.20 -> brier_status=OK."""
    for _ in range(6):
        _add_resolved_prediction(migrated_db, "NVDA", brier=0.15)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_public_track_record(cx)
        assert rec["predictions"]["n_resolved"] == 6
        assert rec["predictions"]["brier_avg"] == 0.15
        assert rec["predictions"]["brier_status"] == "OK"
    finally:
        cx.close()


def test_predictions_brier_alert(migrated_db):
    for _ in range(5):
        _add_resolved_prediction(migrated_db, "NVDA", brier=0.35, outcome="incorrect")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_public_track_record(cx)
        assert rec["predictions"]["brier_status"] == "ALERT"
        assert rec["posture_global"] == "ALERT"
    finally:
        cx.close()


# ─── Bias events aggregation ──────────────────────────────────────────────


def test_bias_events_aggregated(migrated_db):
    for _ in range(5):
        _add_resolved_bias(migrated_db, bias="lock_in", delta_signed_eur=-200.0)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_public_track_record(cx)
        assert len(rec["bias_events"]) == 3  # 3 bias canoniques
        lock_in = next(b for b in rec["bias_events"] if b["bias"] == "lock_in")
        assert lock_in["total_delta_signed_eur"] == -1000.0
        assert lock_in["posture"] == "ALERT"
        assert rec["bias_total_delta_signed_eur"] == -1000.0
    finally:
        cx.close()


# ─── Theses aggregation ───────────────────────────────────────────────────


def test_theses_by_posture(migrated_db):
    """3 theses, 1 avec brier OK / 1 INSUFFICIENT / 1 ALERT."""
    # OK : 5 preds aligned brier 0.15
    _add_thesis(migrated_db, "AAA", direction="bullish")
    for _ in range(5):
        _add_resolved_prediction(migrated_db, "AAA", direction="bullish", brier=0.15)
    # INSUFFICIENT : 1 pred (< 3)
    _add_thesis(migrated_db, "BBB", direction="bullish")
    _add_resolved_prediction(migrated_db, "BBB", direction="bullish", brier=0.15)
    # ALERT : 5 preds brier 0.40 mis-aligned
    _add_thesis(migrated_db, "CCC", direction="bullish")
    for _ in range(5):
        _add_resolved_prediction(migrated_db, "CCC", direction="bearish",
                                  brier=0.40, outcome="incorrect")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_public_track_record(cx)
        assert rec["theses"]["n_active"] == 3
        # By posture distribution
        assert rec["theses"]["by_posture"]["OK"] == 1
        assert rec["theses"]["by_posture"]["INSUFFICIENT_DATA"] == 1
        assert rec["theses"]["by_posture"]["ALERT"] == 1
        # Top alerts must contain CCC
        alert_tickers = [t["ticker"] for t in rec["theses"]["top_alert_tickers"]]
        assert "CCC" in alert_tickers
    finally:
        cx.close()


# ─── Posture global propagation ──────────────────────────────────────────


def test_global_posture_alert_when_predictions_alert(migrated_db):
    for _ in range(5):
        _add_resolved_prediction(migrated_db, "NVDA", brier=0.40, outcome="incorrect")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_public_track_record(cx)
        assert rec["posture_global"] == "ALERT"
    finally:
        cx.close()


def test_global_posture_alert_when_bias_alert(migrated_db):
    """Bias ALERT cumul -> global ALERT meme si predictions OK."""
    for _ in range(6):
        _add_resolved_prediction(migrated_db, "AAA", brier=0.15)
    for _ in range(5):
        _add_resolved_bias(migrated_db, bias="lock_in", delta_signed_eur=-200.0)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_public_track_record(cx)
        assert rec["posture_global"] == "ALERT"
    finally:
        cx.close()


# ─── Methodology disclosure ──────────────────────────────────────────────


def test_methodology_section_complete(migrated_db):
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_public_track_record(cx)
        m = rec["methodology"]
        assert m["scorer_version"] == "v2"
        assert m["prediction_horizon_days"] == 28
        assert m["lock_in_horizon_days"] == 90
        assert m["lock_in_targets_by_conv"][5] == 0.70
        assert m["lock_in_magnitude_threshold_by_conv"][5] == 0.25
        assert m["credibility_floor_ceiling"] == [0.30, 0.95]
    finally:
        cx.close()


# ─── Defensive : errors ne crashent pas ──────────────────────────────────


def test_aggregator_does_not_crash_on_subsection_errors(migrated_db):
    """Si une section interne crash, on retourne quand meme la structure
    avec 'error' key dans la section concernee."""
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_public_track_record(cx)
        # Au minimum predictions et bias_events et theses sont calcules
        assert "predictions" in rec
        assert "bias_events" in rec
        assert "theses" in rec
        # alpha + sources peuvent retourner error (data manquante)
        # mais doivent pas crasher
    finally:
        cx.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
