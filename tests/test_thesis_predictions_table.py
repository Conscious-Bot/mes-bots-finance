"""Tests verrouillants table thesis_predictions (migrations 0052 + 0053).

Vérifie que les triggers MORDENT, pas juste qu'ils existent (distinction
déclaré-vs-appliqué que la session a apprise à ses dépens).

3 triggers à verrouiller :
1. pose_writeonce — UPDATE OF pose cols → RAISE
2. resolve_writeonce — re-résolution (OLD.resolved_at NOT NULL) → RAISE,
                        première résolution (NULL→valeur) → OK
3. no_delete — DELETE → RAISE

Fixture canonique : migrated_db de tests/conftest.py qui applique la
vraie chaîne migrations alembic (0001→head). L8 doctrine + #41 (01/06) :
fixtures dérivées de la migration courante, pas de hand-roll fictif.

Hand-roll précédent supprimé (red-team Olivier 11/06) : il dérivait
subtilement de la vraie migration (messages anglais courts vs français
longs) = 2-référentiels infra test interdit par SPEC §4.1. Source unique
= les fichiers de migration via storage.bootstrap_schema().
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest


# ============================================================
# Helper INSERT (passe par la passerelle storage.db() = L17)
# ============================================================


def _insert_pose(**kwargs):
    """Helper INSERT pose avec defaults sensés (SK Hynix scenario par défaut).

    Passe par storage.db() context manager (passerelle L17 unique).
    Retourne l'id de la ligne insérée.
    """
    from shared import storage
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
    with storage.db() as cx:
        cur = cx.execute(
            f"INSERT INTO thesis_predictions ({cols}) VALUES ({placeholders})",
            tuple(defaults.values()),
        )
        return cur.lastrowid


# ============================================================
# Structure tests (contre schéma réel post-0053)
# ============================================================


def test_table_has_pose_resolve_columns_and_unique_constraint(migrated_db):
    """Schema sain post-0053 : pose cols obligatoires, resolve cols nullable
    (incluant resolution_status), UNIQUE(ticker,asof,target)."""
    from shared import storage
    with storage.db() as cx:
        cols = {r[1]: r for r in cx.execute("PRAGMA table_info(thesis_predictions)").fetchall()}
    # Pose cols obligatoires (notnull=1)
    pose_required = ["ticker", "asof", "asof_price_native", "native_currency", "pt_consensus_raw",
                     "pt_consensus_currency", "pt_native_asof", "fx_at_asof", "your_target_native",
                     "your_delta_native_pct", "thesis_summary", "resolve_due_date"]
    for col in pose_required:
        assert col in cols, f"col {col} missing"
        assert cols[col][3] == 1, f"col {col} should be NOT NULL"
    # Resolve cols nullable — resolution_status ajouté par 0053
    for col in ["resolved_at", "resolve_price_native", "alpha_realized_pct", "direction_correct",
                "magnitude_score", "exclude_reason", "resolution_status"]:
        assert col in cols, f"col {col} missing (0053 ?)"
        assert cols[col][3] == 0, f"col {col} should be nullable"
    # UNIQUE constraint
    with storage.db() as cx:
        indexes = cx.execute("PRAGMA index_list(thesis_predictions)").fetchall()
    assert any(idx[2] == 1 for idx in indexes), "missing UNIQUE index"


def test_can_insert_pose_with_resolve_cols_null(migrated_db):
    """Insert d'une pose laisse resolve_* à NULL — pas pré-résolu."""
    from shared import storage
    _insert_pose()
    with storage.db() as cx:
        row = cx.execute(
            "SELECT resolved_at, resolve_price_native, alpha_realized_pct, resolution_status "
            "FROM thesis_predictions"
        ).fetchone()
    assert tuple(row) == (None, None, None, None)


def test_check_constraints_block_invalid_inputs(migrated_db):
    """CHECK contraintes prix > 0 / confidence in (0,1] / direction_correct in {0,1}."""
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pose(asof_price_native=-100.0)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pose(asof_price_native=1.0, ticker="X", confidence=1.5)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pose(asof_price_native=1.0, ticker="X", fx_at_asof=0.0)


# ============================================================
# Trigger 1 : pose columns immutables
# (match= sur substring stable du vrai message FR)
# ============================================================


def test_trigger_pose_writeonce_raises_on_update_of_ticker(migrated_db):
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        cx.execute("UPDATE thesis_predictions SET ticker='HACKED' WHERE id=?", (pid,))


def test_trigger_pose_writeonce_raises_on_update_of_pt_native(migrated_db):
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        cx.execute("UPDATE thesis_predictions SET pt_native_asof=9999999 WHERE id=?", (pid,))


def test_trigger_pose_writeonce_raises_on_update_of_target(migrated_db):
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        cx.execute("UPDATE thesis_predictions SET your_target_native=999 WHERE id=?", (pid,))


def test_trigger_pose_writeonce_raises_on_update_of_notes(migrated_db):
    """notes mutable serait porte dérobée à l'historique → immutable comme pose."""
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        cx.execute("UPDATE thesis_predictions SET notes='added later' WHERE id=?", (pid,))


# ============================================================
# Trigger 2 : resolve write-once (NULL→valeur OK, valeur→valeur RAISE)
# ============================================================


def test_trigger_resolve_first_pass_allowed_when_resolved_at_null(migrated_db):
    """Première résolution : OLD.resolved_at IS NULL → WHEN false → pass.

    UPDATE atomique tous resolve cols (writer contrat). Inclut
    resolution_status='resolved' (0053).
    """
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx:
        cx.execute("""
            UPDATE thesis_predictions SET
                resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
                direction_correct = ?, magnitude_score = ?, exclude_reason = NULL,
                resolution_status = 'resolved'
            WHERE id = ?
        """, (datetime.now(UTC).isoformat(), 2_500_000.0, 20.5, 1, 0.125, pid))
        row = cx.execute(
            "SELECT direction_correct, alpha_realized_pct, resolution_status "
            "FROM thesis_predictions WHERE id=?", (pid,)
        ).fetchone()
    assert tuple(row) == (1, 20.5, "resolved")


def test_trigger_resolve_writeonce_raises_on_second_resolve(migrated_db):
    """Re-résolution : OLD.resolved_at IS NOT NULL → trigger 2 mord (write-once)."""
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx:
        cx.execute("""
            UPDATE thesis_predictions SET
                resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
                direction_correct = ?, magnitude_score = ?, exclude_reason = NULL,
                resolution_status = 'resolved'
            WHERE id = ?
        """, ("2027-06-10T09:00:00", 2_500_000.0, 20.5, 1, 0.125, pid))
    # Tentative re-resolution → RAISE
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError, match="write-once"):
        cx.execute("UPDATE thesis_predictions SET alpha_realized_pct=999 WHERE id=?", (pid,))


def test_trigger_resolve_writeonce_blocks_exclude_reason_post_resolve(migrated_db):
    """exclude_reason est dans la liste trigger 2 → bloqué post-résolution."""
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx:
        cx.execute("""
            UPDATE thesis_predictions SET
                resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
                direction_correct = NULL, magnitude_score = NULL, exclude_reason = 'neutral',
                resolution_status = 'resolved'
            WHERE id = ?
        """, ("2027-06-10T09:00:00", 2_500_000.0, 0.5, pid))
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError, match="write-once"):
        cx.execute("UPDATE thesis_predictions SET exclude_reason='no_bet' WHERE id=?", (pid,))


def test_trigger_pose_blocks_pose_col_update_even_post_resolve(migrated_db):
    """Disjonction triggers : post-résolution, UPDATE pose col → trigger 1 mord."""
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx:
        cx.execute("""
            UPDATE thesis_predictions SET
                resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
                direction_correct = ?, magnitude_score = ?, exclude_reason = NULL,
                resolution_status = 'resolved'
            WHERE id = ?
        """, ("2027-06-10T09:00:00", 2_500_000.0, 20.5, 1, 0.125, pid))
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        cx.execute("UPDATE thesis_predictions SET ticker='HACKED' WHERE id=?", (pid,))


# ============================================================
# Trigger 3 : DELETE bloqué
# ============================================================


def test_trigger_no_delete_raises_on_any_delete(migrated_db):
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError, match="DELETE interdit"):
        cx.execute("DELETE FROM thesis_predictions WHERE id=?", (pid,))


def test_trigger_no_delete_raises_after_resolve(migrated_db):
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx:
        cx.execute("""
            UPDATE thesis_predictions SET
                resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
                direction_correct = ?, magnitude_score = ?, exclude_reason = NULL,
                resolution_status = 'resolved'
            WHERE id = ?
        """, ("2027-06-10T09:00:00", 2_500_000.0, 20.5, 1, 0.125, pid))
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError, match="DELETE interdit"):
        cx.execute("DELETE FROM thesis_predictions WHERE id=?", (pid,))


# ============================================================
# UNIQUE constraint
# ============================================================


def test_unique_constraint_blocks_double_pose_same_target(migrated_db):
    _insert_pose()
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pose()  # même ticker / asof / target → conflict


def test_unique_constraint_allows_different_targets_same_asof(migrated_db):
    """Partial + full sur même thèse autorisé."""
    from shared import storage
    _insert_pose(your_target_native=2_650_000.0, your_delta_native_pct=15.2)
    _insert_pose(your_target_native=3_800_000.0, your_delta_native_pct=72.2)
    with storage.db() as cx:
        n = cx.execute("SELECT COUNT(*) FROM thesis_predictions").fetchone()[0]
    assert n == 2


def test_unique_constraint_allows_yearly_repose_for_long_thesis(migrated_db):
    """Décision C : thèse longue = paris annuels séquentiels (asof différent)."""
    from shared import storage
    _insert_pose(asof="2026-06-10", resolve_due_date="2027-06-10")
    _insert_pose(asof="2027-06-10", resolve_due_date="2028-06-10")
    with storage.db() as cx:
        n = cx.execute("SELECT COUNT(*) FROM thesis_predictions").fetchone()[0]
    assert n == 2


# ============================================================
# Catch D — anti-dérive trigger 2 recréé en 0053
# ============================================================


def test_d1_trigger_resolve_writeonce_still_bites_after_0053(migrated_db):
    """D-1 : verrou comportemental — la recréation 0053 préserve la sémantique
    re-resolve mord. Re-run du test 0052 contre l'état post-0053 (vraie
    migration, fixture canonique migrated_db)."""
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx:
        cx.execute("""
            UPDATE thesis_predictions SET
                resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
                direction_correct = ?, magnitude_score = ?, exclude_reason = NULL,
                resolution_status = 'resolved'
            WHERE id = ?
        """, ("2027-06-10T09:00", 2_500_000.0, 20.5, 1, 0.125, pid))
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError, match="write-once"):
        cx.execute("UPDATE thesis_predictions SET alpha_realized_pct=999 WHERE id=?", (pid,))


def test_d2_trigger_2_protects_resolution_status_post_resolve(migrated_db):
    """D-2 : verrou anti-dérive — resolution_status dans la liste UPDATE OF
    du trigger 2 recréé en 0053. UPDATE resolution_status seul sur ligne
    résolue → ABORT (sinon mutable post-resolve = bug schéma)."""
    from shared import storage
    pid = _insert_pose()
    with storage.db() as cx:
        cx.execute("""
            UPDATE thesis_predictions SET
                resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
                direction_correct = ?, magnitude_score = NULL, exclude_reason = NULL,
                resolution_status = 'resolved'
            WHERE id = ?
        """, ("2027-06-10T09:00", 2_500_000.0, 20.5, 1, pid))
    # Tenter de modifier resolution_status seul post-resolve → trigger 2 mord
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError, match="write-once"):
        cx.execute("UPDATE thesis_predictions SET resolution_status='abandoned' WHERE id=?", (pid,))


def test_d3_resolution_status_check_constraint(migrated_db):
    """D-3 (bonus structure) : CHECK contraint resolution_status ∈ {resolved,abandoned}."""
    from shared import storage
    pid = _insert_pose()
    # Valeur hors enum → IntegrityError
    with storage.db() as cx, pytest.raises(sqlite3.IntegrityError):
        cx.execute("""
            UPDATE thesis_predictions SET
                resolved_at = ?, resolve_price_native = ?, alpha_realized_pct = ?,
                direction_correct = ?, magnitude_score = NULL, exclude_reason = NULL,
                resolution_status = 'invalid_value'
            WHERE id = ?
        """, ("2027-06-10T09:00", 2_500_000.0, 20.5, 1, pid))
