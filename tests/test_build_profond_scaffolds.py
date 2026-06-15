"""Tests pour les 3 modules build-profond scaffolde (strategie user 31/05) :
- intelligence/recalib_map.py
- intelligence/base_rates.py
- intelligence/outcome_context.py

Focus : verifier le cold-start safe (insufficient data -> None/empty, pas
de crash) + happy path avec data suffisante en memoire (in-memory SQLite).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC

import pytest

from intelligence import base_rates, outcome_context, recalib_map


@pytest.fixture
def empty_db() -> sqlite3.Connection:
    """In-memory SQLite avec schema predictions vide (cold start)."""
    cx = sqlite3.connect(":memory:")
    cx.execute("""
        CREATE TABLE predictions (
            id INTEGER PRIMARY KEY,
            signal_id INTEGER,
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            baseline_price REAL,
            baseline_date TEXT NOT NULL,
            target_date TEXT NOT NULL,
            resolved_at TEXT,
            final_price REAL,
            return_pct REAL,
            outcome TEXT,
            credibility_delta REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            probability_at_creation REAL,
            brier_score REAL,
            signal_type TEXT,
            impact_magnitude REAL,
            methodology_version TEXT NOT NULL DEFAULT 'v1'
        )
    """)
    return cx


@pytest.fixture
def populated_db(empty_db: sqlite3.Connection) -> sqlite3.Connection:
    """In-memory DB avec 40 predictions resolues v1 (au-dessus de MIN_N_FIT=30).

    Dates relatives à 'now' (recent 7-15j) pour eviter test drift :
    fetch_recent_lessons filtre `resolved_at >= now-30 days`. Hard-coded dates
    cessent d'etre dans la fenetre apres N jours → test devient flaky (cure 15/06).
    """
    from datetime import datetime, timedelta, timezone
    _now = datetime.now(UTC)
    baseline_date = (_now - timedelta(days=20)).strftime("%Y-%m-%d")
    target_date = (_now - timedelta(days=10)).strftime("%Y-%m-%d")
    resolved_date = (_now - timedelta(days=7)).strftime("%Y-%m-%d")

    rows = []
    for i in range(40):
        # Alterne correct/incorrect avec probas calibrees-ish
        outcome = "correct" if i % 2 == 0 else "incorrect"
        prob = 0.6 + (0.3 if outcome == "correct" else -0.1)
        rows.append((
            i, 1, "AAPL", "bullish", 14, 100.0, baseline_date, target_date,
            resolved_date, 105.0, 0.05, outcome, 0.03, baseline_date, prob,
            0.1, "earnings", 0.5, "v1",
        ))
    empty_db.executemany(
        "INSERT INTO predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return empty_db


# ===== recalib_map =====


def test_recalib_map_cold_start_returns_none(empty_db: sqlite3.Connection) -> None:
    """DB vide -> fit_calibration_map retourne None (cold start safe)."""
    assert recalib_map.fit_calibration_map(empty_db) is None


def test_recalib_map_get_calibrated_returns_raw_when_cold(
    empty_db: sqlite3.Connection,
) -> None:
    """get_calibrated_prob retourne raw_prob si pas de map fittable."""
    assert recalib_map.get_calibrated_prob(empty_db, 0.7) == 0.7


def test_recalib_map_fits_when_data_sufficient(
    populated_db: sqlite3.Connection,
) -> None:
    """Avec n=40 (> MIN_N_FIT=30), fit retourne une CalibrationMap utilisable."""
    cmap = recalib_map.fit_calibration_map(populated_db, method="isotonic")
    assert cmap is not None
    assert cmap.n_fit == 40
    assert cmap.method == "isotonic"
    # Sanity : correct(0.7) doit etre dans [0, 1]
    corrected = cmap.correct(0.7)
    assert 0.001 <= corrected <= 0.999


# ===== base_rates =====


def test_base_rates_cold_start_returns_none(empty_db: sqlite3.Connection) -> None:
    """DB vide -> get_empirical_base_rate retourne None."""
    assert base_rates.get_empirical_base_rate(empty_db, "earnings", "bullish", 14) is None


def test_base_rates_returns_rate_when_sufficient(
    populated_db: sqlite3.Connection,
) -> None:
    """Avec n=40 bullish/earnings 14j -> retourne dict avec rate + CI Wilson."""
    out = base_rates.get_empirical_base_rate(
        populated_db, "earnings", "bullish", 14
    )
    assert out is not None
    assert out["n"] == 40
    assert 0.0 <= out["rate"] <= 1.0
    assert out["ci_lo"] <= out["rate"] <= out["ci_hi"]
    assert out["horizon_bucket"] == (8, 14)
    assert out["signal_type"] == "earnings"


def test_base_rates_horizon_out_of_range_returns_none(
    populated_db: sqlite3.Connection,
) -> None:
    """horizon=500 jours = hors HORIZON_BUCKETS -> None."""
    assert (
        base_rates.get_empirical_base_rate(populated_db, "earnings", "bullish", 500)
        is None
    )


# ===== outcome_context =====


def test_outcome_context_cold_start_returns_empty(empty_db: sqlite3.Connection) -> None:
    """DB vide -> build_outcome_context retourne string vide."""
    out = outcome_context.build_outcome_context(empty_db, "AAPL", "earnings")
    assert out == ""


def test_outcome_context_includes_analogues_when_available(
    populated_db: sqlite3.Connection,
) -> None:
    """Avec data suffisante -> markdown contient analogues + lessons."""
    out = outcome_context.build_outcome_context(populated_db, "AAPL", "earnings")
    assert "Analogues historiques" in out
    assert "AAPL bullish" in out
    assert "Pattern d'erreurs recents" in out  # lessons enabled at N >= 20


def test_outcome_context_skips_calibration_when_disabled(
    populated_db: sqlite3.Connection,
) -> None:
    """include_calibration_drift=False -> pas de section Calibration drift."""
    out = outcome_context.build_outcome_context(
        populated_db, "AAPL", "earnings", include_calibration_drift=False
    )
    assert "Calibration drift" not in out
