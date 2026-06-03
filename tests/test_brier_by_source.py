"""#72 LOOP -- Tests compute_brier_by_source (disaggregation par source).

Verifie :
  1. Aggregation correcte par source name
  2. Brier moyen, accuracy, Wilson CI
  3. Status thresholds OK/WARN/ALERT/INSUFFICIENT_DATA
  4. Filtre fenetre temporelle
  5. Exclusion neutrals, v0, unresolved
  6. Tri par n_resolved DESC
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from intelligence.calibration_audit import compute_brier_by_source


def _seed(
    db: Path, source_name: str, predictions: list[tuple[float, str]],
    days_ago: int = 30,
) -> None:
    """Insert source + signal + N predictions (brier_score, outcome)."""
    from datetime import UTC, datetime, timedelta
    cx = sqlite3.connect(db)
    cx.execute(
        "INSERT OR IGNORE INTO sources (name, type, credibility) VALUES (?, ?, ?)",
        (source_name, "test", 0.7),
    )
    src_id = cx.execute(
        "SELECT id FROM sources WHERE name=?", (source_name,)
    ).fetchone()[0]
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities) "
        "VALUES (?, ?, ?, '[\"NVDA\"]')",
        (src_id, f"sig for {source_name}",
         (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()),
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    resolved_at = (datetime.now(UTC) - timedelta(days=max(0, days_ago - 28))).isoformat()
    for brier, outcome in predictions:
        cx.execute(
            # ADR 014 : compute_brier_by_source = forward-headline surface,
            # filtre via canonical_predictions_filter() qui exclut v1. Les
            # fixtures specifient methodology_version='v2' pour rester dans
            # le scope canonique (sinon les inserts utilisent le DEFAULT 'v1'
            # de la colonne et les tests renvoient 0).
            "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
            "baseline_price, baseline_date, target_date, probability_at_creation, "
            "brier_score, outcome, resolved_at, methodology_version) "
            "VALUES (?, 'NVDA', 'bullish', 28, 100.0, "
            "?, ?, 0.65, ?, ?, ?, 'v2')",
            (sig_id,
             (datetime.now(UTC) - timedelta(days=days_ago)).date().isoformat(),
             (datetime.now(UTC) - timedelta(days=max(0, days_ago - 28))).date().isoformat(),
             brier, outcome, resolved_at),
        )
    cx.commit()
    cx.close()


# ─── Aggregation ──────────────────────────────────────────────────────────


def test_empty_db_returns_empty(migrated_db):
    cx = sqlite3.connect(migrated_db)
    try:
        result = compute_brier_by_source(cx, days=180)
        assert result == []
    finally:
        cx.close()


def test_single_source_aggregation(migrated_db):
    """5 predictions sur EDGAR_8K -> 1 row, brier_avg + accuracy corrects."""
    _seed(migrated_db, "EDGAR_8K", [
        (0.10, "correct"),
        (0.15, "correct"),
        (0.20, "correct"),
        (0.25, "incorrect"),
        (0.30, "incorrect"),
    ])
    cx = sqlite3.connect(migrated_db)
    try:
        result = compute_brier_by_source(cx, days=180)
        assert len(result) == 1
        r = result[0]
        assert r["source_name"] == "EDGAR_8K"
        assert r["n_resolved"] == 5
        assert abs(r["brier_avg"] - 0.20) < 1e-6
        assert r["accuracy"] == 0.6  # 3/5
    finally:
        cx.close()


def test_two_sources_sorted_by_n(migrated_db):
    """EDGAR avec 6, Newsletter avec 3 -> EDGAR en premier."""
    _seed(migrated_db, "EDGAR", [(0.15, "correct")] * 6)
    _seed(migrated_db, "Newsletter_X", [(0.30, "incorrect")] * 3)
    cx = sqlite3.connect(migrated_db)
    try:
        result = compute_brier_by_source(cx, days=180)
        assert len(result) == 2
        assert result[0]["source_name"] == "EDGAR"
        assert result[0]["n_resolved"] == 6
        assert result[1]["source_name"] == "Newsletter_X"
        assert result[1]["n_resolved"] == 3
    finally:
        cx.close()


# ─── Status thresholds ────────────────────────────────────────────────────


def test_status_ok_brier_low(migrated_db):
    """Brier moyen 0.15 + n>=5 -> OK."""
    _seed(migrated_db, "good_src", [(0.15, "correct")] * 6)
    cx = sqlite3.connect(migrated_db)
    try:
        result = compute_brier_by_source(cx, days=180)
        assert result[0]["status"] == "OK"
    finally:
        cx.close()


def test_status_warn_brier_mid(migrated_db):
    """Brier moyen 0.23 -> WARN."""
    _seed(migrated_db, "mid_src", [(0.23, "incorrect")] * 5)
    cx = sqlite3.connect(migrated_db)
    try:
        result = compute_brier_by_source(cx, days=180)
        assert result[0]["status"] == "WARN"
    finally:
        cx.close()


def test_status_alert_brier_high(migrated_db):
    """Brier moyen 0.40 -> ALERT."""
    _seed(migrated_db, "bad_src", [(0.40, "incorrect")] * 5)
    cx = sqlite3.connect(migrated_db)
    try:
        result = compute_brier_by_source(cx, days=180)
        assert result[0]["status"] == "ALERT"
    finally:
        cx.close()


def test_status_insufficient_data_n_below_5(migrated_db):
    """n=3 -> INSUFFICIENT_DATA quel que soit le Brier."""
    _seed(migrated_db, "small_src", [(0.10, "correct")] * 3)
    cx = sqlite3.connect(migrated_db)
    try:
        result = compute_brier_by_source(cx, days=180)
        assert result[0]["status"] == "INSUFFICIENT_DATA"
        assert result[0]["n_resolved"] == 3
    finally:
        cx.close()


# ─── Filtres ──────────────────────────────────────────────────────────────


def test_window_filter_excludes_old(migrated_db):
    """Predictions resolved il y a 372j (sig 400j old) ne doivent pas
    apparaitre dans fenetre 180j."""
    _seed(migrated_db, "old_src", [(0.10, "correct")] * 5, days_ago=400)
    cx = sqlite3.connect(migrated_db)
    try:
        result = compute_brier_by_source(cx, days=180)
        assert result == []
    finally:
        cx.close()


def test_excludes_neutrals(migrated_db):
    """Outcome 'neutral' ne doit pas etre compte."""
    _seed(migrated_db, "src", [
        (0.10, "correct"),
        (0.0, "neutral"),  # exclu
        (0.20, "incorrect"),
    ])
    cx = sqlite3.connect(migrated_db)
    try:
        result = compute_brier_by_source(cx, days=180)
        assert result[0]["n_resolved"] == 2  # exclut neutral
    finally:
        cx.close()


def test_includes_signals_without_source(migrated_db):
    """Si signal n'a pas de source liee, source_name='?' fallback."""
    cx = sqlite3.connect(migrated_db)
    # Signal sans source_id
    cx.execute(
        "INSERT INTO signals (title, timestamp, entities) "
        "VALUES ('orphan', '2026-06-02T10:00:00+00:00', '[\"X\"]')"
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.execute(
        # ADR 014 : methodology_version='v2' explicit (cf docstring _seed).
        "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
        "baseline_price, baseline_date, target_date, probability_at_creation, "
        "brier_score, outcome, resolved_at, methodology_version) "
        "VALUES (?, 'X', 'bullish', 28, 100, '2026-05-01', '2026-05-29', "
        "0.6, 0.15, 'correct', datetime('now', '-5 days'), 'v2')",
        (sig_id,),
    )
    cx.commit()
    try:
        result = compute_brier_by_source(cx, days=180)
        assert len(result) == 1
        assert result[0]["source_name"] == "?"
    finally:
        cx.close()


# ─── Wilson CI ────────────────────────────────────────────────────────────


def test_wilson_ic95_contains_accuracy(migrated_db):
    """IC95 doit contenir accuracy point (sanity)."""
    _seed(migrated_db, "src_test", [(0.15, "correct")] * 8 + [(0.30, "incorrect")] * 2)
    cx = sqlite3.connect(migrated_db)
    try:
        result = compute_brier_by_source(cx, days=180)
        r = result[0]
        # accuracy = 0.8, IC95 doit englober 0.8
        assert r["accuracy"] == 0.8
        assert r["brier_ic95_low"] <= r["accuracy"] <= r["brier_ic95_high"]
        # IC95 doit etre [0, 1]
        assert 0.0 <= r["brier_ic95_low"] <= r["brier_ic95_high"] <= 1.0
    finally:
        cx.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
