"""Calibration 08/06 : test filtre primary entities pour get_material_signals_since.

Bug audit 1er run thesis_erosion : signal "Retatrutide" avec entities
[LLY, NVDA, AVGO, TSM, AMD, MSFT, GOOGL, META, AMZN] etait capture pour GOOGL
(7e position = mention secondaire). Le LLM Haiku, force de classifier, sur-
interpretait en "erodes" via chaine logique tordue.

Fix : ne capture le signal QUE si ticker dans top-N (=3) entities.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shared import storage


def _schema(cx: sqlite3.Connection) -> None:
    cx.executescript("""
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER, timestamp TEXT NOT NULL,
            title TEXT, content TEXT, summary TEXT, entities TEXT,
            impact_magnitude REAL, materiality_boost REAL,
            score INTEGER, sentiment TEXT, narratives TEXT,
            decay_at TEXT, raw_url TEXT, gmail_id TEXT,
            user_feedback TEXT, echo_cluster_id INTEGER,
            signal_type TEXT, reversibility TEXT,
            time_to_realization TEXT, materiality_breakdown TEXT,
            scoring_status TEXT
        );
        CREATE TABLE chat_extracted_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            chat_message_id INTEGER, kind TEXT, ticker TEXT, sector TEXT,
            theme TEXT, valence TEXT, confidence REAL,
            evidence_quote TEXT, note TEXT, model_used TEXT, cost_usd REAL
        );
    """)


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = tmp_path / "t.db"
    cx = sqlite3.connect(p)
    _schema(cx)
    monkeypatch.setattr("shared.storage.DB_PATH", p)
    return p, cx


def _seed_signal(cx, title, entities, days_ago=10, impact=4.0, mat_boost=1.7):
    ts = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    cx.execute(
        "INSERT INTO signals (timestamp, title, summary, entities, "
        "impact_magnitude, materiality_boost) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, title, "summary", json.dumps(entities), impact, mat_boost),
    )


# ─── Test 1 : ticker en top-3 -> capture ────────────────────────────────


def test_primary_entity_top1_captured(db) -> None:
    p, cx = db
    _seed_signal(cx, "NVDA earnings beat", ["NVDA", "AMD", "AVGO"])
    cx.commit(); cx.close()
    out = storage.get_material_signals_since("NVDA", "2020-01-01", 12)
    assert len(out) == 1


def test_primary_entity_top2_captured(db) -> None:
    p, cx = db
    _seed_signal(cx, "TSM Q3", ["TSM", "NVDA", "AMD"])
    cx.commit(); cx.close()
    out = storage.get_material_signals_since("NVDA", "2020-01-01", 12)
    assert len(out) == 1


def test_primary_entity_top3_boundary_captured(db) -> None:
    """Ticker exactement en position 3 (top_N=3 inclusif) -> capture."""
    p, cx = db
    _seed_signal(cx, "Semis update", ["ASML", "TSM", "NVDA"])
    cx.commit(); cx.close()
    out = storage.get_material_signals_since("NVDA", "2020-01-01", 12)
    assert len(out) == 1


# ─── Test 2 : ticker en position > top-3 -> filtre out (mention secondaire)


def test_secondary_entity_position4_filtered_out(db) -> None:
    """LE TEST CALIBRATION : ticker en 4e position = mention secondaire = SKIP."""
    p, cx = db
    _seed_signal(cx, "Macro", ["LLY", "NVDA", "AMD", "GOOGL"])
    cx.commit(); cx.close()
    out = storage.get_material_signals_since("GOOGL", "2020-01-01", 12)
    assert out == []


def test_retatrutide_case_real_world(db) -> None:
    """Le cas reel decouvert par audit : Retatrutide entities=[LLY+8 mega-caps].
    GOOGL en 7e position = mention macro secondaire, doit etre SKIPPED."""
    p, cx = db
    _seed_signal(
        cx,
        "Retatrutide hits 28% weight loss in Phase 3",
        ["LLY", "NVDA", "AVGO", "TSM", "AMD", "MSFT", "GOOGL", "META", "AMZN"],
        impact=4.0, mat_boost=1.7,
    )
    cx.commit(); cx.close()
    # LLY (position 0) = capture
    assert len(storage.get_material_signals_since("LLY", "2020-01-01", 12)) == 1
    # NVDA (position 1) = capture
    assert len(storage.get_material_signals_since("NVDA", "2020-01-01", 12)) == 1
    # AVGO (position 2) = capture (top-3 boundary)
    assert len(storage.get_material_signals_since("AVGO", "2020-01-01", 12)) == 1
    # TSM (position 3) = SKIP (position 4 1-indexed, hors top-3)
    assert storage.get_material_signals_since("TSM", "2020-01-01", 12) == []
    # GOOGL (position 6) = SKIP
    assert storage.get_material_signals_since("GOOGL", "2020-01-01", 12) == []
    assert storage.get_material_signals_since("AMZN", "2020-01-01", 12) == []


# ─── Test 3 : entities non-JSON ou vide -> SKIP gracieusement ────────────


def test_malformed_entities_skipped(db) -> None:
    p, cx = db
    cx.execute(
        "INSERT INTO signals (timestamp, title, entities, impact_magnitude) "
        "VALUES (?, ?, ?, ?)",
        ("2026-06-01", "broken json", "{bad}", 1.0),
    )
    cx.commit(); cx.close()
    out = storage.get_material_signals_since("ANY", "2020-01-01", 12)
    assert out == []


def test_empty_entities_skipped(db) -> None:
    p, cx = db
    _seed_signal(cx, "no entities", [])
    cx.commit(); cx.close()
    out = storage.get_material_signals_since("ANY", "2020-01-01", 12)
    assert out == []


# ─── Test 4 : chat_extracted_signals toujours capture (par ticker exact) ──


def test_chat_extracted_captured_regardless(db) -> None:
    """chat_extracted_signals filtre par ticker= (pas par entities), donc
    toujours capture si match exact. Le filtre primary_entity ne s'applique
    qu'aux signals avec JSON entities."""
    p, cx = db
    cx.execute(
        "INSERT INTO chat_extracted_signals (created_at, ticker, confidence, "
        "evidence_quote, note) VALUES (?, ?, ?, ?, ?)",
        ("2026-06-01", "GOOGL", 0.7, "quote", "note"),
    )
    cx.commit(); cx.close()
    out = storage.get_material_signals_since("GOOGL", "2020-01-01", 12)
    assert len(out) == 1


# ─── Test 5 : ordre materiality preserve apres filter ────────────────────


def test_order_by_materiality_preserved(db) -> None:
    p, cx = db
    _seed_signal(cx, "low", ["NVDA"], impact=1.0, mat_boost=1.0)        # 1.0
    _seed_signal(cx, "high", ["NVDA"], impact=4.0, mat_boost=2.0)       # 8.0
    _seed_signal(cx, "mid", ["NVDA"], impact=2.0, mat_boost=1.5)        # 3.0
    cx.commit(); cx.close()
    out = storage.get_material_signals_since("NVDA", "2020-01-01", 12)
    assert len(out) == 3
    assert out[0]["materiality"] == 8.0
    assert out[1]["materiality"] == 3.0
    assert out[2]["materiality"] == 1.0
