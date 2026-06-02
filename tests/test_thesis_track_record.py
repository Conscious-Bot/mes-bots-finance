"""Tests thesis_track_record : linkage these <-> predictions liees.

Boucle prediction -> learning -> tracking -> theses :
verifie que la these voit ses propres predictions, leur Brier, et
l'alignment directionnel.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from intelligence.thesis_track_record import (
    compute_all_active_theses_track_record,
    compute_thesis_track_record,
)


def _add_thesis(
    db: Path, ticker: str, conviction: int = 4,
    direction: str = "bullish", status: str = "active",
    days_ago: int = 60, entry_price: float = 100.0,
) -> int:
    cx = sqlite3.connect(db)
    opened_at = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    cx.execute(
        "INSERT INTO theses (ticker, conviction, direction, status, opened_at, "
        "entry_price, target_full, stop_price) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ticker, conviction, direction, status, opened_at,
         entry_price, entry_price * 1.6, entry_price * 0.85),
    )
    tid = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.commit()
    cx.close()
    return tid


def _add_prediction(
    db: Path, ticker: str,
    direction: str = "bullish",
    days_ago_baseline: int = 30,
    resolved: bool = True,
    outcome: str = "correct",
    brier: float = 0.15,
    probability: float = 0.7,
) -> int:
    cx = sqlite3.connect(db)
    # ensure source/signal exist
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
    baseline = (datetime.now(UTC) - timedelta(days=days_ago_baseline)).date().isoformat()
    target = (datetime.now(UTC) - timedelta(days=days_ago_baseline - 28)).date().isoformat()
    resolved_at = (datetime.now(UTC) - timedelta(days=2)).isoformat() if resolved else None
    cx.execute(
        "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
        "baseline_price, baseline_date, target_date, probability_at_creation, "
        "brier_score, outcome, resolved_at, methodology_version) "
        "VALUES (?, ?, ?, 28, 100.0, ?, ?, ?, ?, ?, ?, 'v2')",
        (sig_id, ticker, direction, baseline, target, probability,
         brier if resolved else None, outcome if resolved else None,
         resolved_at),
    )
    pid = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.commit()
    cx.close()
    return pid


# ─── Pas de these ─────────────────────────────────────────────────────────


def test_no_active_thesis_returns_none(migrated_db):
    cx = sqlite3.connect(migrated_db)
    try:
        assert compute_thesis_track_record(cx, "NVDA") is None
    finally:
        cx.close()


# ─── These sans predictions ───────────────────────────────────────────────


def test_thesis_without_predictions(migrated_db):
    """These sans aucune prediction liee -> INSUFFICIENT_DATA."""
    _add_thesis(migrated_db, "NVDA")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_thesis_track_record(cx, "NVDA")
        assert rec is not None
        assert rec["n_predictions_linked"] == 0
        assert rec["n_resolved"] == 0
        assert rec["brier_avg"] is None
        assert rec["posture"] == "INSUFFICIENT_DATA"
    finally:
        cx.close()


# ─── These avec predictions aligned ───────────────────────────────────────


def test_thesis_with_aligned_predictions_good_brier_ok(migrated_db):
    """Brier 0.15 + alignment 100% -> OK."""
    _add_thesis(migrated_db, "NVDA", direction="bullish")
    for _ in range(5):
        _add_prediction(migrated_db, "NVDA", direction="bullish", brier=0.15)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_thesis_track_record(cx, "NVDA")
        assert rec is not None
        assert rec["n_predictions_linked"] == 5
        assert rec["n_resolved"] == 5
        assert rec["brier_avg"] == 0.15
        assert rec["direction_alignment_pct"] == 100.0
        assert rec["posture"] == "OK"
    finally:
        cx.close()


# ─── Brier eleve -> WARN/ALERT ────────────────────────────────────────────


def test_thesis_with_warn_brier(migrated_db):
    """Brier 0.23 -> WARN."""
    _add_thesis(migrated_db, "NVDA", direction="bullish")
    for _ in range(5):
        _add_prediction(migrated_db, "NVDA", direction="bullish", brier=0.23)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_thesis_track_record(cx, "NVDA")
        assert rec["posture"] == "WARN"
    finally:
        cx.close()


def test_thesis_with_alert_brier(migrated_db):
    """Brier 0.40 -> ALERT."""
    _add_thesis(migrated_db, "NVDA", direction="bullish")
    for _ in range(5):
        _add_prediction(migrated_db, "NVDA", direction="bullish",
                        brier=0.40, outcome="incorrect")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_thesis_track_record(cx, "NVDA")
        assert rec["posture"] == "ALERT"
    finally:
        cx.close()


# ─── Direction alignment ──────────────────────────────────────────────────


def test_thesis_misaligned_predictions(migrated_db):
    """These bullish, predictions toutes bearish -> alignment 0%, ALERT."""
    _add_thesis(migrated_db, "NVDA", direction="bullish")
    for _ in range(5):
        _add_prediction(migrated_db, "NVDA", direction="bearish",
                        brier=0.20, outcome="incorrect")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_thesis_track_record(cx, "NVDA")
        assert rec["direction_alignment_pct"] == 0.0
        assert rec["n_aligned"] == 0
        assert rec["n_misaligned"] == 5
        # Brier 0.20 OK seul, mais alignment 0% < 60% -> WARN
        assert rec["posture"] == "WARN"
    finally:
        cx.close()


def test_thesis_mixed_alignment(migrated_db):
    """3 bullish + 2 bearish sur une these bullish -> 60% alignment."""
    _add_thesis(migrated_db, "NVDA", direction="bullish")
    for _ in range(3):
        _add_prediction(migrated_db, "NVDA", direction="bullish", brier=0.15)
    for _ in range(2):
        _add_prediction(migrated_db, "NVDA", direction="bearish", brier=0.15)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_thesis_track_record(cx, "NVDA")
        assert rec["direction_alignment_pct"] == 60.0
        assert rec["n_aligned"] == 3
        assert rec["n_misaligned"] == 2
    finally:
        cx.close()


# ─── Predictions ouvertes ─────────────────────────────────────────────────


def test_thesis_with_open_predictions(migrated_db):
    """3 resolved + 2 open -> n_resolved=3, n_open=2."""
    _add_thesis(migrated_db, "NVDA", direction="bullish")
    for _ in range(3):
        _add_prediction(migrated_db, "NVDA", direction="bullish",
                        brier=0.15, resolved=True)
    for _ in range(2):
        _add_prediction(migrated_db, "NVDA", direction="bullish",
                        resolved=False)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_thesis_track_record(cx, "NVDA")
        assert rec["n_predictions_linked"] == 5
        assert rec["n_resolved"] == 3
        assert rec["n_open"] == 2
    finally:
        cx.close()


# ─── Filtre opened_at ─────────────────────────────────────────────────────


def test_predictions_before_thesis_opened_excluded(migrated_db):
    """Predictions avec baseline_date < these opened_at -> exclues."""
    _add_thesis(migrated_db, "NVDA", days_ago=30)  # these opened il y a 30j
    _add_prediction(migrated_db, "NVDA", days_ago_baseline=60)  # baseline 60j -> avant these
    _add_prediction(migrated_db, "NVDA", days_ago_baseline=10)  # baseline 10j -> apres these
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_thesis_track_record(cx, "NVDA")
        assert rec["n_predictions_linked"] == 1  # seule la 2eme compte
    finally:
        cx.close()


# ─── Rolling window optional ──────────────────────────────────────────────


def test_rolling_window_filter(migrated_db):
    """rolling_days=15 -> exclut predictions plus vieilles que 15j."""
    _add_thesis(migrated_db, "NVDA", days_ago=60)
    _add_prediction(migrated_db, "NVDA", days_ago_baseline=30)  # exclu si rolling=15
    _add_prediction(migrated_db, "NVDA", days_ago_baseline=10)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_thesis_track_record(cx, "NVDA", rolling_days=15)
        assert rec["n_predictions_linked"] == 1
    finally:
        cx.close()


# ─── All active theses ────────────────────────────────────────────────────


def test_all_active_theses_sorted_by_n_resolved(migrated_db):
    """3 theses, sorted by n_resolved DESC."""
    _add_thesis(migrated_db, "AAA", direction="bullish")
    _add_thesis(migrated_db, "BBB", direction="bullish")
    _add_thesis(migrated_db, "CCC", direction="bullish")
    for _ in range(5):
        _add_prediction(migrated_db, "AAA", direction="bullish")
    for _ in range(2):
        _add_prediction(migrated_db, "BBB", direction="bullish")
    # CCC : 0 predictions
    cx = sqlite3.connect(migrated_db)
    try:
        all_rec = compute_all_active_theses_track_record(cx)
        assert len(all_rec) == 3
        assert all_rec[0]["ticker"] == "AAA"
        assert all_rec[0]["n_resolved"] == 5
        assert all_rec[1]["ticker"] == "BBB"
        assert all_rec[1]["n_resolved"] == 2
        assert all_rec[2]["ticker"] == "CCC"
        assert all_rec[2]["n_resolved"] == 0
    finally:
        cx.close()


# ─── Inactive theses skipped ──────────────────────────────────────────────


def test_inactive_thesis_returns_none(migrated_db):
    _add_thesis(migrated_db, "NVDA", status="closed")
    _add_prediction(migrated_db, "NVDA", direction="bullish")
    cx = sqlite3.connect(migrated_db)
    try:
        assert compute_thesis_track_record(cx, "NVDA") is None
    finally:
        cx.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
