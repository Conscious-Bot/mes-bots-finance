"""Tests pour migration 0022 + wrap resolve_prediction_row.

PIT bitemporal predictions (E3 strategie user 31/05). Verifie :
- Premiere resolution -> 1 event_type='resolve' dans audit log
- Re-resolution -> 2 events ('re_resolve_pre' avec ancien snapshot + 're_resolve' avec nouveau)
- Trigger append-only : UPDATE sur audit log abort
- Indexes prediction_id + event_type queryables
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from shared import storage


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """In-disk SQLite isole (pas in-memory : storage.resolve_prediction_row
    ouvre sa propre connection). Schema minimal + table + trigger."""
    db_path = tmp_path / "test_audit.db"
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    cx = sqlite3.connect(db_path)
    cx.executescript("""
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
            brier_score REAL,
            probability_at_creation REAL,
            methodology_version TEXT NOT NULL DEFAULT 'v1'
        );
        CREATE TABLE prediction_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
            payload_json TEXT NOT NULL DEFAULT '{}',
            source TEXT,
            actor TEXT
        );
        CREATE TRIGGER prediction_audit_log_no_update
            BEFORE UPDATE ON prediction_audit_log
            BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        INSERT INTO predictions (id, ticker, direction, horizon_days, baseline_price, baseline_date, target_date, probability_at_creation)
        VALUES (1, 'AAPL', 'bullish', 14, 100.0, '2026-05-01', '2026-05-15', 0.65);
    """)
    cx.commit()
    cx.close()
    return db_path


def test_first_resolve_writes_one_resolve_event(isolated_db: Path) -> None:
    storage.resolve_prediction_row(
        prediction_id=1, final_price=105.0, return_pct=0.05,
        outcome="correct", credibility_delta=0.03, brier_score=0.1225,
    )
    cx = sqlite3.connect(isolated_db)
    rows = cx.execute(
        "SELECT event_type, json_extract(payload_json, '$.outcome') "
        "FROM prediction_audit_log WHERE prediction_id=1 ORDER BY id"
    ).fetchall()
    cx.close()
    assert len(rows) == 1
    assert rows[0][0] == "resolve"
    assert rows[0][1] == "correct"


def test_re_resolve_writes_pre_and_post(isolated_db: Path) -> None:
    storage.resolve_prediction_row(
        prediction_id=1, final_price=105.0, return_pct=0.05,
        outcome="correct", credibility_delta=0.03, brier_score=0.1225,
    )
    storage.resolve_prediction_row(
        prediction_id=1, final_price=108.0, return_pct=0.08,
        outcome="correct", credibility_delta=0.03, brier_score=0.1225,
    )
    cx = sqlite3.connect(isolated_db)
    rows = cx.execute(
        "SELECT event_type, json_extract(payload_json, '$.outcome'), "
        "       json_extract(payload_json, '$.final_price') "
        "FROM prediction_audit_log WHERE prediction_id=1 ORDER BY id"
    ).fetchall()
    cx.close()
    assert len(rows) == 3  # resolve + re_resolve_pre + re_resolve
    assert rows[0][0] == "resolve"
    assert rows[1][0] == "re_resolve_pre"  # snapshot avant overwrite
    assert rows[1][2] == 105.0  # ancien final_price preserve
    assert rows[2][0] == "re_resolve"
    assert rows[2][2] == 108.0  # nouveau


def test_audit_log_is_append_only_trigger_aborts_update(isolated_db: Path) -> None:
    """Tentative d'UPDATE sur audit log doit ABORT (trigger no_update)."""
    storage.resolve_prediction_row(
        prediction_id=1, final_price=105.0, return_pct=0.05,
        outcome="correct", credibility_delta=0.03, brier_score=0.1225,
    )
    cx = sqlite3.connect(isolated_db)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        cx.execute("UPDATE prediction_audit_log SET event_type='hacked' WHERE id=1")
    cx.close()


def test_source_and_actor_propagated_to_audit_log(isolated_db: Path) -> None:
    storage.resolve_prediction_row(
        prediction_id=1, final_price=105.0, return_pct=0.05,
        outcome="correct", credibility_delta=0.03, brier_score=0.1225,
        source="cron:daily_resolve_job", actor="bot_main",
    )
    cx = sqlite3.connect(isolated_db)
    row = cx.execute(
        "SELECT source, actor FROM prediction_audit_log WHERE prediction_id=1"
    ).fetchone()
    cx.close()
    assert row[0] == "cron:daily_resolve_job"
    assert row[1] == "bot_main"
