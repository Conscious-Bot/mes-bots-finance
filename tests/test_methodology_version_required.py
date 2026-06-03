"""#98 ADR 014 hazard B : methodology_version is REQUIRED, never default.

Tests structurels (Python boundary + SQL constraint) qui garantissent que
NULLE prediction ne peut etre ecrite sans methodology_version explicite.
Defense en profondeur :
  - Layer 1 (Python boundary) : storage.insert_prediction raise ValueError
    si methodology_version est missing / vide / non-str.
  - Layer 2 (SQL constraint) : alembic 0028 retire le DEFAULT 'v1'. Un raw
    INSERT qui omettrait la colonne crash IntegrityError NOT NULL.

Sans ces deux verrous, le silent-mistag (default 'v1' qui masque v2) reste
possible : c'est exactement le bug que le doctrine resilience combat.

Spec user 03/06 (resilience phase B + ADR 014) :
  "DEFAULT 'v1' = silent-mistag vector quand v2 scorer ship -> explicit 'v2'
   + invariant test. Pre-#94 ship."

Pas property-based (control-flow + schema invariant). Pas e2e.
"""

from __future__ import annotations

import sqlite3

import pytest

from shared import storage

# ─── Layer 1 (Python boundary) : insert_prediction valide le param ───────


def test_insert_prediction_rejects_missing_methodology_version(migrated_db):
    """Sans methodology_version, la fonction doit raise TypeError (kwarg required)."""
    # L'omission de methodology_version est volontaire pour tester le contrat.
    with pytest.raises(TypeError, match="methodology_version"):
        storage.insert_prediction(  # type: ignore[call-arg]
            signal_id=1,
            ticker="NVDA",
            direction="bullish",
            horizon_days=28,
            baseline_price=140.0,
            baseline_date="2026-06-02",
            target_date="2026-06-30",
            probability_override=0.65,
        )


def test_insert_prediction_rejects_empty_methodology_version(migrated_db):
    """Empty string -> ValueError (defense vs caller qui passe '' bypass)."""
    with pytest.raises(ValueError, match="methodology_version is required"):
        storage.insert_prediction(
            signal_id=1,
            ticker="NVDA",
            direction="bullish",
            horizon_days=28,
            baseline_price=140.0,
            baseline_date="2026-06-02",
            target_date="2026-06-30",
            methodology_version="",
            probability_override=0.65,
        )


def test_insert_prediction_rejects_none_methodology_version(migrated_db):
    """None explicit -> ValueError (defense vs caller qui passe None bypass)."""
    with pytest.raises(ValueError, match="methodology_version is required"):
        storage.insert_prediction(
            signal_id=1,
            ticker="NVDA",
            direction="bullish",
            horizon_days=28,
            baseline_price=140.0,
            baseline_date="2026-06-02",
            target_date="2026-06-30",
            methodology_version=None,  # type: ignore[arg-type]
            probability_override=0.65,
        )


def test_insert_prediction_accepts_v2_explicit(migrated_db):
    """Happy path : 'v2' explicit -> persist OK."""
    cx = sqlite3.connect(migrated_db)
    cx.execute("INSERT INTO sources (name, type, credibility) VALUES ('s', 'newsletter', 0.7)")
    src_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities) "
        "VALUES (?, 't', '2026-06-02T10:00:00+00:00', '[\"NVDA\"]')",
        (src_id,),
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.commit()
    cx.close()

    # Monkey-pierce DB_PATH so insert_prediction targets the test DB.
    from shared import storage as stg_mod
    orig_path = stg_mod.DB_PATH
    stg_mod.DB_PATH = migrated_db
    try:
        pid = storage.insert_prediction(
            signal_id=sig_id,
            ticker="NVDA",
            direction="bullish",
            horizon_days=28,
            baseline_price=140.0,
            baseline_date="2026-06-02",
            target_date="2026-06-30",
            methodology_version="v2",
            probability_override=0.65,
        )
    finally:
        stg_mod.DB_PATH = orig_path
    assert pid is not None
    cx = sqlite3.connect(migrated_db)
    row = cx.execute(
        "SELECT methodology_version FROM predictions WHERE id = ?", (pid,)
    ).fetchone()
    cx.close()
    assert row[0] == "v2"


# ─── Layer 2 (SQL constraint) : column has no DEFAULT post-0028 ─────────


def test_predictions_schema_has_no_default_on_methodology_version(migrated_db):
    """Migration 0028 doit retirer DEFAULT 'v1'. Verification structurelle."""
    cx = sqlite3.connect(migrated_db)
    rows = cx.execute("PRAGMA table_info(predictions)").fetchall()
    cx.close()
    # PRAGMA table_info returns : (cid, name, type, notnull, dflt_value, pk)
    methodo_row = next(r for r in rows if r[1] == "methodology_version")
    notnull, dflt = methodo_row[3], methodo_row[4]
    assert notnull == 1, "methodology_version doit rester NOT NULL"
    assert dflt is None, (
        f"methodology_version DEFAULT doit etre None (migration 0028), "
        f"actuel: {dflt!r}. ADR 014 hazard B silent-mistag risk."
    )


def test_raw_insert_without_methodology_version_raises_integrity_error(migrated_db):
    """Garde-fou cote SQL : INSERT raw qui omet la colonne crash loud."""
    cx = sqlite3.connect(migrated_db)
    try:
        cx.execute("INSERT INTO sources (name, type, credibility) VALUES ('s2', 't', 0.5)")
        src_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
        cx.execute(
            "INSERT INTO signals (source_id, title, timestamp, entities) "
            "VALUES (?, 't', '2026-06-02T10:00:00+00:00', '[\"X\"]')",
            (src_id,),
        )
        sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="methodology_version"):
            cx.execute(
                "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
                "baseline_price, baseline_date, target_date, probability_at_creation) "
                "VALUES (?, 'X', 'bullish', 28, 100.0, '2026-06-02', '2026-06-30', 0.6)",
                (sig_id,),
            )
    finally:
        cx.close()


# ─── Round-trip : la migration preserve les valeurs existantes ──────────


def test_migration_preserves_existing_methodology_values(migrated_db):
    """Apres 0028, les rows v0 quarantine + v1 existants gardent leur valeur."""
    cx = sqlite3.connect(migrated_db)
    cx.execute("INSERT INTO sources (name, type, credibility) VALUES ('s3', 't', 0.5)")
    src_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities) "
        "VALUES (?, 't', '2026-06-02T10:00:00+00:00', '[\"X\"]')",
        (src_id,),
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Insert v0 quarantine et v1 archive explicite
    cx.execute(
        "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
        "baseline_price, baseline_date, target_date, methodology_version) "
        "VALUES (?, 'V0_TIK', 'bullish', 30, 100, '2026-05-12', '2026-06-10', 'v0')",
        (sig_id,),
    )
    cx.execute(
        "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
        "baseline_price, baseline_date, target_date, methodology_version) "
        "VALUES (?, 'V1_TIK', 'bullish', 28, 100, '2026-05-15', '2026-06-12', 'v1')",
        (sig_id,),
    )
    cx.commit()
    rows = cx.execute(
        "SELECT ticker, methodology_version FROM predictions "
        "WHERE ticker IN ('V0_TIK', 'V1_TIK') ORDER BY ticker"
    ).fetchall()
    cx.close()
    assert dict(rows) == {"V0_TIK": "v0", "V1_TIK": "v1"}
