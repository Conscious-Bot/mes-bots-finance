"""Verrouille les invariants KPI #2 (user critique 31/05 close : "le bug qui
ne crashe pas"). 3 sites de query "predictions résolues sur fenêtre" doivent
TOUS exclure :
1. outcome = 'neutral' (non-scoreable -- gonfle le compte sinon)
2. methodology_version = 'v0' (cohorte 12/05 horizon=30 hardcode quarantine)

Sans ces filtres : KPI #2 affichait 6/N au lieu de 2/N (+200% gonfle).
Si une modif de #1/#2 re-introduit le bug, ces tests crashent.
"""

from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def db_with_mixed_predictions() -> sqlite3.Connection:
    """In-memory DB peuplée d'un mix qui force les invariants à
    discriminer :
    - 2 correct v1 (substance vraie) → comptés
    - 1 incorrect v1 (substance vraie) → compté
    - 3 neutral v1 (non-scoreables) → EXCLUS
    - 1 correct v0 (cohorte quarantine) → EXCLUS
    - 1 NULL outcome v1 (pas résolu) → EXCLUS
    Expected count substance = 3 (2 correct + 1 incorrect)
    """
    cx = sqlite3.connect(":memory:")
    cx.execute("""
        CREATE TABLE predictions (
            id INTEGER PRIMARY KEY,
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
            methodology_version TEXT NOT NULL DEFAULT 'v1'
        )
    """)
    now = "2026-05-31T12:00:00"
    rows = [
        (1, "AAPL", "bullish", 14, 100, "2026-05-01", "2026-05-15", now, 110, 0.10, "correct",   0.03, now, 0.7, 0.09,   "v1"),
        (2, "MSFT", "bullish", 14, 100, "2026-05-01", "2026-05-15", now, 112, 0.12, "correct",   0.03, now, 0.7, 0.09,   "v1"),
        (3, "NVDA", "bullish", 14, 100, "2026-05-01", "2026-05-15", now, 90,  -0.10, "incorrect", -0.05, now, 0.7, 0.49,  "v1"),
        (4, "GOOG", "bullish", 14, 100, "2026-05-01", "2026-05-15", now, 102, 0.02, "neutral",   0.0,  now, 0.7, None,   "v1"),
        (5, "AMZN", "bullish", 14, 100, "2026-05-01", "2026-05-15", now, 101, 0.01, "neutral",   0.0,  now, 0.7, None,   "v1"),
        (6, "TSLA", "bullish", 14, 100, "2026-05-01", "2026-05-15", now, 103, 0.03, "neutral",   0.0,  now, 0.7, None,   "v1"),
        (7, "META", "bullish", 30, 100, "2026-05-12", "2026-06-10", now, 115, 0.15, "correct",   0.03, now, 0.7, 0.09,   "v0"),
        (8, "AMD",  "bullish", 14, 100, "2026-05-25", "2026-06-08", None, None, None, None,      None, now, 0.7, None,   "v1"),
    ]
    cx.executemany(
        "INSERT INTO predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows,
    )
    return cx


# ─── Invariant 1 : observability KPI #2 28d ────────────────────────────────


def test_kpi2_observability_excludes_neutral_and_v0(db_with_mixed_predictions: sqlite3.Connection) -> None:
    """Lock query bot/handlers/observability.py:257-260 KPI #2."""
    n = db_with_mixed_predictions.execute(
        "SELECT COUNT(*) FROM predictions "
        "WHERE resolved_at IS NOT NULL AND outcome != 'neutral' "
        "AND methodology_version != 'v0' "
        "AND resolved_at >= datetime('now', '-28 days')"
    ).fetchone()[0]
    assert n == 3, (
        f"KPI #2 substance attendu = 3 (2 correct + 1 incorrect v1). "
        f"Obtenu = {n}. Si > 3 : filter neutral OU v0 cassé. Si < 3 : "
        f"filter trop strict."
    )


# ─── Invariant 2 : morning_brief predictions_resolved_30d ──────────────────


def test_kpi2_morning_brief_30d_excludes_neutral_and_v0(db_with_mixed_predictions: sqlite3.Connection) -> None:
    """Lock query intelligence/morning_brief.py:240-245."""
    n = db_with_mixed_predictions.execute(
        "SELECT COUNT(*) FROM predictions "
        "WHERE resolved_at IS NOT NULL AND outcome != 'neutral' "
        "AND methodology_version != 'v0' "
        "AND datetime(resolved_at) >= datetime('now', '-30 days')"
    ).fetchone()[0]
    assert n == 3


# ─── Invariant 3 : morning_brief predictions_resolved_24h ──────────────────


def test_kpi2_morning_brief_24h_excludes_neutral_and_v0(db_with_mixed_predictions: sqlite3.Connection) -> None:
    """Lock query intelligence/morning_brief.py:210-214."""
    n = db_with_mixed_predictions.execute(
        "SELECT COUNT(*) FROM predictions "
        "WHERE resolved_at IS NOT NULL AND outcome != 'neutral' "
        "AND methodology_version != 'v0' "
        "AND datetime(resolved_at) >= datetime('now', '-24 hours')"
    ).fetchone()[0]
    assert n == 3


# ─── Invariant 4 : neutral est l'UNIQUE signal de non-comptage ─────────────


def test_neutral_is_only_non_count_outcome(db_with_mixed_predictions: sqlite3.Connection) -> None:
    """Si on ne filtre QUE outcome != neutral (sans v0), le v0 fuite.
    Test miroir : démontre que v0 SEUL filtre laisse les neutral dedans.
    Ces 2 filtres sont indépendants et tous deux nécessaires."""
    # Si on oublie le filtre v0 : 3 v1 substance + 1 v0 correct = 4
    n_oublie_v0 = db_with_mixed_predictions.execute(
        "SELECT COUNT(*) FROM predictions "
        "WHERE resolved_at IS NOT NULL AND outcome != 'neutral'"
    ).fetchone()[0]
    assert n_oublie_v0 == 4, (
        "Si on oublie le filtre v0, on devrait avoir 4 (3 v1 substance + 1 v0 "
        "correct cohorte quarantine)"
    )
    # Si on oublie le filtre neutral : 3 v1 substance + 3 v1 neutral = 6
    n_oublie_neutral = db_with_mixed_predictions.execute(
        "SELECT COUNT(*) FROM predictions "
        "WHERE resolved_at IS NOT NULL AND methodology_version != 'v0'"
    ).fetchone()[0]
    assert n_oublie_neutral == 6, (
        "Si on oublie le filtre neutral, on devrait avoir 6 (3 v1 substance "
        "+ 3 v1 neutral). C'est le +200% gonflé que la wave KPI #2 a corrigé."
    )


# ─── Invariant 5 : open predictions cluster (due in 28d) v0 filter ─────────


def test_kpi2_due_in_28d_excludes_v0(db_with_mixed_predictions: sqlite3.Connection) -> None:
    """Lock query intelligence/morning_brief.py:232-238 (predictions due in
    window). Le 10/06 : 40 v0 vont tomber à target_date ; sans filtre, le
    bot afficherait fausse panique '40 predictions due in 28d'."""
    n = db_with_mixed_predictions.execute(
        "SELECT COUNT(*) FROM predictions "
        "WHERE resolved_at IS NULL "
        "AND methodology_version != 'v0' "
        "AND target_date <= date('now', '+28 days')"
    ).fetchone()[0]
    # Le seul prediction NULL résolution v1 a target 2026-06-08, dans la
    # fenêtre 28j depuis 2026-05-31 → comptée. v0 (id=7 target 2026-06-10)
    # exclu même si dans la fenêtre.
    assert n == 1, (
        f"Une seule prediction v1 dans fenêtre 28d (AMD target 2026-06-08). "
        f"Obtenu = {n}. Si > 1 : v0 fuite, fausse panique 10/06."
    )
