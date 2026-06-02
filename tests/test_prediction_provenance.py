"""#70 + #74 -- Tests audit trail full per prediction (provenance immutable).

Verifie que :
  1. Le schema head a les colonnes scoring_trace_json + source_metadata_json
  2. insert_prediction persiste les nouveaux fields
  3. get_prediction_provenance() retourne la chaine complete
  4. Les anciens predictions sans trace continuent de fonctionner (back-compat)
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


def _cols(db: Path, table: str) -> set[str]:
    cx = sqlite3.connect(db)
    try:
        rows = cx.execute(f"PRAGMA table_info({table})").fetchall()
    finally:
        cx.close()
    return {r[1] for r in rows}


# ─── Schema check (alembic head) ──────────────────────────────────────────


def test_predictions_has_scoring_trace_json(migrated_db):
    """Migration 0026 doit ajouter scoring_trace_json."""
    cols = _cols(migrated_db, "predictions")
    assert "scoring_trace_json" in cols


def test_predictions_has_source_metadata_json(migrated_db):
    """Migration 0026 doit ajouter source_metadata_json."""
    cols = _cols(migrated_db, "predictions")
    assert "source_metadata_json" in cols


# ─── insert_prediction persiste les nouveaux fields ───────────────────────


def test_insert_prediction_persists_scoring_trace(migrated_db):
    """Quand on passe scoring_trace_json, il doit etre stocke verbatim."""
    from shared import storage

    # Setup source + signal pour FK
    cx = sqlite3.connect(migrated_db)
    cx.execute("INSERT INTO sources (name, type, credibility) VALUES ('test_src', 'newsletter', 0.7)")
    src_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities) "
        "VALUES (?, 'test signal', '2026-06-02T10:00:00+00:00', '[\"NVDA\"]')",
        (src_id,),
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.commit()
    cx.close()

    trace = json.dumps({
        "version": "v2",
        "ticker": "NVDA",
        "base_rate": 0.55,
        "evidence_strength": "moderate",
        "probability": 0.68,
        "direction": "bullish",
        "reasoning": "earnings beat + guidance up",
    })
    meta = json.dumps({
        "title": "NVDA Q1 beat",
        "source_name": "SEC EDGAR 8-K",
        "credibility_at_creation": 0.85,
    })

    pid = storage.insert_prediction(
        signal_id=sig_id,
        ticker="NVDA",
        direction="bullish",
        horizon_days=28,
        baseline_price=140.0,
        baseline_date="2026-06-02",
        target_date="2026-06-30",
        probability_override=0.68,
        scoring_trace_json=trace,
        source_metadata_json=meta,
    )
    assert pid is not None

    # Verify persistence
    cx = sqlite3.connect(migrated_db)
    row = cx.execute(
        "SELECT scoring_trace_json, source_metadata_json FROM predictions WHERE id = ?",
        (pid,),
    ).fetchone()
    cx.close()
    assert row is not None
    assert row[0] == trace
    assert row[1] == meta


def test_insert_prediction_works_without_trace_backward_compat(migrated_db):
    """Sans scoring_trace_json, l'insert doit toujours marcher (legacy paths)."""
    from shared import storage

    cx = sqlite3.connect(migrated_db)
    cx.execute("INSERT INTO sources (name, type, credibility) VALUES ('test_src2', 'newsletter', 0.7)")
    src_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities) "
        "VALUES (?, 'test', '2026-06-02T10:00:00+00:00', '[\"MSFT\"]')",
        (src_id,),
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.commit()
    cx.close()

    pid = storage.insert_prediction(
        signal_id=sig_id,
        ticker="MSFT",
        direction="bullish",
        horizon_days=28,
        baseline_price=420.0,
        baseline_date="2026-06-02",
        target_date="2026-06-30",
        probability_override=0.62,
    )
    assert pid is not None
    cx = sqlite3.connect(migrated_db)
    row = cx.execute(
        "SELECT scoring_trace_json FROM predictions WHERE id = ?", (pid,),
    ).fetchone()
    cx.close()
    assert row[0] is None


# ─── get_prediction_provenance ────────────────────────────────────────────


def test_get_prediction_provenance_full_chain(migrated_db):
    """Retourne la chaine prediction + signal + source + trace + metadata."""
    from shared import storage

    cx = sqlite3.connect(migrated_db)
    cx.execute("INSERT INTO sources (name, type, credibility) VALUES ('EDGAR_8K', 'edgar', 0.85)")
    src_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities) "
        "VALUES (?, 'NVDA 8-K Q1 beat', '2026-06-02T10:00:00+00:00', '[\"NVDA\"]')",
        (src_id,),
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.commit()
    cx.close()

    trace_dict = {"version": "v2", "base_rate": 0.55, "probability": 0.68}
    meta_dict = {"title": "NVDA 8-K Q1 beat", "source_name": "EDGAR_8K"}

    pid = storage.insert_prediction(
        signal_id=sig_id,
        ticker="NVDA",
        direction="bullish",
        horizon_days=28,
        baseline_price=140.0,
        baseline_date="2026-06-02",
        target_date="2026-06-30",
        probability_override=0.68,
        scoring_trace_json=json.dumps(trace_dict, sort_keys=True),
        source_metadata_json=json.dumps(meta_dict, sort_keys=True),
    )

    prov = storage.get_prediction_provenance(pid)
    assert prov is not None
    assert prov["prediction"]["ticker"] == "NVDA"
    assert prov["prediction"]["probability_at_creation"] == 0.68
    assert prov["signal"]["title"] == "NVDA 8-K Q1 beat"
    assert prov["source"]["name"] == "EDGAR_8K"
    assert prov["source"]["credibility"] == 0.85
    assert prov["scoring_trace"]["base_rate"] == 0.55
    assert prov["source_metadata"]["title"] == "NVDA 8-K Q1 beat"


def test_get_prediction_provenance_unknown_id_returns_none(migrated_db):
    from shared import storage
    assert storage.get_prediction_provenance(99999) is None


def test_get_prediction_provenance_handles_corrupted_trace(migrated_db):
    """Si scoring_trace_json est corrompu, retourne dict avec scoring_trace=None
    (pas de crash). Defensive design pour les anciens rows."""
    from shared import storage

    cx = sqlite3.connect(migrated_db)
    cx.execute("INSERT INTO sources (name, type, credibility) VALUES ('x', 'newsletter', 0.5)")
    src_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities) "
        "VALUES (?, 'x', '2026-06-02T10:00:00+00:00', '[\"X\"]')",
        (src_id,),
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.execute(
        "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
        "baseline_price, baseline_date, target_date, probability_at_creation, "
        "scoring_trace_json) "
        "VALUES (?, 'X', 'bullish', 28, 100.0, '2026-06-02', '2026-06-30', 0.6, ?)",
        (sig_id, "{not valid json}"),
    )
    pid = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.commit()
    cx.close()

    prov = storage.get_prediction_provenance(pid)
    assert prov is not None
    assert prov["scoring_trace"] is None  # corrupted -> None, pas crash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
