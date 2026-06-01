"""#41 -- Verifie que `migrated_db` (alembic upgrade head sur DB vide)
contient les colonnes critiques connues. Catch L8 drift a la racine :
si quelqu'un ajoute une colonne en code sans poser la migration, ou
inversement pose la migration sans MAJ le code, ce test fire.

Cf docs/LESSONS.md L8 : "Les test fixtures DB ne sont pas le schema de
production. Les fixtures DB tests sont derivees de la migration head
courante, pas commitees comme snapshots statiques."

Pattern : un test par table critique avec la liste des colonnes head
attendues. Si une migration ajoute une colonne, MAJ ce test EN MEME
TEMPS que le code consommateur -- le test fire sinon.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _columns(db: Path, table: str) -> set[str]:
    cx = sqlite3.connect(db)
    try:
        rows = cx.execute(f"PRAGMA table_info({table})").fetchall()
    finally:
        cx.close()
    return {r[1] for r in rows}


def _tables(db: Path) -> set[str]:
    cx = sqlite3.connect(db)
    try:
        rows = cx.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        cx.close()
    return {r[0] for r in rows}


# ─── Smoke : DB migrated existe + WAL ───────────────────────────────────


def test_migrated_db_has_expected_tables(migrated_db):
    """Apres alembic upgrade head, les tables critiques doivent exister."""
    tables = _tables(migrated_db)
    expected = {
        "positions", "theses", "decisions",
        "signals", "bias_events",
        "decision_counterfactual", "counterfactual_resolution",
        "predictions",  # cluster KPI #2
    }
    missing = expected - tables
    assert not missing, f"Tables manquantes apres alembic head : {missing}"


# ─── L8 sentinel : colonnes ajoutees par migrations recentes ────────────


def test_bias_events_has_note_tags_json(migrated_db):
    """Colonne `note_tags_json` ajoutee par migration 0023_bias_events.
    Cf L8 : hotfix `9a67e0c` -- la colonne n'avait jamais ete propagee
    aux fixtures tests, code prod silently failed pendant 40 jours."""
    cols = _columns(migrated_db, "bias_events")
    assert "note_tags_json" in cols, (
        "bias_events.note_tags_json absente. Drift L8 : check que "
        "scripts/alembic/versions/0023_bias_events.py est applique."
    )


def test_bias_events_has_position_event_id(migrated_db):
    """Colonne `position_event_id` ajoutee par migration 0025."""
    cols = _columns(migrated_db, "bias_events")
    assert "position_event_id" in cols, (
        "bias_events.position_event_id absente. Check migration 0025."
    )


def test_bias_events_status_enum_covers_canonical(migrated_db):
    """Status enum doit couvrir : open, resolved, void, thesis_invalidated,
    reentered, missing_data (cf intelligence/bias_events.py)."""
    cx = sqlite3.connect(migrated_db)
    try:
        # Tente d'inserer chaque status -- ceux invalides doivent fail
        # via CHECK constraint. Ceux valides doivent passer.
        canonical = {"open", "resolved", "void", "thesis_invalidated",
                     "reentered", "missing_data"}
        for s in canonical:
            try:
                cx.execute(
                    "INSERT INTO bias_events "
                    "(created_at, bias, action, decision_json, "
                    " counterfactual_json, status, source, horizon_days, "
                    " resolve_at) VALUES (?, 'lock_in', 'acted_on_bias', "
                    " '{}', '{}', ?, 'auto_detected', 30, ?)",
                    ("2026-06-01T00:00:00", s, "2026-07-01T00:00:00"),
                )
            except sqlite3.IntegrityError as e:
                pytest.fail(
                    f"status canonique '{s}' rejete par CHECK constraint : {e}. "
                    "Schema drift L8 : verifier migration bias_events."
                )
        cx.rollback()  # ne pas polluer
    finally:
        cx.close()


def test_decision_counterfactual_append_only_triggers(migrated_db):
    """Triggers append-only dcf_no_update + dcf_no_delete doivent exister."""
    cx = sqlite3.connect(migrated_db)
    try:
        triggers = {r[0] for r in cx.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name='decision_counterfactual'"
        ).fetchall()}
    finally:
        cx.close()
    expected = {"dcf_no_update", "dcf_no_delete"}
    missing = expected - triggers
    assert not missing, f"Triggers append-only manquants : {missing}"


def test_predictions_has_baseline_price(migrated_db):
    """Colonne baseline_price requise pour KPI #2 (cf fix #30)."""
    cols = _columns(migrated_db, "predictions")
    assert "baseline_price" in cols or "anchor_price" in cols, (
        "predictions.baseline_price absente. Check fix #30 + migration."
    )


# ─── Demo : fixture s'integre avec storage.DB_PATH ──────────────────────


def test_fixture_patches_storage_db_path(migrated_db):
    """Verifie que `migrated_db` patche bien storage.DB_PATH -> les
    consumers (ex. open_candidate, register_prediction) frappent
    automatiquement la DB temp."""
    from shared import storage
    assert storage.DB_PATH == migrated_db, (
        f"storage.DB_PATH {storage.DB_PATH} != fixture {migrated_db}"
    )
