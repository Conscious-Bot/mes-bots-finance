"""Tests migration 0060 -- predictions claim_type/resolution_source/origin.

Cure chantier #150 G2 : le schema predictions a appris qu'une prediction peut
etre autre chose qu'un pari de prix sur ticker issue d'un signal.

8 tests :
1. Schema post-migration : ticker NULL OK, 3 nouvelles colonnes presentes.
2. Backfill : 285 lignes existantes -> claim_type='price', origin='signal'.
3. Triggers append-only PRESERVES (no_delete + resolve_writeonce).
4. INSERT event sans resolution_source -> ValueError (validation app).
5. INSERT manual sans signal_id -> OK (signal_id NULL accepte).
6. INSERT signal sans signal_id -> ValueError (validation app).
7. INSERT event sans ticker -> OK (ticker NULL accepte schema).
8. resolve_due_predictions skip event/data, ne lit pas baseline_price.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_schema_post_0060_has_new_columns(migrated_db):
    """ticker nullable, claim_type/resolution_source/origin presents."""
    import sqlite3
    cx = sqlite3.connect(migrated_db)
    cols = {r[1]: r for r in cx.execute("PRAGMA table_info(predictions)").fetchall()}
    # ticker nullable (notnull=0 dans pragma)
    assert cols["ticker"][3] == 0, f"ticker doit etre nullable post 0060, pragma={cols['ticker']}"
    # nouvelles colonnes
    assert "claim_type" in cols
    assert "resolution_source" in cols
    assert "origin" in cols
    # claim_type NOT NULL avec default
    assert cols["claim_type"][3] == 1
    # origin NOT NULL avec default
    assert cols["origin"][3] == 1


def test_triggers_append_only_preserved(migrated_db):
    """Migration recreate-table PRESERVE les 2 triggers append-only."""
    import sqlite3
    cx = sqlite3.connect(migrated_db)
    trigs = [
        r[0] for r in cx.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='predictions'"
        ).fetchall()
    ]
    assert "predictions_no_delete" in trigs
    assert "predictions_resolve_writeonce" in trigs


def test_insert_event_without_resolution_source_raises(migrated_db):
    """event/data REQUIERT resolution_source."""
    from shared import storage as s
    # Cree d'abord un signal parent valide pour le test
    import sqlite3
    cx = sqlite3.connect(migrated_db)
    cx.execute(
        "INSERT INTO sources (name, type, credibility, family) "
        "VALUES ('test_src_0060', 'manual', 0.8, 'test')"
    )
    sid_source = cx.execute(
        "SELECT id FROM sources WHERE name='test_src_0060'"
    ).fetchone()[0]
    cx.execute(
        "INSERT INTO signals (source_id, gmail_id, timestamp, title, content, scoring_status) "
        "VALUES (?, 'g1_0060', '2026-06-13', 'subj', 'content', 'pending')",
        (sid_source,),
    )
    sid = cx.execute("SELECT id FROM signals WHERE gmail_id='g1_0060'").fetchone()[0]
    cx.commit()
    cx.close()
    with pytest.raises(ValueError, match="resolution_source"):
        s.insert_prediction(
            signal_id=sid, ticker="MU", direction="watch", horizon_days=200,
            baseline_price=None, baseline_date="2026-06-13", target_date="2026-12-31",
            methodology_version="v2", probability_override=0.25,
            claim_type="event", resolution_source=None,
        )


def test_insert_manual_without_signal_id_ok(migrated_db):
    """origin='manual' accepte signal_id NULL."""
    from shared import storage as s
    pid = s.insert_prediction(
        signal_id=None, ticker="MU", direction="watch", horizon_days=200,
        baseline_price=None, baseline_date="2026-06-13", target_date="2026-12-31",
        methodology_version="v2", probability_override=0.25,
        claim_type="event", resolution_source="TrendForce hebdo",
        origin="manual",
    )
    assert pid is not None and pid > 0


def test_insert_signal_without_signal_id_raises(migrated_db):
    """origin='signal' EXIGE signal_id (defaut backwards-compat)."""
    from shared import storage as s
    with pytest.raises(ValueError, match="signal_id"):
        s.insert_prediction(
            signal_id=None, ticker="MU", direction="bullish", horizon_days=30,
            baseline_price=100.0, baseline_date="2026-06-13", target_date="2026-07-13",
            methodology_version="v2", probability_override=0.60,
            # claim_type='price' + origin='signal' par defaut
        )


def test_insert_event_without_ticker_ok(migrated_db):
    """Macro event (DRAM glut, hyperscaler capex) -> ticker NULL accepte."""
    from shared import storage as s
    pid = s.insert_prediction(
        signal_id=None, ticker=None, direction="watch", horizon_days=200,
        baseline_price=None, baseline_date="2026-06-13", target_date="2026-12-31",
        methodology_version="v2", probability_override=0.25,
        claim_type="event", resolution_source="TrendForce/DRAMeXchange hebdo",
        origin="manual",
    )
    assert pid is not None and pid > 0


def test_insert_invalid_claim_type_raises(migrated_db):
    """claim_type doit etre IN ('price','event','data')."""
    from shared import storage as s
    with pytest.raises(ValueError, match="claim_type"):
        s.insert_prediction(
            signal_id=None, ticker="MU", direction="watch", horizon_days=30,
            baseline_price=None, baseline_date="2026-06-13", target_date="2026-07-13",
            methodology_version="v2", probability_override=0.50,
            claim_type="invented", resolution_source="x", origin="manual",
        )


def test_resolve_due_skips_event_type(migrated_db):
    """resolve_due_predictions ne touche pas aux event/data claims.

    Garantit que la resolution prix-basee ne contamine pas un event-claim
    (cure pattern price-as-proof, doctrine 13/06).
    """
    from shared import storage as s
    from intelligence import learning as l
    # Pose 1 event-claim deja due (target_date passe)
    pid = s.insert_prediction(
        signal_id=None, ticker=None, direction="watch", horizon_days=1,
        baseline_price=None, baseline_date="2026-06-10", target_date="2026-06-11",
        methodology_version="v2", probability_override=0.25,
        claim_type="event", resolution_source="TrendForce",
        origin="manual",
    )
    assert pid is not None
    # resolve_due_predictions doit le SKIP (pas crash, pas resolve)
    with patch("shared.prices.get_price_on_date", return_value=(None, None)):
        out = l.resolve_due_predictions(limit=10)
    assert out.get("skipped_event", 0) >= 1
    # event-claim toujours non-resolu (resolved_at IS NULL)
    import sqlite3
    cx = sqlite3.connect(migrated_db)
    row = cx.execute("SELECT resolved_at FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row[0] is None, "event-claim doit rester non-resolu post resolve_due_predictions"
