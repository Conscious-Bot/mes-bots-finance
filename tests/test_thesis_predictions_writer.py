"""Tests pièce 3 — writers thesis_predictions (SPEC §2.2 + décisions A/B/C/D/E).

Vérifie :
- Mapping classify → DB (4 cas + None refusé)
- Fail-closed à la pose : no_bet skipped, UNIQUE handled
- Resolve atomique : 1 UPDATE passe, splits mordus par trigger 2
- Round-trip insert → get_due → update_resolve

Pattern : monkey-patch DB_PATH vers une in-memory shared sqlite file
puis appliquer le schema 0052 directement.
"""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest


def _apply_0052_schema(db_path: Path) -> None:
    """Applique le schema 0052 dans une DB fraîche (calque migration upgrade)."""
    cx = sqlite3.connect(str(db_path))
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
    cx.execute("""
        CREATE TRIGGER thesis_predictions_pose_writeonce
        BEFORE UPDATE OF
            ticker, asof, asof_price_native, native_currency,
            pt_consensus_raw, pt_consensus_currency, pt_native_asof, fx_at_asof,
            your_target_native, your_delta_native_pct, confidence, thesis_summary,
            resolve_due_date, source, notes, created_at
        ON thesis_predictions
        FOR EACH ROW
        BEGIN SELECT RAISE(ABORT, 'pose immutable'); END
    """)
    cx.execute("""
        CREATE TRIGGER thesis_predictions_resolve_writeonce
        BEFORE UPDATE OF resolved_at, resolve_price_native, alpha_realized_pct,
            direction_correct, magnitude_score, exclude_reason
        ON thesis_predictions
        FOR EACH ROW WHEN OLD.resolved_at IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'already resolved'); END
    """)
    cx.execute("""
        CREATE TRIGGER thesis_predictions_no_delete
        BEFORE DELETE ON thesis_predictions
        FOR EACH ROW
        BEGIN SELECT RAISE(ABORT, 'delete forbidden'); END
    """)
    # bot_events pour log_event
    cx.execute("""
        CREATE TABLE bot_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details TEXT
        )
    """)
    cx.commit()
    cx.close()


@pytest.fixture
def writer_db(monkeypatch, tmp_path):
    """DB sqlite temporaire isolée + schema 0052 + monkey-patch DB_PATH.

    Le writer utilise shared.storage.db() context manager qui résout DB_PATH
    dynamiquement à chaque appel → un seul monkey-patch sur storage suffit.
    """
    db_path = tmp_path / "test_alpha.db"
    _apply_0052_schema(db_path)
    import shared.storage
    monkeypatch.setattr(shared.storage, "DB_PATH", db_path)
    return db_path


def _pose_kwargs(**overrides):
    """SK Hynix scenario par défaut, override possible."""
    base = dict(
        ticker="000660.KS",
        asof=date(2026, 6, 10),
        asof_price_native=2_077_000.0,
        native_currency="KRW",
        pt_consensus_raw=2_300_000.0,
        pt_consensus_currency="KRW",
        pt_native_asof=2_300_000.0,
        fx_at_asof=1.0,
        your_target_native=3_800_000.0,
        your_delta_native_pct=72.2,
        thesis_summary="SK Hynix HBM gen5 bull thesis",
        resolve_due_date=date(2027, 6, 10),
        source="sweep_133",
    )
    base.update(overrides)
    return base


# ============================================================
# Mapping classify → DB
# ============================================================


def test_map_classify_correct():
    from shared.thesis_predictions_writer import _map_classify_to_db
    assert _map_classify_to_db("correct") == (1, None)


def test_map_classify_incorrect():
    from shared.thesis_predictions_writer import _map_classify_to_db
    assert _map_classify_to_db("incorrect") == (0, None)


def test_map_classify_neutral():
    from shared.thesis_predictions_writer import _map_classify_to_db
    assert _map_classify_to_db("neutral") == (None, "neutral")


def test_map_classify_no_bet_defensive():
    """no_bet ne devrait jamais arriver ici (gate à la pose) mais le mapping
    est défensif au cas où mode B futur."""
    from shared.thesis_predictions_writer import _map_classify_to_db
    assert _map_classify_to_db("no_bet") == (None, "no_bet")


def test_map_classify_unknown_raises():
    from shared.thesis_predictions_writer import _map_classify_to_db
    with pytest.raises(ValueError, match="hors enum"):
        _map_classify_to_db("hacked_value")


# ============================================================
# insert_thesis_pose — fail-closed gates
# ============================================================


def test_insert_pose_succeeds_for_real_bet(writer_db):
    from shared.thesis_predictions_writer import insert_thesis_pose
    pred_id = insert_thesis_pose(**_pose_kwargs())
    assert pred_id is not None
    assert pred_id > 0


def test_insert_pose_skips_no_bet(writer_db):
    """Gate no_bet : |delta| < ε_delta=1.0 → skip, log event, return None."""
    from shared.thesis_predictions_writer import insert_thesis_pose
    pred_id = insert_thesis_pose(**_pose_kwargs(your_delta_native_pct=0.5))
    assert pred_id is None
    # Verify event logged
    cx = sqlite3.connect(str(writer_db))
    rows = cx.execute("SELECT event_type FROM bot_events WHERE event_type='no_variant_view_at_pose'").fetchall()
    assert len(rows) == 1
    cx.close()


def test_insert_pose_skips_no_bet_symmetric_negative(writer_db):
    """Gate no_bet symétrique : |-0.5%| < ε_delta = no_bet aussi."""
    from shared.thesis_predictions_writer import insert_thesis_pose
    assert insert_thesis_pose(**_pose_kwargs(your_delta_native_pct=-0.5)) is None


def test_insert_pose_handles_unique_collision(writer_db):
    """Double pose même (ticker, asof, target) → 2e return None + log dupe."""
    from shared.thesis_predictions_writer import insert_thesis_pose
    id1 = insert_thesis_pose(**_pose_kwargs())
    assert id1 is not None
    id2 = insert_thesis_pose(**_pose_kwargs())
    assert id2 is None
    # Verify dupe event logged
    cx = sqlite3.connect(str(writer_db))
    rows = cx.execute("SELECT event_type FROM bot_events WHERE event_type='thesis_pose_duplicate'").fetchall()
    assert len(rows) == 1
    cx.close()


def test_insert_pose_allows_multi_target_same_asof(writer_db):
    """Partial + full sur même asof = 2 lignes distinctes."""
    from shared.thesis_predictions_writer import insert_thesis_pose
    id1 = insert_thesis_pose(**_pose_kwargs(your_target_native=2_650_000.0, your_delta_native_pct=15.2))
    id2 = insert_thesis_pose(**_pose_kwargs(your_target_native=3_800_000.0, your_delta_native_pct=72.2))
    assert id1 is not None and id2 is not None and id1 != id2


# ============================================================
# get_due_thesis_predictions
# ============================================================


def test_get_due_returns_only_due_and_unresolved(writer_db):
    from shared.thesis_predictions_writer import get_due_thesis_predictions, insert_thesis_pose
    today = date(2027, 6, 10)
    # Due (resolve_due_date <= today)
    id1 = insert_thesis_pose(**_pose_kwargs(resolve_due_date=date(2027, 1, 1)))
    # Not yet due
    id2 = insert_thesis_pose(**_pose_kwargs(
        ticker="CCJ", asof=date(2026, 12, 1), resolve_due_date=date(2027, 12, 1),
        native_currency="USD", pt_consensus_currency="USD",
        pt_consensus_raw=138.0, pt_native_asof=138.0,
        asof_price_native=105.0, your_target_native=155.0, your_delta_native_pct=16.0,
        thesis_summary="CCJ uranium supercycle",
    ))
    due = get_due_thesis_predictions(today=today)
    ids = {r["id"] for r in due}
    assert id1 in ids
    assert id2 not in ids


def test_get_due_excludes_already_resolved(writer_db):
    from shared.thesis_predictions_writer import (
        get_due_thesis_predictions, insert_thesis_pose, update_thesis_resolve_fields,
    )
    id1 = insert_thesis_pose(**_pose_kwargs(resolve_due_date=date(2027, 1, 1)))
    # Résoudre
    update_thesis_resolve_fields(
        prediction_id=id1, resolve_price_native=3_000_000.0,
        alpha_realized_pct=33.7, classify_result="correct", magnitude_score=0.117,
    )
    due = get_due_thesis_predictions(today=date(2027, 6, 10))
    assert all(r["id"] != id1 for r in due)


# ============================================================
# update_thesis_resolve_fields — atomic + classify mapping
# ============================================================


def test_resolve_atomic_writes_all_fields_at_once(writer_db):
    from shared.thesis_predictions_writer import insert_thesis_pose, update_thesis_resolve_fields
    pred_id = insert_thesis_pose(**_pose_kwargs())
    ok = update_thesis_resolve_fields(
        prediction_id=pred_id, resolve_price_native=3_000_000.0,
        alpha_realized_pct=33.7, classify_result="correct", magnitude_score=0.117,
    )
    assert ok is True
    cx = sqlite3.connect(str(writer_db))
    row = cx.execute(
        "SELECT resolved_at, resolve_price_native, alpha_realized_pct, "
        "direction_correct, magnitude_score, exclude_reason "
        "FROM thesis_predictions WHERE id=?", (pred_id,)
    ).fetchone()
    assert row[0] is not None  # resolved_at set
    assert row[1] == 3_000_000.0
    assert row[2] == 33.7
    assert row[3] == 1  # correct → 1
    assert row[4] == 0.117
    assert row[5] is None  # no exclude
    cx.close()


def test_resolve_neutral_sets_exclude_reason(writer_db):
    from shared.thesis_predictions_writer import insert_thesis_pose, update_thesis_resolve_fields
    pred_id = insert_thesis_pose(**_pose_kwargs())
    update_thesis_resolve_fields(
        prediction_id=pred_id, resolve_price_native=2_310_000.0,
        alpha_realized_pct=0.5, classify_result="neutral",  # |alpha|<1%
    )
    cx = sqlite3.connect(str(writer_db))
    row = cx.execute(
        "SELECT direction_correct, exclude_reason FROM thesis_predictions WHERE id=?",
        (pred_id,)
    ).fetchone()
    assert row[0] is None  # neutral → direction_correct NULL
    assert row[1] == "neutral"
    cx.close()


def test_resolve_raises_on_none_classify(writer_db):
    """classify=None signifie alpha incalculable → ne PAS écrire (caller retry §4)."""
    from shared.thesis_predictions_writer import insert_thesis_pose, update_thesis_resolve_fields
    pred_id = insert_thesis_pose(**_pose_kwargs())
    with pytest.raises(ValueError, match="alpha incalculable"):
        update_thesis_resolve_fields(
            prediction_id=pred_id, resolve_price_native=3_000_000.0,
            alpha_realized_pct=33.7, classify_result=None,
        )


def test_resolve_blocked_on_second_call(writer_db):
    """Re-resolve → trigger 2 mord → return False (pas raise, log only)."""
    from shared.thesis_predictions_writer import insert_thesis_pose, update_thesis_resolve_fields
    pred_id = insert_thesis_pose(**_pose_kwargs())
    ok1 = update_thesis_resolve_fields(
        prediction_id=pred_id, resolve_price_native=3_000_000.0,
        alpha_realized_pct=33.7, classify_result="correct",
    )
    assert ok1 is True
    ok2 = update_thesis_resolve_fields(
        prediction_id=pred_id, resolve_price_native=4_000_000.0,
        alpha_realized_pct=99.9, classify_result="correct",
    )
    assert ok2 is False  # trigger 2 a mordu


def test_resolve_returns_false_on_unknown_pred_id(writer_db):
    from shared.thesis_predictions_writer import update_thesis_resolve_fields
    ok = update_thesis_resolve_fields(
        prediction_id=99999, resolve_price_native=100.0,
        alpha_realized_pct=10.0, classify_result="correct",
    )
    assert ok is False


# ============================================================
# Round-trip end-to-end
# ============================================================


def test_round_trip_pose_due_resolve_aggregate(writer_db):
    """Workflow complet : pose SK + CCJ → get_due → resolve les deux."""
    from shared.thesis_predictions_writer import (
        get_due_thesis_predictions, insert_thesis_pose, update_thesis_resolve_fields,
    )
    # Pose SK (KRW)
    sk_id = insert_thesis_pose(**_pose_kwargs(resolve_due_date=date(2027, 1, 1)))
    # Pose CCJ (USD)
    ccj_id = insert_thesis_pose(**_pose_kwargs(
        ticker="CCJ", asof=date(2026, 6, 10), resolve_due_date=date(2027, 1, 1),
        native_currency="USD", pt_consensus_currency="USD",
        pt_consensus_raw=138.0, pt_native_asof=138.0,
        asof_price_native=105.44, your_target_native=155.0, your_delta_native_pct=16.1,
        thesis_summary="CCJ supercycle uranium",
    ))
    assert sk_id and ccj_id

    # Récupérer due
    due = get_due_thesis_predictions(today=date(2027, 6, 10))
    assert len(due) == 2
    assert {r["ticker"] for r in due} == {"000660.KS", "CCJ"}

    # Résoudre SK correct (action a battu PT)
    update_thesis_resolve_fields(
        prediction_id=sk_id, resolve_price_native=2_800_000.0,
        alpha_realized_pct=24.1, classify_result="correct", magnitude_score=0.117,
    )
    # Résoudre CCJ incorrect (action n'a pas atteint PT)
    update_thesis_resolve_fields(
        prediction_id=ccj_id, resolve_price_native=120.0,
        alpha_realized_pct=-17.1, classify_result="incorrect", magnitude_score=0.392,
    )

    # Re-check : plus de due
    due2 = get_due_thesis_predictions(today=date(2027, 6, 10))
    assert due2 == []

    # Verify final state
    cx = sqlite3.connect(str(writer_db))
    rows = cx.execute(
        "SELECT ticker, direction_correct, alpha_realized_pct FROM thesis_predictions "
        "WHERE resolved_at IS NOT NULL ORDER BY ticker"
    ).fetchall()
    assert rows == [("000660.KS", 1, 24.1), ("CCJ", 0, -17.1)]
    cx.close()
