"""Tests pièce 3 — writers thesis_predictions (SPEC §2.2 + décisions A/B/C/D/E).

Vérifie :
- Mapping classify → DB (4 cas + None refusé)
- Fail-closed à la pose : no_bet skipped, UNIQUE handled
- Resolve atomique : 1 UPDATE passe, splits mordus par trigger 2
- Round-trip insert → get_due → update_resolve

Fixture canonique : migrated_db de tests/conftest.py qui applique la
vraie chaîne migrations alembic (0001→head, incluant 0052 + 0053).
L8 doctrine + #41 (01/06) : fixtures dérivées de la migration courante,
pas hand-roll.

Hand-roll _apply_0052_schema supprimé (red-team Olivier 11/06) : c'était
un 2-référentiels figé à 0052 sans resolution_status — bloqueur pièce 4
dès que update_resolve setera resolution_status='resolved'.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import pytest


def _pose_kwargs(**overrides):
    """SK Hynix scenario par défaut, override possible."""
    base = {
        "ticker": "000660.KS",
        "asof": date(2026, 6, 10),
        "asof_price_native": 2_077_000.0,
        "native_currency": "KRW",
        "pt_consensus_raw": 2_300_000.0,
        "pt_consensus_currency": "KRW",
        "pt_native_asof": 2_300_000.0,
        "fx_at_asof": 1.0,
        "your_target_native": 3_800_000.0,
        "your_delta_native_pct": 72.2,
        "thesis_summary": "SK Hynix HBM gen5 bull thesis",
        "resolve_due_date": date(2027, 6, 10),
        "source": "sweep_133",
    }
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


def test_insert_pose_succeeds_for_real_bet(migrated_db):
    from shared.thesis_predictions_writer import insert_thesis_pose
    pred_id = insert_thesis_pose(**_pose_kwargs())
    assert pred_id is not None
    assert pred_id > 0


def test_insert_pose_skips_no_bet(migrated_db):
    """Gate no_bet : |delta| < ε_delta=1.0 → skip, log event, return None."""
    from shared import storage
    from shared.thesis_predictions_writer import insert_thesis_pose
    pred_id = insert_thesis_pose(**_pose_kwargs(your_delta_native_pct=0.5))
    assert pred_id is None
    # Verify event logged
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT event_type FROM bot_events WHERE event_type='no_variant_view_at_pose'"
        ).fetchall()
    assert len(rows) == 1


def test_insert_pose_skips_no_bet_symmetric_negative(migrated_db):
    """Gate no_bet symétrique : |-0.5%| < ε_delta = no_bet aussi."""
    from shared.thesis_predictions_writer import insert_thesis_pose
    assert insert_thesis_pose(**_pose_kwargs(your_delta_native_pct=-0.5)) is None


def test_insert_pose_handles_unique_collision(migrated_db):
    """Double pose même (ticker, asof, target) → 2e return None + log dupe."""
    from shared import storage
    from shared.thesis_predictions_writer import insert_thesis_pose
    id1 = insert_thesis_pose(**_pose_kwargs())
    assert id1 is not None
    id2 = insert_thesis_pose(**_pose_kwargs())
    assert id2 is None
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT event_type FROM bot_events WHERE event_type='thesis_pose_duplicate'"
        ).fetchall()
    assert len(rows) == 1


def test_insert_pose_allows_multi_target_same_asof(migrated_db):
    """Partial + full sur même asof = 2 lignes distinctes."""
    from shared.thesis_predictions_writer import insert_thesis_pose
    id1 = insert_thesis_pose(**_pose_kwargs(your_target_native=2_650_000.0, your_delta_native_pct=15.2))
    id2 = insert_thesis_pose(**_pose_kwargs(your_target_native=3_800_000.0, your_delta_native_pct=72.2))
    assert id1 is not None and id2 is not None and id1 != id2


# ============================================================
# get_due_thesis_predictions
# ============================================================


def test_get_due_returns_only_due_and_unresolved(migrated_db):
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


def test_get_due_excludes_already_resolved(migrated_db):
    from shared.thesis_predictions_writer import (
        get_due_thesis_predictions,
        insert_thesis_pose,
        update_thesis_resolve_fields,
    )
    id1 = insert_thesis_pose(**_pose_kwargs(resolve_due_date=date(2027, 1, 1)))
    update_thesis_resolve_fields(
        prediction_id=id1, resolve_price_native=3_000_000.0,
        alpha_realized_pct=33.7, classify_result="correct", magnitude_score=0.117,
    )
    due = get_due_thesis_predictions(today=date(2027, 6, 10))
    assert all(r["id"] != id1 for r in due)


# ============================================================
# update_thesis_resolve_fields — atomic + classify mapping
# ============================================================


def test_resolve_atomic_writes_all_fields_at_once(migrated_db):
    """UPDATE atomique inclut resolution_status='resolved' (SPEC §4.1 lifecycle)."""
    from shared import storage
    from shared.thesis_predictions_writer import insert_thesis_pose, update_thesis_resolve_fields
    pred_id = insert_thesis_pose(**_pose_kwargs())
    ok = update_thesis_resolve_fields(
        prediction_id=pred_id, resolve_price_native=3_000_000.0,
        alpha_realized_pct=33.7, classify_result="correct", magnitude_score=0.117,
    )
    assert ok is True
    with storage.db() as cx:
        row = cx.execute(
            "SELECT resolved_at, resolve_price_native, alpha_realized_pct, "
            "direction_correct, magnitude_score, exclude_reason, resolution_status "
            "FROM thesis_predictions WHERE id=?", (pred_id,)
        ).fetchone()
    assert row[0] is not None  # resolved_at set
    assert row[1] == 3_000_000.0
    assert row[2] == 33.7
    assert row[3] == 1  # correct → 1
    assert row[4] == 0.117
    assert row[5] is None  # no scoring exclude
    assert row[6] == "resolved"  # lifecycle = resolved (SPEC §4.1)


def test_resolve_neutral_sets_exclude_reason(migrated_db):
    """Neutral : direction_correct=NULL + exclude_reason='neutral' +
    resolution_status='resolved' (le pari A été résolu, juste non-scorable)."""
    from shared import storage
    from shared.thesis_predictions_writer import insert_thesis_pose, update_thesis_resolve_fields
    pred_id = insert_thesis_pose(**_pose_kwargs())
    update_thesis_resolve_fields(
        prediction_id=pred_id, resolve_price_native=2_310_000.0,
        alpha_realized_pct=0.5, classify_result="neutral",  # |alpha|<1%
    )
    with storage.db() as cx:
        row = cx.execute(
            "SELECT direction_correct, exclude_reason, resolution_status "
            "FROM thesis_predictions WHERE id=?",
            (pred_id,)
        ).fetchone()
    assert row[0] is None  # neutral → direction_correct NULL (exclu scoring)
    assert row[1] == "neutral"  # axe scoring
    assert row[2] == "resolved"  # axe lifecycle — le pari A été résolu


# ============================================================
# mark_thesis_prediction_abandoned (pièce 3++)
# ============================================================


def test_mark_abandoned_sets_lifecycle_and_nulls_scoring_cols(migrated_db):
    """Abandon terminal : resolution_status='abandoned', tous scoring cols NULL.

    La ligne sort du pool get_due (resolved_at set) ET du pool scoring
    (direction_correct=NULL → exclu par WHERE direction_correct IS NOT NULL
    de l'agrégateur SPEC §4.1).
    """
    from shared import storage
    from shared.thesis_predictions_writer import (
        insert_thesis_pose,
        mark_thesis_prediction_abandoned,
    )
    pred_id = insert_thesis_pose(**_pose_kwargs())
    ok = mark_thesis_prediction_abandoned(prediction_id=pred_id)
    assert ok is True
    with storage.db() as cx:
        row = cx.execute(
            "SELECT resolved_at, resolve_price_native, alpha_realized_pct, "
            "direction_correct, magnitude_score, exclude_reason, resolution_status "
            "FROM thesis_predictions WHERE id=?", (pred_id,)
        ).fetchone()
    assert row[0] is not None  # resolved_at set → sort de get_due
    assert row[1] is None  # resolve_price_native NULL (jamais observé)
    assert row[2] is None  # alpha_realized_pct NULL (jamais calculé)
    assert row[3] is None  # direction_correct NULL → exclu scoring
    assert row[4] is None  # magnitude_score NULL
    assert row[5] is None  # pas un scoring exclude (lifecycle distinct)
    assert row[6] == "abandoned"  # lifecycle terminal


def test_mark_abandoned_removes_from_get_due_pool(migrated_db):
    """Post-abandon, get_due ne re-pickup plus (resolved_at set)."""
    from datetime import date as _date

    from shared.thesis_predictions_writer import (
        get_due_thesis_predictions,
        insert_thesis_pose,
        mark_thesis_prediction_abandoned,
    )
    pred_id = insert_thesis_pose(**_pose_kwargs(resolve_due_date=_date(2027, 1, 1)))
    mark_thesis_prediction_abandoned(prediction_id=pred_id)
    due = get_due_thesis_predictions(today=_date(2027, 6, 10))
    assert all(r["id"] != pred_id for r in due)


def test_mark_abandoned_logs_bot_event(migrated_db):
    """Abandon logge un event 'thesis_resolve_abandoned' avec reason."""
    from shared import storage
    from shared.thesis_predictions_writer import (
        insert_thesis_pose,
        mark_thesis_prediction_abandoned,
    )
    pred_id = insert_thesis_pose(**_pose_kwargs())
    mark_thesis_prediction_abandoned(prediction_id=pred_id, reason="price_unavailable")
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT event_type, details FROM bot_events "
            "WHERE event_type='thesis_resolve_abandoned'"
        ).fetchall()
    assert len(rows) == 1
    assert "price_unavailable" in rows[0][1]
    assert str(pred_id) in rows[0][1]


def test_mark_abandoned_blocked_on_already_resolved(migrated_db):
    """L'abandon ne peut PAS overwrite une résolution normale (trigger 2 mord)."""
    from shared.thesis_predictions_writer import (
        insert_thesis_pose,
        mark_thesis_prediction_abandoned,
        update_thesis_resolve_fields,
    )
    pred_id = insert_thesis_pose(**_pose_kwargs())
    # Résolution normale d'abord
    update_thesis_resolve_fields(
        prediction_id=pred_id, resolve_price_native=3_000_000.0,
        alpha_realized_pct=33.7, classify_result="correct",
    )
    # Tentative abandon post-résolution → trigger 2 mord
    ok = mark_thesis_prediction_abandoned(prediction_id=pred_id)
    assert ok is False


def test_mark_abandoned_returns_false_on_unknown_pred_id(migrated_db):
    from shared.thesis_predictions_writer import mark_thesis_prediction_abandoned
    ok = mark_thesis_prediction_abandoned(prediction_id=99999)
    assert ok is False


def test_mark_abandoned_twice_blocked_idempotent_intent(migrated_db):
    """Re-mark_abandoned sur même pred → trigger 2 mord (resolved_at déjà set).
    Pas un crash — le 2e call retourne False. L'abandon est terminal,
    idempotent par échec contrôlé."""
    from shared.thesis_predictions_writer import (
        insert_thesis_pose,
        mark_thesis_prediction_abandoned,
    )
    pred_id = insert_thesis_pose(**_pose_kwargs())
    ok1 = mark_thesis_prediction_abandoned(prediction_id=pred_id)
    ok2 = mark_thesis_prediction_abandoned(prediction_id=pred_id)
    assert ok1 is True
    assert ok2 is False  # trigger 2 mord (resolved_at set par 1er call)


def test_resolve_raises_on_none_classify(migrated_db):
    """classify=None signifie alpha incalculable → ne PAS écrire (caller retry §4)."""
    from shared.thesis_predictions_writer import insert_thesis_pose, update_thesis_resolve_fields
    pred_id = insert_thesis_pose(**_pose_kwargs())
    with pytest.raises(ValueError, match="alpha incalculable"):
        update_thesis_resolve_fields(
            prediction_id=pred_id, resolve_price_native=3_000_000.0,
            alpha_realized_pct=33.7, classify_result=None,
        )


def test_resolve_blocked_on_second_call(migrated_db):
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
    assert ok2 is False


def test_resolve_returns_false_on_unknown_pred_id(migrated_db):
    from shared.thesis_predictions_writer import update_thesis_resolve_fields
    ok = update_thesis_resolve_fields(
        prediction_id=99999, resolve_price_native=100.0,
        alpha_realized_pct=10.0, classify_result="correct",
    )
    assert ok is False


# ============================================================
# Round-trip end-to-end
# ============================================================


def test_round_trip_pose_due_resolve_aggregate(migrated_db):
    """Workflow complet : pose SK + CCJ → get_due → resolve les deux."""
    from shared import storage
    from shared.thesis_predictions_writer import (
        get_due_thesis_predictions,
        insert_thesis_pose,
        update_thesis_resolve_fields,
    )
    sk_id = insert_thesis_pose(**_pose_kwargs(resolve_due_date=date(2027, 1, 1)))
    ccj_id = insert_thesis_pose(**_pose_kwargs(
        ticker="CCJ", asof=date(2026, 6, 10), resolve_due_date=date(2027, 1, 1),
        native_currency="USD", pt_consensus_currency="USD",
        pt_consensus_raw=138.0, pt_native_asof=138.0,
        asof_price_native=105.44, your_target_native=155.0, your_delta_native_pct=16.1,
        thesis_summary="CCJ supercycle uranium",
    ))
    assert sk_id and ccj_id

    due = get_due_thesis_predictions(today=date(2027, 6, 10))
    assert len(due) == 2
    assert {r["ticker"] for r in due} == {"000660.KS", "CCJ"}

    update_thesis_resolve_fields(
        prediction_id=sk_id, resolve_price_native=2_800_000.0,
        alpha_realized_pct=24.1, classify_result="correct", magnitude_score=0.117,
    )
    update_thesis_resolve_fields(
        prediction_id=ccj_id, resolve_price_native=120.0,
        alpha_realized_pct=-17.1, classify_result="incorrect", magnitude_score=0.392,
    )

    due2 = get_due_thesis_predictions(today=date(2027, 6, 10))
    assert due2 == []

    with storage.db() as cx:
        rows = cx.execute(
            "SELECT ticker, direction_correct, alpha_realized_pct FROM thesis_predictions "
            "WHERE resolved_at IS NOT NULL ORDER BY ticker"
        ).fetchall()
    assert [tuple(r) for r in rows] == [("000660.KS", 1, 24.1), ("CCJ", 0, -17.1)]
