"""Etape 3 chantier #2 : tests event-driven trigger thesis_erosion.

Verrouille :
- Signal fresh post-cutoff sur ticker avec these active -> trigger recompute
- Signal sur ticker SANS these active -> skip
- Signal post-cutoff sur ticker en POSITION SECONDAIRE entities -> skip
  (calibration primary-entity filter)
- Verdict change INTACT -> EROSION_DETECTED -> push Telegram notable
- Verdict no-change -> no push (silent)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from intelligence import thesis_erosion as te


def _schema(cx: sqlite3.Connection) -> None:
    cx.executescript("""
        CREATE TABLE theses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, opened_at TEXT NOT NULL,
            conviction INTEGER, direction TEXT DEFAULT 'long',
            key_drivers TEXT, invalidation_triggers TEXT,
            status TEXT DEFAULT 'active'
        );
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
        CREATE TABLE thesis_erosion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            computed_at TEXT NOT NULL DEFAULT (datetime('now')),
            thesis_id INTEGER NOT NULL, ticker TEXT NOT NULL,
            verdict TEXT NOT NULL,
            n_confirm INTEGER DEFAULT 0, n_erode INTEGER DEFAULT 0,
            n_invalidation_hit INTEGER DEFAULT 0,
            driver_status_json TEXT NOT NULL DEFAULT '[]',
            signals_considered_json TEXT NOT NULL DEFAULT '[]',
            degraded INTEGER DEFAULT 0, steer TEXT
        );
        CREATE TABLE thesis_erosion_classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            erosion_log_id INTEGER NOT NULL, signal_id INTEGER NOT NULL,
            signal_source TEXT NOT NULL,
            bears_on TEXT, target_index INTEGER, relation TEXT,
            confidence REAL, materiality REAL, rationale TEXT, evidence_quote TEXT
        );
    """)


def _seed_thesis(cx, ticker="ASML.AS", prev_verdict=None):
    cur = cx.execute(
        "INSERT INTO theses (ticker, opened_at, conviction, key_drivers, "
        "invalidation_triggers) VALUES (?, ?, ?, ?, ?)",
        (ticker, "2026-03-15T00:00:00+00:00", 5,
         json.dumps(["Duopole EUV"]),
         json.dumps(["Bookings <35B"])),
    )
    tid = cur.lastrowid
    if prev_verdict:
        cx.execute(
            "INSERT INTO thesis_erosion_log (thesis_id, ticker, verdict) "
            "VALUES (?, ?, ?)",
            (tid, ticker, prev_verdict),
        )
    return tid


def _seed_fresh_signal(cx, entities, minutes_ago=10):
    ts = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()
    cx.execute(
        "INSERT INTO signals (timestamp, title, summary, entities, "
        "impact_magnitude, materiality_boost) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, "Fresh sig", "summary", json.dumps(entities), 3.0, 1.5),
    )


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = tmp_path / "t.db"
    cx = sqlite3.connect(p)
    _schema(cx)
    monkeypatch.setattr("shared.storage.DB_PATH", p)
    return p, cx


# ─── Test 1 : fresh signal primary ticker active these -> trigger ────────


def test_fresh_signal_triggers_recompute(isolated_db, monkeypatch) -> None:
    """Signal fresh sur ASML.AS primary -> trigger compute (INTACT par défaut)."""
    _p, cx = isolated_db
    _seed_thesis(cx, "ASML.AS", prev_verdict="INTACT")
    _seed_fresh_signal(cx, ["ASML.AS", "TSM"])
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.notify.send_text", MagicMock())

    # Mock LLM to return neutral (verdict stays INTACT)
    monkeypatch.setattr(te.llm, "call", MagicMock(return_value=json.dumps({
        "bears_on": "none", "target_index": None,
        "relation": "neutral", "confidence": 0.3,
        "rationale": "x", "evidence_quote": "",
    })))

    stats = te.recompute_for_tickers_with_fresh_signals(since_minutes=30)
    assert stats["checked"] == 1
    assert stats["triggered"] == 1
    # No verdict change (INTACT -> INTACT) -> no notable
    assert len(stats["verdict_changes"]) == 0


# ─── Test 2 : fresh signal mais aucune these active -> skip ──────────────


def test_no_active_thesis_no_trigger(isolated_db, monkeypatch) -> None:
    _p, cx = isolated_db
    _seed_thesis(cx, "ASML.AS")
    _seed_fresh_signal(cx, ["NVDA", "AMD"])  # NVDA primary, mais pas de these
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.notify.send_text", MagicMock())

    stats = te.recompute_for_tickers_with_fresh_signals(since_minutes=30)
    assert stats["checked"] == 0
    assert stats["triggered"] == 0


# ─── Test 3 : signal primary ticker en POSITION SECONDAIRE -> skip ───────


def test_secondary_entity_position_skipped(isolated_db, monkeypatch) -> None:
    """ASML.AS en 5e position entities = secondaire = SKIP (calibration filter)."""
    _p, cx = isolated_db
    _seed_thesis(cx, "ASML.AS")
    _seed_fresh_signal(cx, ["LLY", "NVDA", "AMD", "TSM", "ASML.AS"])  # ASML en 5e
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.notify.send_text", MagicMock())

    stats = te.recompute_for_tickers_with_fresh_signals(since_minutes=30)
    # ASML.AS en position 5 (hors top-3) -> pas dans fresh_tickers
    assert stats["checked"] == 0


# ─── Test 4 : verdict change INTACT->EROSION_DETECTED -> push notable ────


def test_verdict_change_intact_to_erosion_triggers_push(isolated_db, monkeypatch) -> None:
    _p, cx = isolated_db
    _seed_thesis(cx, "ASML.AS", prev_verdict="INTACT")
    # 2 signaux fresh primary (impact*boost x conf -> net negatif fort)
    _seed_fresh_signal(cx, ["ASML.AS"])
    _seed_fresh_signal(cx, ["ASML.AS"])
    cx.commit()
    cx.close()
    notify_mock = MagicMock()
    monkeypatch.setattr("shared.notify.send_text", notify_mock)
    # Mock LLM to return erodes strong
    monkeypatch.setattr(te.llm, "call", MagicMock(return_value=json.dumps({
        "bears_on": "driver", "target_index": 0,
        "relation": "erodes", "confidence": 0.9,
        "rationale": "x", "evidence_quote": "y",
    })))

    stats = te.recompute_for_tickers_with_fresh_signals(since_minutes=30)
    assert stats["triggered"] == 1
    assert len(stats["verdict_changes"]) == 1
    change = stats["verdict_changes"][0]
    assert change["ticker"] == "ASML.AS"
    assert change["prev"] == "INTACT"
    assert change["new"] == "EROSION_DETECTED"
    assert notify_mock.call_count == 1
    msg = notify_mock.call_args[0][0]
    assert "ASML.AS" in msg
    assert "INTACT -> EROSION_DETECTED" in msg


# ─── Test 5 : signal hors fenetre (>30min) -> skip ──────────────────────


def test_old_signal_outside_window_skipped(isolated_db, monkeypatch) -> None:
    _p, cx = isolated_db
    _seed_thesis(cx, "ASML.AS")
    _seed_fresh_signal(cx, ["ASML.AS"], minutes_ago=120)  # 2h old
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.notify.send_text", MagicMock())

    stats = te.recompute_for_tickers_with_fresh_signals(since_minutes=30)
    assert stats["checked"] == 0


# ─── Test 6 : empty fresh_tickers -> stats vides clean ──────────────────


def test_empty_fresh_signals_no_op(isolated_db, monkeypatch) -> None:
    _p, cx = isolated_db
    cx.close()
    monkeypatch.setattr("shared.notify.send_text", MagicMock())

    stats = te.recompute_for_tickers_with_fresh_signals(since_minutes=30)
    assert stats == {
        "checked": 0, "triggered": 0,
        "verdict_changes": [], "errors": 0,
    }
