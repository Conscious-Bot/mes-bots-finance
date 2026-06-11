"""Tests verrouillants table thesis_predictions (migration 0052).

Vérifie que les triggers MORDENT, pas juste qu'ils existent (distinction
déclaré-vs-appliqué que la session a apprise à ses dépens).

3 triggers à verrouiller :
1. pose_writeonce — UPDATE OF pose cols → RAISE
2. resolve_writeonce — re-résolution (OLD.resolved_at NOT NULL) → RAISE,
                        première résolution (NULL→valeur) → OK
3. no_delete — DELETE → RAISE

Pattern fixture in-memory (calque tests/test_transactions_ledger.py).
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest


# ============================================================
# Fixture : in-memory SQLite avec schema 0052
# ============================================================


@pytest.fixture
def alpha_db():
    """In-memory SQLite avec schema thesis_predictions + 3 triggers (mig 0052)."""
    cx = sqlite3.connect(":memory:")
    cx.execute("""
        CREATE TABLE thesis_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            asof DATE NOT NULL,
            asof_price_native REAL NOT NULL CHECK(asof_price_native > 0),
            native_currency TEXT NOT NULL,
            pt_consensus_raw REAL NOT NULL CHECK(pt_consensus_raw > 0),
            pt_consensus_currency TEXT NOT NULL,
            pt_native_asof REAL NOT NULL CHECK(pt_native_asof > 0),
            fx_at_asof REAL NOT NULL CHECK(fx_at_asof > 0),
            your_target_native REAL NOT NULL CHECK(your_target_native > 0),
            your_delta_native_pct REAL NOT NULL,
            confidence REAL CHECK(confidence IS NULL OR (confidence > 0 AND confidence <= 1)),
            thesis_summary TEXT NOT NULL,
            resolve_due_date DATE NOT NULL,
            source TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            resolved_at TEXT,
            resolve_price_native REAL CHECK(resolve_price_native IS NULL OR resolve_price_native > 0),
            alpha_realized_pct REAL,
            direction_correct INTEGER CHECK(direction_correct IS NULL OR direction_correct IN (0, 1)),
            magnitude_score REAL CHECK(magnitude_score IS NULL OR (magnitude_score >= 0 AND magnitude_score <= 1)),
            exclude_reason TEXT CHECK(exclude_reason IS NULL OR exclude_reason IN ('neutral', 'no_bet')),
            UNIQUE(ticker, asof, your_target_native)
        )
    """)
    cx.execute("CREATE INDEX idx_thesis_predictions_due ON thesis_predictions(resolve_due_date) WHERE resolved_at IS NULL")
    cx.execute("CREATE INDEX idx_thesis_predictions_ticker_asof ON thesis_predictions(ticker, asof)")
    cx.execute("""
        CREATE TRIGGER thesis_predictions_pose_writeonce
        BEFORE UPDATE OF
            ticker, asof, asof_price_native, native_currency,
            pt_consensus_raw, pt_consensus_currency, pt_native_asof, fx_at_asof,
            your_target_native, your_delta_native_pct, confidence, thesis_summary,
            resolve_due_date, source, notes, created_at
        ON thesis_predictions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'pose columns immutable');
        END
    """)
    cx.execute("""
        CREATE TRIGGER thesis_predictions_resolve_writeonce
        BEFORE UPDATE OF
            resolved_at, resolve_price_native, alpha_realized_pct,
            direction_correct, magnitude_score, exclude_reason
        ON thesis_predictions
        FOR EACH ROW
        WHEN OLD.resolved_at IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'resolve write-once : already resolved');
        END
    """)
    cx.execute("""
        CREATE TRIGGER thesis_predictions_no_delete
        BEFORE DELETE ON thesis_predictions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'append-only : DELETE forbidden');
        END
    """)
    cx.commit()
    yield cx
    cx.close()


def _insert_pose(cx, **kwargs):
    """Helper INSERT pose avec defaults sensés (SK Hynix scenario par défaut)."""
    defaults = {
        "ticker": "000660.KS",
        "asof": "2026-06-10",
        "asof_price_native": 2_077_000.0,
        "native_currency": "KRW",
        "pt_consensus_raw": 2_300_000.0,
        "pt_consensus_currency": "KRW",
        "pt_native_asof": 2_300_000.0,
        "fx_at_asof": 1.0,
        "your_target_native": 3_800_000.0,
        "your_delta_native_pct": 72.2,
        "confidence": None,
        "thesis_summary": "SK Hynix HBM gen5 bull thesis vs blended consensus",
        "resolve_due_date": "2027-06-10",
        "source": "sweep_133",
        "notes": None,
    }
    defaults.update(kwargs)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" * len(defaults))
    cx.execute(f"INSERT INTO thesis_predictions ({cols}) VALUES ({placeholders})", tuple(defaults.values()))
    cx.commit()


# ============================================================
# Structure tests
# ============================================================


def test_table_has_pose_resolve_columns_and_unique_constraint(alpha_db):
    """Schema sain : pose cols obligatoires, resolve cols nullable, UNIQUE(ticker,asof,target)."""
    cols = {r[1]: r for r in alpha_db.execute("PRAGMA table_info(thesis_predictions)").fetchall()}
    # Pose cols obligatoires (notnull=1)
    pose_required = ["ticker", "asof", "asof_price_native", "native_currency", "pt_consensus_raw",
                     "pt_consensus_currency", "pt_native_asof", "fx_at_asof", "your_target_native",
                     "your_delta_native_pct", "thesis_summary", "resolve_due_date"]
    for col in pose_required:
        assert col in cols, f"col {col} missing"
        assert cols[col][3] == 1, f"col {col} should be NOT NULL"
    # Resolve cols nullable (notnull=0)
    for col in ["resolved_at", "resolve_price_native", "alpha_realized_pct", "direction_correct",
                "magnitude_score", "exclude_reason"]:
        assert col in cols, f"col {col} missing"
        assert cols[col][3] == 0, f"col {col} should be nullable"
    # UNIQUE constraint
    indexes = alpha_db.execute("PRAGMA index_list(thesis_predictions)").fetchall()
    assert any(idx[2] == 1 for idx in indexes), "missing UNIQUE index"


def test_can_insert_pose_with_resolve_cols_null(alpha_db):
    """Insert d'une pose laisse resolve_* à NULL — pas pré-résolu."""
    _insert_pose(alpha_db)
    row = alpha_db.execute("SELECT resolved_at, resolve_price_native, alpha_realized_pct FROM thesis_predictions").fetchone()
    assert row == (None, None, None)


def test_check_constraints_block_invalid_inputs(alpha_db):
    """CHECK contraintes prix > 0 / confidence in (0,1] / direction_correct in {0,1}."""
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pose(alpha_db, asof_price_native=-100.0)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pose(alpha_db, asof_price_native=1.0, ticker="X", confidence=1.5)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pose(alpha_db, asof_price_native=1.0, ticker="X", fx_at_asof=0.0)


# ============================================================
# Trigger 1 : pose columns immutables
# ============================================================


def test_trigger_pose_writeonce_raises_on_update_of_ticker(alpha_db):
    """UPDATE ticker post-insert → RAISE (pose immuable)."""
    _insert_pose(alpha_db)
    with pytest.raises(sqlite3.IntegrityError, match="pose columns immutable"):
        alpha_db.execute("UPDATE thesis_predictions SET ticker='HACKED' WHERE id=1")


def test_trigger_pose_writeonce_raises_on_update_of_pt_native(alpha_db):
    """UPDATE pt_native_asof post-insert → RAISE (le mètre est figé à asof)."""
    _insert_pose(alpha_db)
    with pytest.raises(sqlite3.IntegrityError, match="pose columns immutable"):
        alpha_db.execute("UPDATE thesis_predictions SET pt_native_asof=9999999 WHERE id=1")


def test_trigger_pose_writeonce_raises_on_update_of_target(alpha_db):
    """UPDATE your_target_native post-insert → RAISE (le pari est figé)."""
    _insert_pose(alpha_db)
    with pytest.raises(sqlite3.IntegrityError, match="pose columns immutable"):
        alpha_db.execute("UPDATE thesis_predictions SET your_target_native=999 WHERE id=1")


def test_trigger_pose_writeonce_raises_on_update_of_notes(alpha_db):
    """UPDATE notes post-insert → RAISE (notes mutable serait porte dérobée à l'historique)."""
    _insert_pose(alpha_db)
    with pytest.raises(sqlite3.IntegrityError, match="pose columns immutable"):
        alpha_db.execute("UPDATE thesis_predictions SET notes='added later' WHERE id=1")


# ============================================================
# Trigger 2 : resolve write-once (NULL→valeur OK, valeur→valeur RAISE)
# ============================================================


def test_trigger_resolve_first_pass_allowed_when_resolved_at_null(alpha_db):
    """Première résolution : OLD.resolved_at IS NULL → WHEN false → pass.

    Le writer (pièce 3) doit faire un UPDATE atomique (tous resolve cols
    en une fois) pour respecter ce contrat.
    """
    _insert_pose(alpha_db)
    alpha_db.execute("""
        UPDATE thesis_predictions SET
            resolved_at = ?,
            resolve_price_native = ?,
            alpha_realized_pct = ?,
            direction_correct = ?,
            magnitude_score = ?,
            exclude_reason = NULL
        WHERE id=1
    """, (datetime.utcnow().isoformat(), 2_500_000.0, 20.5, 1, 0.125))
    alpha_db.commit()
    row = alpha_db.execute("SELECT direction_correct, alpha_realized_pct FROM thesis_predictions").fetchone()
    assert row == (1, 20.5)


def test_trigger_resolve_writeonce_raises_on_second_resolve(alpha_db):
    """Re-résolution : OLD.resolved_at IS NOT NULL → WHEN true → RAISE."""
    _insert_pose(alpha_db)
    # 1ère résolution OK
    alpha_db.execute("""
        UPDATE thesis_predictions SET
            resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
            direction_correct = ?, magnitude_score = ?, exclude_reason = NULL
        WHERE id=1
    """, ("2027-06-10T09:00:00", 2_500_000.0, 20.5, 1, 0.125))
    alpha_db.commit()
    # Tentative de re-résolution → RAISE
    with pytest.raises(sqlite3.IntegrityError, match="already resolved"):
        alpha_db.execute("UPDATE thesis_predictions SET alpha_realized_pct=999 WHERE id=1")


def test_trigger_resolve_writeonce_blocks_exclude_reason_post_resolve(alpha_db):
    """exclude_reason est dans la liste trigger 2 → bloqué post-résolution."""
    _insert_pose(alpha_db)
    alpha_db.execute("""
        UPDATE thesis_predictions SET
            resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
            direction_correct = NULL, magnitude_score = NULL, exclude_reason = 'neutral'
        WHERE id=1
    """, ("2027-06-10T09:00:00", 2_500_000.0, 0.5))
    alpha_db.commit()
    with pytest.raises(sqlite3.IntegrityError, match="already resolved"):
        alpha_db.execute("UPDATE thesis_predictions SET exclude_reason='no_bet' WHERE id=1")


def test_trigger_pose_blocks_pose_col_update_even_post_resolve(alpha_db):
    """Disjonction triggers : post-résolution, UPDATE pose col → trigger 1 mord (pas trigger 2)."""
    _insert_pose(alpha_db)
    # Résoudre
    alpha_db.execute("""
        UPDATE thesis_predictions SET
            resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
            direction_correct = ?, magnitude_score = ?, exclude_reason = NULL
        WHERE id=1
    """, ("2027-06-10T09:00:00", 2_500_000.0, 20.5, 1, 0.125))
    alpha_db.commit()
    # Tentative UPDATE pose col → trigger 1 mord
    with pytest.raises(sqlite3.IntegrityError, match="pose columns immutable"):
        alpha_db.execute("UPDATE thesis_predictions SET ticker='HACKED' WHERE id=1")


# ============================================================
# Trigger 3 : DELETE bloqué
# ============================================================


def test_trigger_no_delete_raises_on_any_delete(alpha_db):
    """DELETE → RAISE, même post-résolution."""
    _insert_pose(alpha_db)
    with pytest.raises(sqlite3.IntegrityError, match="DELETE forbidden"):
        alpha_db.execute("DELETE FROM thesis_predictions WHERE id=1")


def test_trigger_no_delete_raises_after_resolve(alpha_db):
    """DELETE post-résolution → RAISE (append-only strict, l'historique reste)."""
    _insert_pose(alpha_db)
    alpha_db.execute("""
        UPDATE thesis_predictions SET
            resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
            direction_correct = ?, magnitude_score = ?, exclude_reason = NULL
        WHERE id=1
    """, ("2027-06-10T09:00:00", 2_500_000.0, 20.5, 1, 0.125))
    alpha_db.commit()
    with pytest.raises(sqlite3.IntegrityError, match="DELETE forbidden"):
        alpha_db.execute("DELETE FROM thesis_predictions WHERE id=1")


# ============================================================
# UNIQUE constraint
# ============================================================


def test_unique_constraint_blocks_double_pose_same_target(alpha_db):
    """UNIQUE(ticker, asof, your_target_native) bloque la double pose identique."""
    _insert_pose(alpha_db)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pose(alpha_db)  # même ticker / asof / target → conflict


def test_unique_constraint_allows_different_targets_same_asof(alpha_db):
    """Plusieurs targets sur même ticker/asof autorisé (partial + full sur même thèse)."""
    _insert_pose(alpha_db, your_target_native=2_650_000.0, your_delta_native_pct=15.2)
    _insert_pose(alpha_db, your_target_native=3_800_000.0, your_delta_native_pct=72.2)
    n = alpha_db.execute("SELECT COUNT(*) FROM thesis_predictions").fetchone()[0]
    assert n == 2


def test_unique_constraint_allows_yearly_repose_for_long_thesis(alpha_db):
    """Décision C : thèse longue = paris annuels séquentiels (asof différent)."""
    _insert_pose(alpha_db, asof="2026-06-10", resolve_due_date="2027-06-10")
    _insert_pose(alpha_db, asof="2027-06-10", resolve_due_date="2028-06-10")
    n = alpha_db.execute("SELECT COUNT(*) FROM thesis_predictions").fetchone()[0]
    assert n == 2
