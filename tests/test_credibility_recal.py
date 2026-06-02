"""#76 LOOP -- Tests recalibrate_source_credibility (recal mensuel auto).

Verifie :
  1. Source avec n<min_n : pas d'update, applied=False
  2. Source ALERT (Brier 0.40) : credibility descend
  3. Source OK (Brier 0.10) : credibility monte
  4. Floor/ceiling respectes (jamais hors [0.30, 0.95])
  5. Learning rate (inertie 70%)
  6. dry_run mode = pas d'update
  7. Delta minimum 0.001 = pas d'update
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from intelligence.calibration_audit import recalibrate_source_credibility


def _seed(
    db: Path, source_name: str, initial_cred: float,
    n_correct: int, n_incorrect: int, brier_per_pred: float,
) -> None:
    """Crée source + N prédictions résolues avec Brier ciblé."""
    cx = sqlite3.connect(db)
    cx.execute(
        "INSERT OR REPLACE INTO sources (name, type, credibility) VALUES (?, ?, ?)",
        (source_name, "test", initial_cred),
    )
    src_id = cx.execute(
        "SELECT id FROM sources WHERE name=?", (source_name,)
    ).fetchone()[0]
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities) "
        "VALUES (?, ?, ?, '[\"NVDA\"]')",
        (src_id, f"sig {source_name}",
         (datetime.now(UTC) - timedelta(days=30)).isoformat()),
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    resolved_at = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    for outcome in (["correct"] * n_correct + ["incorrect"] * n_incorrect):
        cx.execute(
            "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
            "baseline_price, baseline_date, target_date, probability_at_creation, "
            "brier_score, outcome, resolved_at) "
            "VALUES (?, 'NVDA', 'bullish', 28, 100.0, "
            "'2026-05-01', '2026-05-29', 0.65, ?, ?, ?)",
            (sig_id, brier_per_pred, outcome, resolved_at),
        )
    cx.commit()
    cx.close()


def _get_cred(db: Path, source_name: str) -> float:
    cx = sqlite3.connect(db)
    try:
        row = cx.execute(
            "SELECT credibility FROM sources WHERE name=?", (source_name,)
        ).fetchone()
    finally:
        cx.close()
    return float(row[0]) if row else 0.0


# ─── Path nominal ─────────────────────────────────────────────────────────


def test_source_below_min_n_not_recalibrated(migrated_db):
    """n=5 < min_n=10 -> pas d'update, applied=False."""
    _seed(migrated_db, "small", 0.7, n_correct=3, n_incorrect=2, brier_per_pred=0.20)
    cx = sqlite3.connect(migrated_db)
    try:
        result = recalibrate_source_credibility(cx, min_n=10)
        small = next(r for r in result if r["source_name"] == "small")
        assert small["applied"] is False
        assert small["new_cred"] == small["old_cred"]
        assert "n<10" in small["reason"]
    finally:
        cx.close()
    # Credibility en DB inchange
    assert _get_cred(migrated_db, "small") == pytest.approx(0.7)


def test_alert_source_credibility_decreases(migrated_db):
    """Source avec Brier 0.40 ALERT -> target_cred = 0.60, old=0.85, descend."""
    _seed(migrated_db, "bad", 0.85, n_correct=2, n_incorrect=10, brier_per_pred=0.40)
    cx = sqlite3.connect(migrated_db)
    try:
        result = recalibrate_source_credibility(cx, min_n=10)
        bad = next(r for r in result if r["source_name"] == "bad")
        assert bad["applied"] is True
        assert bad["new_cred"] < bad["old_cred"]
        # learning_rate=0.3 : new = 0.85 + 0.3*(0.60 - 0.85) = 0.775
        assert abs(bad["new_cred"] - 0.775) < 0.01
    finally:
        cx.close()
    assert _get_cred(migrated_db, "bad") == pytest.approx(0.775, abs=0.01)


def test_ok_source_credibility_increases(migrated_db):
    """Source avec Brier 0.10 OK + cred a priori 0.5 -> bump vers 0.90."""
    _seed(migrated_db, "good", 0.5, n_correct=10, n_incorrect=0, brier_per_pred=0.10)
    cx = sqlite3.connect(migrated_db)
    try:
        result = recalibrate_source_credibility(cx, min_n=10)
        good = next(r for r in result if r["source_name"] == "good")
        assert good["applied"] is True
        # new = 0.5 + 0.3*(0.90 - 0.5) = 0.62
        assert abs(good["new_cred"] - 0.62) < 0.01
    finally:
        cx.close()


# ─── Floor/ceiling ────────────────────────────────────────────────────────


def test_floor_respected(migrated_db):
    """Source totalement cassee (Brier 0.99) -> floor 0.30 atteint."""
    _seed(migrated_db, "broken", 0.32, n_correct=0, n_incorrect=12, brier_per_pred=0.99)
    cx = sqlite3.connect(migrated_db)
    try:
        result = recalibrate_source_credibility(cx, min_n=10, floor=0.30)
        broken = next(r for r in result if r["source_name"] == "broken")
        assert broken["new_cred"] >= 0.30
    finally:
        cx.close()


def test_ceiling_respected(migrated_db):
    """Source parfaite (Brier 0.0) + cred 0.94 -> ceiling 0.95 cap."""
    _seed(migrated_db, "perfect", 0.94, n_correct=12, n_incorrect=0, brier_per_pred=0.0)
    cx = sqlite3.connect(migrated_db)
    try:
        result = recalibrate_source_credibility(cx, min_n=10, ceiling=0.95)
        perf = next(r for r in result if r["source_name"] == "perfect")
        assert perf["new_cred"] <= 0.95
    finally:
        cx.close()


# ─── dry_run ──────────────────────────────────────────────────────────────


def test_dry_run_no_db_update(migrated_db):
    """dry_run=True -> calcul correct mais credibility en DB unchanged."""
    _seed(migrated_db, "dry", 0.7, n_correct=2, n_incorrect=10, brier_per_pred=0.40)
    cx = sqlite3.connect(migrated_db)
    try:
        result = recalibrate_source_credibility(cx, min_n=10, dry_run=True)
        dry = next(r for r in result if r["source_name"] == "dry")
        assert dry["applied"] is False
        assert dry["reason"] == "dry_run"
        assert dry["new_cred"] != dry["old_cred"]  # calcul fait
    finally:
        cx.close()
    # Pas de change en DB
    assert _get_cred(migrated_db, "dry") == pytest.approx(0.7)


# ─── Delta minimum ────────────────────────────────────────────────────────


def test_minimal_delta_not_applied(migrated_db):
    """Si delta < 0.001 (deja optimal), pas d'update bruyant."""
    # Source dont la target = old (Brier match credibility)
    # old=0.85, brier=0.15 -> target=0.85, delta=0
    _seed(migrated_db, "optimal", 0.85, n_correct=10, n_incorrect=0, brier_per_pred=0.15)
    cx = sqlite3.connect(migrated_db)
    try:
        result = recalibrate_source_credibility(cx, min_n=10)
        opt = next(r for r in result if r["source_name"] == "optimal")
        assert opt["applied"] is False
        assert abs(opt["delta"]) < 0.001
    finally:
        cx.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
